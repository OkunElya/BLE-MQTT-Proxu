import asyncio
from bleak import BleakClient, exc
import bleak
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable
import textwrap


# imports used inside value read/write functions

from extensions import format as fmt
from os import listdir
import importlib
import extensions

extension_path = "extensions."
for extension in listdir("extensions"):
    extension = extension.split(".")[0]
    module = importlib.import_module(extension_path + extension)
    setattr(module, extension, extensions)


class Characteristics:
    name: str
    uuid: str
    read_as: Any = None
    write_as: Any = None
    can_read: bool = True
    can_subscribe: bool = False
    can_write: bool = False
    wait_write_response: bool = False

    _parent_link: "Service" = None
    _char_obj: bleak.BleakGATTCharacteristic = None
    value: Any = None
    is_updated: bool = False
    is_changed: bool = False

    def get_value(self):
        self.is_changed = False
        self.is_updated = False
        return self.value

    def getValue(self):
        return self.get_value()

    on_update_callbacks: list = []
    on_change_callbacks: list = []

    def add_on_update_callback(self, coro):
        self.on_update_callbacks.append(coro)

    async def run_on_update_callbacks(self):
        if self.on_update_callbacks:
            for coro in self.on_update_callbacks:
                await coro(self)

    def add_on_change_callback(self, coro):
        self.on_change_callbacks.append(coro)

    async def run_on_change_callbacks(self):
        if self.on_change_callbacks:
            for coro in self.on_change_callbacks:
                await coro(self)

    def __init__(self, data: dict, name: str, logger: logging.Logger):
        self.logger = logger
        required_fields = ["uuid"]
        for field in required_fields:
            if field not in data:
                raise ValueError(
                    f"Missing required field '{field}' in characteristic definition"
                )

        scope = {
            **globals(),
            "self": self,
            "fmt": fmt,
            "extensions": extensions,
            "__name__": __name__,
        }

        if "writeAs" in data.keys():
            write_func_text = data["writeAs"]
            write_func_args = [
                x.strip() for x in write_func_text.split(":")[0].split(",")
            ]
            write_func_body = write_func_text.split(":", 1)[1]

            if "await" in write_func_text:

                asyncFunc = f"""
                async def _write_as({', '.join(write_func_args)}):
                    return {write_func_body}
                """
                asyncFunc = textwrap.dedent(asyncFunc)
                exec(asyncFunc, scope, scope)
                write_as_func = scope["_write_as"]

                async def write_as(x):
                    call_args = dict(
                        {
                            arg_name: {**locals(), **scope}[arg_name]
                            for arg_name in write_func_args
                        }
                    )
                    try:
                        if len(write_func_args) == 1:
                            call_args[write_func_args[0]] = x
                        return await write_as_func(**call_args)
                    except Exception as e:
                        raise RuntimeError(
                            f"Error occurred while executing write_as coro: {e}"
                        )

            else:
                try:
                    write_as_func = eval(f"lambda {write_func_text}", scope, scope)
                except:
                    raise ValueError(
                        f"Failed to evaluate writeAs function: {write_func_text}"
                    )

                async def write_as(x):
                    call_args = dict(
                        {
                            arg_name: {**locals(), **scope}[arg_name]
                            for arg_name in write_func_args
                        }
                    )
                    try:
                        if len(write_func_args) == 1:
                            call_args[write_func_args[0]] = x
                        return write_as_func(**call_args)
                    except Exception as e:
                        raise RuntimeError(
                            f"Error occurred while executing write_as coro: {e}"
                        )

            self.write_as = write_as

        if "readAs" in data.keys():
            read_func_text = data["readAs"]
            read_func_args = [
                x.strip() for x in read_func_text.split(":")[0].split(",")
            ]
            read_func_body = read_func_text.split(":", 1)[1]

            if "await" in read_func_text:

                asyncFunc = f"""
                async def _read_as({', '.join(read_func_args)}):
                    return {read_func_body}
                """
                asyncFunc = textwrap.dedent(asyncFunc)
                exec(asyncFunc, scope, scope)
                read_as_func = scope["_read_as"]

                async def write_as(x):
                    call_args = dict(
                        {
                            arg_name: {**locals(), **scope}[arg_name]
                            for arg_name in read_func_args
                        }
                    )
                    try:
                        if len(read_func_args) == 1:
                            call_args[read_func_args[0]] = x
                        return await read_as_func(**call_args)
                    except Exception as e:
                        raise RuntimeError(
                            f"Error occurred while executing write_as coro: {e}"
                        )

            else:
                try:
                    read_as_func = eval(f"lambda {read_func_text}", scope, scope)
                except:
                    raise ValueError(
                        f"Failed to evaluate readAs function: {read_func_text}"
                    )

                async def read_as(x):
                    call_args = dict(
                        {
                            arg_name: {**locals(), **scope}[arg_name]
                            for arg_name in read_func_args
                        }
                    )
                    try:
                        if len(read_func_args) == 1:
                            call_args[read_func_args[0]] = x
                        return read_as_func(**call_args)
                    except Exception as e:
                        raise RuntimeError(
                            f"Error occurred while executing write_as coro: {e}"
                        )

            self.read_as = read_as

        self.name = name
        self.uuid = data["uuid"]
        self.can_read = self.read_as is not None
        self.can_write = self.write_as is not None
        self.can_subscribe = data.get("subscribe", False)
        self.wait_write_response = data.get("wait_write_response", False)

    async def read(self):
        if not self.can_read:
            raise RuntimeError(
                f"Config is forbidding  read to characteristic {self.name})"
            )
        if self._char_obj is None:
            self.logger.warning(
                f"Characteristic object for {self.name} is not initialized (device not connected yet)."
            )
            return

        if not "read" in self._char_obj.properties:
            self.logger.warning(
                f"Characteristic {self.name} does not support read operation."
            )
            return

        try:
            value = await self._parent_link._parent_link.ble_client.read_gatt_char(
                self._char_obj
            )
        except:
            # lost connection to device
            self.is_connected = False
            return
        await self.load_value(value)

        return self.value

    async def load_value(self, data):
        retValue = None
        try:
            retValue = await self.read_as(data)

        except Exception as e:
            # failed to load value, probably wrong type
            print(
                f"Failed to evaluete characteristic {self.name} from service {self._parent_link.name} in device {self._parent_link._parent_link.name}: {e}\n maybe bad format of loaded varible"
            )
        self.is_updated = True
        self.is_changed = self.value != retValue
        await self.run_on_update_callbacks()
        if self.is_changed:
            await self.run_on_change_callbacks()

        self.value = retValue

        return self.value

    async def write(self, value):
        if not self.can_write:
            raise RuntimeError(
                f"Config is forbidding  write to characteristic {self.name})"
            )

        if self.write_as is not None:
            value = bytes(await self.write_as(value))

        if not "write" in self._char_obj.properties:
            raise PermissionError(
                f"Can't write to characteristic {self.name} (write not allowed)"
            )

        await self._parent_link._parent_link.ble_client.write_gatt_char(
            self._char_obj, value, self.wait_write_response
        )


