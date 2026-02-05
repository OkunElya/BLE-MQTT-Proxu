import asyncio
import json
import random
import logging
from device import DeviceCollection
from mqtt_connector import InputTopicCollection, OutputTopicCollection
import aiomqtt


with open("config.json") as F:
    config = json.load(F)
    
if not isinstance(config, dict):
    raise TypeError("Config file must contain a JSON object (dict)")
#===MQTT PART ===#
if "mqtt" not in config or not isinstance(config["mqtt"], dict):
    raise KeyError("Config file must contain an 'mqtt' section as a dictionary")

client_id = f"BLE proxy-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))}",
mqtt_server_address =config["mqtt"].get("serverAddress", None)
if mqtt_server_address is None:
    raise ValueError("MQTT server address must be specified in the config file")

mqtt_server_hostname = mqtt_server_address.split(":")[0]
mqtt_server_port = 1883
if ":" in mqtt_server_address:
    mqtt_port = int(mqtt_server_address.split(":")[-1])

username = config["mqtt"].get("username", None)
password = config["mqtt"].get("password", None)

if "topics" not in config["mqtt"] or not isinstance(config["mqtt"]["topics"], dict):
    raise KeyError("Config file must contain an 'mqtt.topics' section as a dictionary")

mqtt_topics = config["mqtt"]["topics"]

if "toSubscribeTo" not in mqtt_topics:
    raise KeyError("Config file must contain 'mqtt.topics.toSubscribeTo' key")
to_subscribe_to = mqtt_topics["toSubscribeTo"]

if "toSendTo" not in mqtt_topics:
    raise KeyError("Config file must contain 'mqtt.topics.toSendTo' key")
to_send_to = mqtt_topics["toSendTo"]


if "logger" in config and isinstance(config["logger"], dict):
    logging.basicConfig(**config["logger"])
else:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

if "devices" not in config or not isinstance(config["devices"], dict):
    raise KeyError("Config file must contain a 'devices' section as a dictionary")
devices_config = config["devices"]


async def main():
    
    #add Devices to context 
    try:
        Devices = DeviceCollection(devices_config,logger)
        
        async with aiomqtt.Client(
            hostname=mqtt_server_hostname,
            port=mqtt_server_port,
            username=username,
            password=password,
            # identifier=client_id,
        ) as client:
            Devices.set_send_mqtt_message_handle(client.publish)
            
            ctx = {**locals(), **globals()}
            all_tasks = []
            output_topics = OutputTopicCollection(to_send_to,client,ctx,logger)
            input_topics = InputTopicCollection(to_subscribe_to,client,ctx,logger)
                
                
            all_tasks = output_topics.get_coroutines()
            all_tasks += Devices.get_corutines()
            all_tasks += [input_topics.run_routing(),input_topics.run_subcribe()]
            await asyncio.gather(*(task for task in all_tasks))
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(asyncio.gather(main()))
