import asyncio
import asyncio_mqtt
import json
import random


with open("config.json") as F:
    config = json.load(F)

client_id = f"BLE proxy-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))}",

mqtt_server_address = config["mqtt"]["serverAddress"].split(":")[0]
mqtt_port = 1883
if ":" in config["mqtt"]["serverAddress"]:
    mqtt_port = int(config["mqtt"]["serverAddress"].split(":")[-1])

