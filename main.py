import asyncio
import threading
from bleak import BleakClient,exc
import bleak
import struct
import json
from paho.mqtt import client as MQTTClient
import re
import time
import random 
import extensions 

with open("config.json") as F:
    config=json.load(F)



mqttClient=MQTTClient.Client(MQTTClient.CallbackAPIVersion.VERSION2, f"BLE proxy-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))}")
mqttServerAddress=config["mqtt"]["serverAddress"].split(":")[0]
mqttPort=1883
if ":" in config["mqtt"]["serverAddress"]:
    mqttPort=int(config["mqtt"]["serverAddress"].split(":")[-1])

def onMqttConnect(client, userdata, flags, rc,xd):
    if rc == 0:
        print("Connected to MQTT Broker!")
    else:
        print("Failed to connect, return code %d\n", rc)
        
mqttClient.on_connect=onMqttConnect
mqttClient.password=config["mqtt"]["password"]
mqttClient.username=config["mqtt"]["username"]
mqttClient.connect(mqttServerAddress,mqttPort)

devicesData={}
#predefine data structure
for devAddr, device in config["devices"].items():
    devicesData[device["name"]]={"connected":False}
    for service in device["services"].values():
        devicesData[device["name"]][service["name"]]={}
        for characteristics in service["characteristics"].values():
            devicesData[device["name"]][service["name"]][characteristics["name"]]={"isUpdated":False,"isChanged":False,"data":None}

# Function to recursively parse and replace variables
def parse_inp(data, values,modifier=None,funcToRunOnReplace=None):
    if isinstance(data, str):
        # Find all the patterns of the format $A.B.c& that are not prefixed by \
        matches = re.findall(r'(?<!\\)\$(.*?)&', data)
        for match in matches:
            # Split path by '.' and retrieve value from values dictionary
            keys = match.split('.')
            val = values
            for key in keys:
                if key not in val.keys():
                    print(f"unable to find value {match} ({key})")
                    break
                val = val.get(key)
                
            if modifier is not None:
                    val=val[modifier]#replace whole sequence while keeping type 
            if funcToRunOnReplace is not None:
                funcToRunOnReplace(values,keys)
            # Replace the match only if it's not escaped
            if len(match)+2==len(data):
                data=val#replace whole sequence while keeping type 
            else:
                data = data.replace(f"${match}&", str(val))
                # Escape the expressions with \ in front of them
                data = data.replace(r"\$", r"$")
        return data
    elif isinstance(data, dict):
        return {parse_inp(key, values,modifier,funcToRunOnReplace): parse_inp(value, values,modifier,funcToRunOnReplace) for key, value in data.items()}
    elif isinstance(data, list):
        return [parse_inp(item, values,modifier,funcToRunOnReplace) for item in data]
    else:
        return data

