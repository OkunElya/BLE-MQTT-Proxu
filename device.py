import extensions

import asyncio
import threading
from bleak import BleakClient, exc
import bleak
import struct
import json
import logging

from dataclasses import dataclass, fields
from typing import Any


@dataclass
class Characteristics:
    name: str
    uuid: str
    read_as: function | None
    write_as: function | None
    can_read: bool = True
    can_subscribe: bool = False
    can_write: bool = False
    wait_write_response: bool = False
    hmac_key: str = None
    
    _parent_link: "Service" = None
    _char_obj: bleak.BleakGATTCharacteristic = None
    value: Any = None
    is_updated: bool = False
    is_changed: bool = False

    @classmethod
    def from_config(cls, data: dict, name: str):
        required_fields = ["uuid"]
        for field in required_fields:
            if field not in data:
                raise ValueError(
                    f"Missing required field '{field}' in characteristic definition"
                )

        read_as_func = None
        if "read_as" in data.keys():
            try:
                func = eval(f"lambda {data['read_as']}", locals() + globals())
            except:
                raise ValueError(
                    f"Failed to evaluate read_as function: {data['read_as']}"
                )

            async def read_as(x):
                try:
                    return func(x)
                except Exception as e:
                    raise RuntimeError(
                        f"Error occurred while executing read_as function: {e}"
                    )

            read_as_func = read_as

        write_as_func = None
        if "write_as" in data.keys():
            try:
                func = eval(f"lambda {data['write_as']}", locals() | globals())
            except:
                raise ValueError(
                    f"Failed to evaluate write_as function: {data['write_as']}"
                )

            async def write_as(x):
                try:
                    return func(x)
                except Exception as e:
                    raise RuntimeError(
                        f"Error occurred while executing write_as function: {e}"
                    )
            write_as_func = write_as

        return cls(
            name=name,
            uuid=data["uuid"],
            read_as=read_as_func,
            write_as=write_as_func,
            can_read=read_as_func is not None,
            can_subscribe=data.get("subscribe", False),
            wait_write_response=data.get("wait_write_response", False),
            hmac_key=data.get("hmac_key", None),
            can_write=write_as_func is not None,
        )
        
    async def read(self):
        if not self.can_read:
            raise RuntimeError(f"Config is forbidding  read to characteristic {self.name})")
            
        if not "read" in self._char_obj.properties:
            self.logger.warning(f"Characteristic {self.name} does not support read operation.")
            return
        
        try:
            value = await self._parent_link._parent_link.ble_client.read_gatt_char(self.uuid)
        except:
            # lost connection to device
            self.is_connected = False
            return
        await self.load_value(value)
        
        return self.value

    async def load_value(self,data):
        value = None
        try:
           value = await self.read_as(data)

        except Exception as e:
            # failed to load value, probably wrong type
            print(
                f"Failed to evaluete characteristic {self.name} from service {self._parent_link.name} in device {self._parent_link._parent_link.name}: {e}\n maybe bad format of loaded varible"
            )
        self.is_updated = True
        self.is_changed = self.value != value
        self.value = value
        
        return self.value
        
    async def write(self, value):
        if not self.can_write:
            raise RuntimeError(f"Config is forbidding  write to characteristic {self.name})")
        
        if self.write_as is not None:
            value = bytes(await self.write_as(value))
            
        if not "write" in self._char_obj.properties:
            raise PermissionError(f"Can't write to characteristic {self.name} (write not allowed)")
    
        self._parent_link._parent_link.ble_client.write_gatt_char(self._char_obj,value,self.wait_write_response)    
        
@dataclass
class Service:
    name: str
    uuid: str
    characteristics: dict[str, Characteristics]

    _service_obj: bleak.BleakGATTServiceCollection = None
    _parent_link: "BleDevice" = None

    @classmethod
    def from_config(cls, data: dict, name: str):
        required_fields = ["uuid", "characteristics"]
        for field in required_fields:
            if field not in data:
                raise ValueError(
                    f"Missing required field '{field}' in service definition"
                )

        service = cls(name=name, uuid=data["uuid"], characteristics={})

        for char_name, char_data in data["characteristics"].items():
            char = Characteristics.from_config(char_data, char_name)
            char._parent_link = service
            service.characteristics[char_name] = char

        return service


@dataclass
class NotificationMessage:
    topic: str
    message: Any[str, list, dict, int, float]


