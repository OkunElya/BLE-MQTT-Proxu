import asyncio
import aiomqtt
import json
import random


with open("config.json") as F:
    config = json.load(F)
if not isinstance(config, dict):
    raise TypeError("Config file must contain a JSON object (dict)")



client_id = f"BLE proxy-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))}",
mqtt_server_address = config.get
mqtt_server_hostname = config["mqtt"]["serverAddress"].split(":")[0]
mqtt_port = 1883
if ":" in config["mqtt"]["serverAddress"]:
    mqtt_port = int(config["mqtt"]["serverAddress"].split(":")[-1])