async def bleTask(devAddr,deviceConfig):
    devData=devicesData[device["name"]]
    devData["isFirstConnect"]=True
    configuredServices=deviceConfig["services"]
    
    def connectCallback():

        print(f"restored connection to {device['name']}")
        devData["connected"]=bleClient.is_connected
        if "notifyOnChangeState" not  in deviceConfig.keys():
            return
        if "connect" not  in deviceConfig["notifyOnChangeState"].keys():
            return
        if not ("notifyOnFirstConnect" in deviceConfig["notifyOnChangeState"].keys() and deviceConfig["notifyOnChangeState"]["notifyOnFirstConnect"]):#if do not notify on first connect
            if devData["isFirstConnect"]:
                devData["isFirstConnect"]=False
                return 
        devData["isFirstConnect"]=False
        for topic,message in deviceConfig["notifyOnChangeState"]["connect"].items():
            mqttClient.publish(topic,json.dumps(message))
        pass
    
    def disconnectCallback(client):
        devData["connected"]=bleClient.is_connected
        if "notifyOnChangeState" not  in deviceConfig.keys():
            return
        if "disconnect" not  in deviceConfig["notifyOnChangeState"].keys():
            return
        print(f"lost connection to {device['name']}")
        for topic,message in deviceConfig["notifyOnChangeState"]["disconnect"].items():
            mqttClient.publish(topic,json.dumps(message))
        pass
    
    bleClient = BleakClient(devAddr,disconnectCallback,winrt=dict(use_cached_services=False))

    updateInterval=10
    reconnectInterval=60
    if "updateInterval" in deviceConfig.keys():
        updateInterval=deviceConfig["updateInterval"]
    if "reconnectInterval" in deviceConfig.keys():
        reconnectInterval=deviceConfig["reconnectInterval"]

    
    def loadChar(charConfig,value):
        try: 
            if charConfig["loadAs"]=="int":
                loaded=int.from_bytes(value, byteorder="little")
            elif charConfig["loadAs"]=="float":
                loaded=struct.unpack("f", value)[0]
            elif charConfig["loadAs"]=="string":
                loaded=value.decode( "encoding" in charConfig.keys() if  charConfig["encoding"] else 'utf-8' )#requires tesing
            elif charConfig["loadAs"]=="bytes":
                loaded=bytes(value)
            
        except Exception as e:
            #failed to load value, probably wrong type
            print(f"Failed to read characteristic {charConfig['name']} from service {configuredService['name']} in device {deviceConfig['name']} at address {devAddr}: {e}\n maybe bad format of loaded varible")
            return None
        try:
            #apply format from config
            func=eval(f"(lambda {charConfig['format']})")
            formated=func(loaded)
            dataStored=devicesData[deviceConfig["name"]][configuredService["name"]][charConfig["name"]]
            if dataStored["data"]!=formated:
                dataStored["data"]=formated
                dataStored["isChanged"]=True
            dataStored["isUpdated"]=True
            return formated
        except Exception as e:
            #failed to load value, probably bad function
            print(f"Failed to evaluete characteristic {charConfig['name']} from service {configuredService['name']} in device {deviceConfig['name']} at address {devAddr}: {e}\n check lambda expression")
            return None
   
    async def waitTillConnect():
        while not devData["connected"]:
            try:
                await bleClient.disconnect()
                await bleClient.connect()
                for configuredServiceUuid in configuredServices.keys():
                    service=bleClient.services.get_service(configuredServiceUuid)
                    if service is None:
                        print(f"Service with UUID {configuredServiceUuid} not found for device {deviceConfig['name']} at address {devAddr}")
                        continue
                    configuredService=configuredServices[configuredServiceUuid]
                    
                    for uuid,charConfig  in configuredService["characteristics"].items():
                        char= service.get_characteristic(uuid)
                        if char is None:
                            #nonExisteant charracteristics, 
                            print(f"Characteristic with UUID {charConfig['name']} not found for service {configuredService['name']} in device {deviceConfig['name']} at address {devAddr}")
                            continue
                        if "subscribe" in  charConfig.keys() and charConfig["subscribe"]==True:
                            if "notify" in char.properties:
                                async def notyfyCallback(sender: bleak.BleakGATTCharacteristic, data: bytearray):
                                    loadChar(charConfig,data)
                                    print("recieved notification for char")

                                try:
                                    # await bleClient.start_notify(char,notyfyCallback)#breaks on windows
                                    ...
                                except exc.BleakError:
                                    print(f"Failed to set notify for characteristic {charConfig['name']} in service {configuredService['name']} for device {deviceConfig['name']} at address {devAddr}")
                devData["connected"]=bleClient.is_connected
                connectCallback()
                break       
            except:
                devData["connected"]=bleClient.is_connected
            await asyncio.sleep(reconnectInterval)
    
    await waitTillConnect()
    
    while 1:
        for configuredServiceUuid in configuredServices.keys():
            service=bleClient.services.get_service(configuredServiceUuid)
            if service is None:
                print(f"Service with UUID {configuredServiceUuid} not found for device {deviceConfig['name']} at address {devAddr}")
                continue
            configuredService=configuredServices[configuredServiceUuid]
            
            for uuid,charConfig  in configuredService["characteristics"].items():
                char= service.get_characteristic(uuid)
                if char is None:
                    #nonExisteant charracteristics, 
                    print(f"Characteristic with UUID {uuid} not found for service {configuredService['name']} in device {deviceConfig['name']} at address {devAddr}")
                    continue
                
                if "read" in char.properties:
                    try:
                        value = await bleClient.read_gatt_char(char.uuid)
                    except:
                        #lost connection to device
                        devData["connected"]=False
                        break
                    loadChar(charConfig,value)
            if not devData["connected"]:
                break
        await waitTillConnect()
            
        await asyncio.sleep(updateInterval)
    
async def mqttCheckTask(topicName:str,topicMessageForm):
    lastSend=0
    while 1:
        doSend=False
        if topicMessageForm["sendOn"]==0:
            print(f"no trigger is set for {topicName}")
        for sendCause in topicMessageForm["sendOn"]:
            if sendCause["type"]=="equation":
                toEval=parse_inp(sendCause["toEval"],devicesData)
                if eval(toEval):
                    doSend=True
                    break
            if sendCause["type"]=="interval":
               if time.time()-lastSend>sendCause["time"]:
                   doSend=True
                   break
        if doSend:
            lastSend=time.time()
            asyncio.run_coroutine_threadsafe(mqttSendTask(topicName,topicMessageForm["payload"]),asyncio.get_running_loop())
        await asyncio.sleep(topicMessageForm["checkInterval"])
       
async def mqttSendTask(topicName,topicMessageFormat):
    def unUpdateVaribles(values,keys):
        val=values
        if len(keys)==3:
            for key in keys[:3]:
                val = val.get(key)
            val["isUpdated"]=False
            val["isChanged"]=False
        
    #method will not check for undefined data
    value=parse_inp(topicMessageFormat,devicesData,"data",unUpdateVaribles)
    if isinstance(value, dict)or isinstance(value, list):
        value=json.dumps(value)
    msg=mqttClient.publish(topicName,value)
    
def mqtt_loop():
    mqttClient.loop_forever()  
    
async def main():
    for devAddr, device in config["devices"].items():
        asyncio.run_coroutine_threadsafe(bleTask(devAddr,device),asyncio.get_running_loop())
        
    if "toSendTo" in config["mqtt"]["topics"].keys():
        for topicName,topicMessageForm in config["mqtt"]["topics"]["toSendTo"].items():
            asyncio.run_coroutine_threadsafe(mqttCheckTask(topicName,topicMessageForm),asyncio.get_running_loop()) 

    while 1:
        await asyncio.sleep(0.5)
mqttThread=threading.Thread(target=mqtt_loop,daemon=True)#)))) костыль

mqttThread.start()
asyncio.run(main())
