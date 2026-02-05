# BLE-MQTT Proxy

Bridges Bluetooth Low Energy devices to MQTT. Supports bidirectional communication: read BLE characteristics -> publish to MQTT, subscribe to MQTT <- write to BLE.

## Features
- Flexible JSON configuration with dynamic data transformations
- Automatic reconnection handling
- Configurable triggers (interval, conditions, on-update)
- Extensible via Python modules (`extensions/`)

## Quick Start

```bash
pip install bleak aiomqtt
cp config_example.json config.json
# Edit config.json with your devices and MQTT broker
python main.py
```

## Configuration

See `config_example.json` and `DOCUMENTATION.md` for detailed configuration reference.

**Security Note:** Config allows arbitrary Python code execution. Only use trusted configurations.

## Known Issues

Long-term BLE stability issues on Linux may require power cycling the Bluetooth adapter. Please create an issue or contribute if you know how to fix this