class Service:
    name: str
    uuid: str
    characteristics: dict[str, Characteristics]

    _service_obj: bleak.BleakGATTServiceCollection = None
    _parent_link: "BleDevice" = None

    def __getattr__(self, name) -> Characteristics:
        if name in self.characteristics.keys():
            return self.characteristics[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    def __init__(self, data: dict, name: str, logger: logging.Logger):
        required_fields = ["uuid", "characteristics"]
        for field in required_fields:
            if field not in data:
                raise ValueError(
                    f"Missing required field '{field}' in service definition"
                )

        self.name = name
        self.uuid = data["uuid"]
        self.characteristics = {}

        for char_name, char_data in data["characteristics"].items():
            char = Characteristics(char_data, char_name, logger)
            char._parent_link = self
            self.characteristics[char_name] = char


@dataclass
class NotificationMessage:
    topic: str
    message: str | list | dict | int | float


class BleDevice:
    name: str
    address: str

    notify_on_first_connect: bool = False
    connect_notification_messages: list[NotificationMessage]
    disconnect_notification_messages: list[NotificationMessage]

    update_interval: float = 10.0
    reconnect_interval: float = 60.0

    services: dict[str, Service]
    secret_key: bytes | None

    _parent_link = "DeviceCollection"

    def __init__(
        self,
        data: dict,
        name: str,
        _parent_link: "DeviceCollection",
        logger: logging.Logger,
    ):
        self.logger = logger
        self._parent_link = _parent_link
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
        self.secret_key = str(data.get("secretKey", None)).encode("utf-8")
        self.services = {}

        for svc_name, svc_data in data["services"].items():
            svc = Service(svc_data, svc_name, self.logger)
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

    def __getattr__(self, name) -> Service:
        if name in self.services.keys():
            return self.services[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    async def send_mqtt_message(self, topic: str, message: str):
        await self._parent_link.send_mqtt_message(topic, message)

    async def device_connect_callback(self):
        self.logger.info(f"restored connection to {self.name}")
        self.is_connected = self.ble_client.is_connected

        if self.notify_on_first_connect and not self.has_connected_previously:
            self.has_connected_previously = True
            return
        for msg in self.connect_notification_messages:
            await self.send_mqtt_message(msg.topic, json.dumps(msg.message))
        pass

    def device_disconnect_callback(self, client):
        self.logger.info(f"lost connection to {self.name}")

        self.is_connected = self.ble_client.is_connected

        async def notify_disconnect():
            for msg in self.disconnect_notification_messages:
                await self.send_mqtt_message(msg.topic, json.dumps(msg.message))

        asyncio.create_task(notify_disconnect())
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
                            if "notify" in char._char_obj.properties:

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
                    await self.device_connect_callback()
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
                try:
                    await char.read()
                except Exception as e:
                    self.logger.error(
                        f"Error reading characteristic '{char.name}' in service '{service.name}' of device '{self.name}': {e}"
                    )


class DeviceCollection:
    devices: dict[str, BleDevice] = {}
    devices_corutines: list = []

    send_mqtt_message_handle: Callable[[str, str], Any] = None

    def __init__(self, config: dict, logger: logging.Logger):
        self.logger = logger
        for device_name, device_config in config.items():
            device = BleDevice(device_config, device_name, self, self.logger)
            self.devices[device_name] = device
            self.devices_corutines.append(device.read_values_loop())

    def set_send_mqtt_message_handle(self, send_mqtt_message_handle):
        self.send_mqtt_message_handle = send_mqtt_message_handle

    def __getattr__(self, name) -> BleDevice:
        if name in self.devices.keys():
            return self.devices[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    async def send_mqtt_message(self, topic: str, message: str):
        if self.send_mqtt_message_handle is not None:
            await self.send_mqtt_message_handle(topic, message)
        else:
            self.logger.warn(
                f"Sending MQTT message to topic failed, uninitialized handle '{topic}': {message}"
            )


if __name__ == "__main__":
    with open("./config.json", "r") as F:
        config = json.load(F)["devices"]

    devices = DeviceCollection(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def testWrtite():
        await asyncio.sleep(10)
        print("Sending!")
        thermostat = devices.Thermostat1
        thermostat: BleDevice
        await thermostat.Thermostat.temperatureSetPoint.write(15)

    pending = DeviceCollection.devices_corutines
    pending.append(testWrtite())
    loop.run_until_complete(asyncio.gather(*pending))
