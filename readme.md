### Bluetooth Low Energy to MQTT PROXY
This project constains little python script that uses bleak and paho.matt to forward bluetooth data from devices like smart thermometers and more to uor mqtt server with specified data format
For now it supports only one way proxying (BLE -> MQTT) but i might add support for another direction in not so distant future
The configuration is pretty flexible which also could be an attack vector (don't use someone's config without readig it thoroughly)

## Running it
1. attach bluetooth modem
2. install bleak and paho-mqtt
3. create configuration.json in the same dirrectory as the script. (use config example as the  reference)
4. run main.py

There might be some issues with long term connections on the linux platfoem (also on the windows, but i've not tested it there) (rebooting won't help, so `sudo shutdown now` it unplug frompower and wait 10 sec, if your modem is unplagable , just repluging it or tinkering with the usp power state might just fix it for you)