class BleDevice:
    name: str
    address: str

    notify_on_first_connect: bool = False
    connect_notification_messages: list[NotificationMessage]
    disconnect_notification_messages: list[NotificationMessage]

    update_interval: float = 10.0
    reconnect_interval: float = 60.0

    services: dict[str, Service]

    def __init__(
        self, data: dict, name: str, logger: logging.Logger = logging.getLogger()
    ):
        required_fields = ["address", "services"]
        for field in required_fields:
            if field not in data:
                raise ValueError(
                    f"Missing required field '{field}' in device definition"
                )

        notify_on_first_connect = False
        connect_msgs = []
        disconnect_msgs = []

        notify_cfg = data.get("notifyOnLinkStateChange", {})
        if notify_cfg:
            notify_on_first_connect = notify_cfg.get("notifyOnFirstConnect", False)
            connect_msg_dict = notify_cfg.get("connectMsg", {})
            disconnect_msg_dict = notify_cfg.get("disconnectMsg", {})
            for topic, msg in connect_msg_dict.items():
                connect_msgs.append(NotificationMessage(topic=topic, message=msg))
            for topic, msg in disconnect_msg_dict.items():
                disconnect_msgs.append(NotificationMessage(topic=topic, message=msg))

        self.name = name
        self.address = data["address"]
        self.notify_on_first_connect = notify_on_first_connect
        self.connect_notification_messages = connect_msgs
        self.disconnect_notification_messages = disconnect_msgs
        self.update_interval = float(data.get("updateInterval", 10.0))
        self.reconnect_interval = float(data.get("reconnectInterval", 60.0))
        self.services = {}

        for svc_name, svc_data in data["services"].items():
            svc = Service.from_config(svc_data, svc_name)
            svc._parent_link = self
            self.services[svc_name] = svc

        self.logger = logger

        self.is_connected = False
        self.has_connected_previously = False

        self.ble_client = BleakClient(
            self.address,
            self.device_disconnect_callback,
            winrt=dict(use_cached_services=False),
        )

    def send_mqtt_message(self, topic: str, message: str):
        self.logger.info(f"Sending MQTT message to topic '{topic}': {message}")
        ...  # TODO

    def device_connect_callback(self):
        self.logger.info(f"restored connection to {self.name}")
        self.is_connected = self.ble_client.is_connected

        if self.notify_on_first_connect and not self.has_connected_previously:
            self.has_connected_previously = True
            return
        for msg in self.connect_notification_messages:
            self.send_mqtt_message(msg.topic, json.dumps(msg.message))
        pass

    def device_disconnect_callback(self, client):
        self.logger.info(f"lost connection to {self.name}")

        self.is_connected = self.ble_client.is_connected
        for msg in self.disconnect_notification_messages:
            self.send_mqtt_message(msg.topic, json.dumps(msg.message))
        pass

    async def check_connection(self):
        while not self.is_connected:
            try:
                await self.ble_client.disconnect()
                await self.ble_client.connect()
                for service_name, service in self.services.items():
                    service._service_obj = self.ble_client.services.get_service(
                        service.uuid
                    )
                    if service is None:
                        self.logger.warning(
                            f"Service with UUID {service.uid} not found for device {self.name} "
                        )
                        continue

                    for char_name, char in service.characteristics.items():
                        char._char_obj = service._service_obj.get_characteristic(
                            char.uuid
                        )
                        if char is None:
                            self.logger.warning(
                                f"Characteristic with UUID {char_name} not found in service {service_name} in device {self.name}"
                            )
                            continue
                        if char.can_subscribe:
                            if "notify" in char.properties:

                                async def notyfyCallback(
                                    char_obj: bleak.BleakGATTCharacteristic,
                                    data: bytearray,
                                ):
                                    self.loadData(char, data, isNotification=True)

                                try:
                                    # await self.ble_client.start_notify(
                                    #     char._char_obj, notyfyCallback
                                    # )  # idk how to use it FIXME
                                    ...
                                except exc.BleakError:
                                    self.logger.warning(
                                        f"Failed to set notify for characteristic {char_name} in service {service_name} for device {self.name}"
                                    )
                                    
                self.is_connected = self.ble_client.is_connected
                if self.is_connected:
                    self.device_connect_callback()
                    break
            except:
                self.is_connected = self.ble_client.is_connected
            await asyncio.sleep(self.reconnect_interval)

    async def read_values_loop(self):
        while 1:
            await self.check_connection()
            await self.read_values()
            await asyncio.sleep(self.update_interval)
            
    async def read_values(self):
        for service in self.services.values():
            for char in service.characteristics.values():
                await char.read()  

       
