# BLE-MQTT Proxy Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation & Setup](#installation--setup)
4. [Configuration](#configuration)
5. [Core Components](#core-components)
6. [Extensions](#extensions)
7. [Usage Examples](#usage-examples)
8. [Troubleshooting](#troubleshooting)
9. [API Reference](#api-reference)

---

## Overview

BLE-MQTT Proxy is a Python-based application that bridges Bluetooth Low Energy (BLE) devices with MQTT brokers. It enables bidirectional communication between BLE devices (like smart thermostats, environmental sensors) and MQTT topics, allowing integration with home automation systems and IoT platforms.

### Key Features
- **BLE to MQTT**: Read data from BLE characteristics and publish to MQTT topics
- **MQTT to BLE**: Subscribe to MQTT topics and write values to BLE characteristics
- **Flexible Configuration**: JSON-based configuration with dynamic data transformations
- **Data Formatting**: Built-in support for various data types (int16, int32, float, bytes)
- **HMAC Signing**: Security extension for signed BLE writes
- **Automatic Reconnection**: Handles device disconnections and reconnects automatically
- **Conditional Publishing**: Trigger-based MQTT publishing with intervals, delays, and conditions

### Technology Stack
- **bleak**: BLE communication library
- **aiomqtt**: Async MQTT client
- **Python 3.x**: Async/await architecture using asyncio

---

## Architecture

### System Design

```
┌─────────────────┐
│  BLE Devices    │
│  (Sensors,      │
│   Actuators)    │
└────────┬────────┘
         │ BLE
         │
┌────────▼────────┐
│  BLE-MQTT Proxy │
│                 │
│  ┌───────────┐  │
│  │  Device   │  │
│  │Collection │  │
│  └─────┬─────┘  │
│        │        │
│  ┌─────▼─────┐  │
│  │   MQTT    │  │
│  │ Connector │  │
│  └───────────┘  │
└────────┬────────┘
         │ MQTT
         │
┌────────▼────────┐
│  MQTT Broker    │
│  (Mosquitto,    │
│   HiveMQ, etc)  │
└─────────────────┘
```

### Component Hierarchy

```
DeviceCollection
└── BleDevice (per device)
    └── Service (per GATT service)
        └── Characteristics (per GATT characteristic)

InputTopicCollection
└── InputTopic (per subscribed topic)
    └── InputTopicAction (per action)

OutputTopicCollection
└── OutputTopic (per publish topic)
    ├── TopicPayload
    └── TopicTriggerCollection
        └── TopicTrigger (per trigger condition)
```

---

## Installation & Setup

### Prerequisites
- Python 3.8 or higher
- Bluetooth adapter (USB or built-in)
- Access to MQTT broker

### Installation Steps

1. **Clone the repository**
```bash
git clone <repository-url>
cd BLE-MQTT-Proxy
```

2. **Install dependencies**
```bash
pip install bleak aiomqtt
```

3. **Create configuration file**
```bash
cp config_example.json config.json
```

4. **Edit configuration** (see Configuration section)

5. **Run the application**
```bash
python main.py
```

### System Requirements

- **Linux**: Recommended platform (tested)
- **Windows**: Should work but not extensively tested
- **macOS**: Should work with appropriate Bluetooth permissions

### Known Issues

**Long-term connection issues on Linux:**
- Symptom: BLE connections become unstable after extended periods
- Solution 1: Power cycle the system completely (full shutdown, wait 10s)
- Solution 2: Replug USB Bluetooth adapter
- Solution 3: Reset USB power state

---

## Configuration

The configuration file (`config.json`) uses JSON format and consists of three main sections:

### Configuration Structure

```json
{
  "devices": { ... },
  "mqtt": { ... },
  "logger": { ... }  // optional
}
```

### 1. Logger Configuration (Optional)

The `logger` section is passed directly to Python's `logging.basicConfig()`. If omitted, defaults to `INFO` level.

```json
"logger": {
  "level": "DEBUG",
  "format": "%(asctime)s - %(levelname)s - %(message)s"
}
```

Any valid `logging.basicConfig()` keyword arguments can be used.

---

### 2. Devices Configuration

Each device is defined with:

```json
"devices": {
  "DeviceName": {
    "address": "AA:BB:CC:DD:EE:FF",
    "secretKey": "optional_secret_for_hmac",
    "updateInterval": 5,
    "reconnectInterval": 10,
    "notifyOnLinkStateChange": { ... },
    "services": { ... }
  }
}
```

#### Device Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `address` | string | Yes | BLE MAC address |
| `secretKey` | string | No | Secret key for HMAC signing |
| `updateInterval` | number | No | Seconds between reads (default: 10) |
| `reconnectInterval` | number | No | Seconds between reconnection attempts (default: 60) |
| `notifyOnLinkStateChange` | object | No | MQTT notifications for connect/disconnect |
| `services` | object | Yes | GATT services definition |

#### Connection Notifications

Send MQTT messages when device connection state changes.

```json
"notifyOnLinkStateChange": {
  "notifyOnFirstConnect": false,
  "connectMsg": {
    "topic/path": { "connected": true }
  },
  "disconnectMsg": {
    "topic/path": { "connected": false }
  }
}
```

**Note:** When `notifyOnFirstConnect` is `true`, the connect message is **suppressed** on the initial connection (useful to avoid spurious notifications on startup). When `false`, connect messages are sent on every connection including the first one.

#### Services Configuration

```json
"services": {
  "ServiceName": {
    "uuid": "0000181a-0000-1000-8000-00805f9b34fb",
    "characteristics": {
      "CharacteristicName": {
        "uuid": "00002a6e-0000-1000-8000-00805f9b34fb",
        "readAs": "x : float(fmt.unpack.int16l(x)/100)",
        "writeAs": "x, self : fmt.pack.int16l(int(x*100))",
        "subscribe": true,
        "wait_write_response": false
      }
    }
  }
}
```

#### Characteristic Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `uuid` | string | Yes | Characteristic UUID |
| `readAs` | string | No | Transform function for read data. **Presence enables reading.** |
| `writeAs` | string | No | Transform function for write data. **Presence enables writing.** |
| `subscribe` | boolean | No | Mark for BLE notifications (default: false). Currently used as a flag only. |
| `wait_write_response` | boolean | No | Wait for write response from device (default: false) |

**Important:** A characteristic's read/write capability is determined by the presence of `readAs`/`writeAs` in the config, not by separate enable flags. If you want to read a characteristic, you must provide a `readAs` function (even if it's just `"x : x"` for raw bytes).

#### Read/Write Transform Functions

**Format:** `arg1, arg2, ... : expression`

**Simple example:**
```json
"readAs": "x : int(x[0])"
```

**With self reference:**
```json
"writeAs": "x, self : fmt.pack.int16l(int(x*100))"
```

**Async example:**
```json
"writeAs": "x, self : await extensions.hmac_sign.sign_postfix(self, fmt.pack.int16l(int(x*100)))"
```

**Available in scope:**
- `x`: The raw bytes (for read) or value to write (for write)
- `self`: Reference to the Characteristics object
- `fmt`: Format extension module
- `extensions`: All extension modules
- Any global scope variables

### 3. MQTT Configuration

```json
"mqtt": {
  "serverAddress": "mqtt.example.com:1883",
  "username": "optional_username",
  "password": "optional_password",
  "topics": {
    "toSendTo": { ... },
    "toSubscribeTo": { ... }
  }
}
```

#### MQTT Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `serverAddress` | string | Yes | MQTT broker address with optional port (e.g., `mqtt.example.com:1883`) |
| `username` | string | No | MQTT username |
| `password` | string | No | MQTT password |
| `topics.toSendTo` | object | Yes | Topics to publish to |
| `topics.toSubscribeTo` | object | Yes | Topics to subscribe to |

**Note:** Default port is 1883 if not specified in `serverAddress`.

#### Output Topics (toSendTo)

```json
"toSendTo": {
  "topic/name": {
    "payload": { ... },
    "sendOn": [ ... ]
  }
}
```

**Payload Examples:**

Static payload:
```json
"payload": {
  "'temperature'": 25.5,
  "'humidity'": 60
}
```

Dynamic payload (all strings are evaluated as Python expressions):
```json
"payload": {
  "'temperature'": "Devices.Thermostat1.Thermostat.temperature.getValue()",
  "'humidity'": "Devices.Thermostat1.Thermostat.humidity.getValue()"
}
```

**Important:** In the payload config, **all strings** (both keys and values) are evaluated as Python expressions at send time. To use a literal string as a key, wrap it in quotes like `"'keyName'"`. Non-string values (numbers, booleans, null) are passed through as-is.

#### Triggers (sendOn)

Array of trigger conditions:

```json
"sendOn": [
  {
    "interval": 30,
    "delay": 5,
    "equation": "Devices.Device1.Service1.char1.is_updated",
    "onUpdate": ["Devices.Device1.Service1.char1"]
  }
]
```

**Trigger Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `interval` | number | Minimum seconds between triggers (rate limiting) |
| `delay` | number | Minimum seconds between triggers (functionally similar to interval) |
| `equation` | string | Python expression that must return `True` for trigger to fire |
| `onUpdate` | array | List of characteristic paths - all must have `is_updated=True` |

**Trigger Evaluation Order (all must pass):**
1. **delay** check: Time since last delay-trigger must exceed `delay` seconds
2. **interval** check: Time since last interval-trigger must exceed `interval` seconds  
3. **onUpdate** check: All listed characteristics must have `is_updated == True`
4. **equation** check: Expression must evaluate to `True`

**Trigger Loop Behavior:**
- If `interval` or `delay` is set, trigger runs in a polling loop at the minimum of those intervals
- If only `onUpdate` is set (no interval/delay), trigger fires via callbacks when characteristics update
- If no timing is specified and no `onUpdate`, defaults to 1 second polling interval

#### Input Topics (toSubscribeTo)

```json
"toSubscribeTo": {
  "topic/name": {
    "onReceive": [
      "x : await Devices.Device1.Service1.char1.write(float(x))"
    ]
  }
}
```


**Action Format:** `x : expression`

- `x`: The received message payload (as string)
- Expression: Python code to execute (can be async)

**Examples:**

Write float value:
```json
"x : await Devices.Thermostat1.Thermostat.setPoint.write(float(x))"
```

Write with conversion:
```json
"x : await Devices.Device1.Control.mode.write(['off','heat','cool'].index(x))"
```

Multiple actions:
```json
"onReceive": [
  "x : await Devices.Dev1.Svc1.char1.write(float(x))",
  "x : print(f'Received: {x}')"
]
```

---

## Core Components

### main.py

Entry point of the application. Responsibilities:
- Load and validate configuration
- Initialize logging
- Create MQTT client
- Initialize device and topic collections
- Run main async event loop

**Main execution flow:**
1. Load `config.json`
2. Validate required sections
3. Setup logging
4. Create `DeviceCollection`
5. Connect to MQTT broker
6. Create `InputTopicCollection` and `OutputTopicCollection`
7. Gather all coroutines and run

### device.py

Manages BLE device communication.

#### Classes

**`Characteristics`**
- Represents a GATT characteristic
- Dynamically compiles `readAs`/`writeAs` expressions from config into callable functions
- Supports both sync and async transform functions (detected by presence of `await` keyword)
- Tracks update state with `is_updated` and `is_changed` flags
- Supports callbacks on update/change events
- Properties:
  - `value`: Current transformed value (after `readAs` processing)
  - `is_updated`: `True` after any read, cleared by `get_value()`
  - `is_changed`: `True` if value changed on last read, cleared by `get_value()`
  - `can_read`: `True` if `readAs` was configured
  - `can_write`: `True` if `writeAs` was configured
  - `can_subscribe`: Value of `subscribe` config option

**Methods:**
- `read()`: Read characteristic value from BLE device and process through `readAs`
- `write(value)`: Transform value through `writeAs` and write to BLE device
- `get_value()` / `getValue()`: Get current value and **clear both `is_updated` and `is_changed` flags**
- `add_on_update_callback(coro)`: Register async callback called on every update
- `add_on_change_callback(coro)`: Register async callback called only when value changes

**Flag Behavior:**
- `is_updated`: Set to `True` on every read (including via BLE notify)
- `is_changed`: Set to `True` only when new value differs from previous
- Both flags are cleared when `get_value()`/`getValue()` is called

**`Service`**
- Represents a GATT service
- Contains characteristics
- Property access: `service.characteristic_name`

**`BleDevice`**
- Manages connection to a single BLE device
- Handles automatic reconnection on disconnect
- Runs periodic reading loop for all readable characteristics
- Sends MQTT notifications on connection state changes

**Key Methods:**
- `read_values()`: Read all characteristics with `can_read=True` once
- `read_values_loop()`: Infinite loop: check connection → read values → sleep `updateInterval`
- `check_connection()`: Attempt reconnection loop while disconnected (sleeps `reconnectInterval` between attempts)
- `device_connect_callback()`: Called on successful connection, sends connect notifications
- `device_disconnect_callback()`: Called on disconnect, sends disconnect notifications

**`DeviceCollection`**
- Container for all devices
- Provides device access by name
- Handles MQTT message sending

**Access pattern:**
```python
Devices.DeviceName.ServiceName.CharacteristicName.value
```

### mqtt_connector.py

Manages MQTT communication.

#### Classes

**`TopicPayload`**
- Handles dynamic payload generation
- Recursively evaluates expressions in payload config
- Supports nested objects and arrays

**`TopicTrigger`**
- Evaluates trigger conditions
- Manages intervals, delays, and conditional logic
- Triggers message sending when conditions met

**`TopicTriggerCollection`**
- Manages multiple triggers for a topic
- Runs trigger check loops

**`OutputTopic`**
- Represents an MQTT topic to publish to
- Combines payload and triggers
- Sends messages when triggered

**`OutputTopicCollection`**
- Container for all output topics
- Provides coroutines for all triggers

**`InputTopicAction`**
- Represents a single action to perform on message receipt
- Compiles the action string into a callable (sync or async based on `await` presence)
- Action format: `x : expression` where `x` is always the payload string
- All actions for a topic run concurrently via `asyncio.gather()`

**`InputTopic`**
- Represents an MQTT topic to subscribe to
- Contains multiple actions

**`InputTopicCollection`**
- Container for all input topics
- Handles message routing
- Runs subscription and message loops

---

## Extensions

Extensions are Python modules in the `extensions/` directory that provide additional functionality. All `.py` files in this directory are automatically imported at startup and made available via the `extensions` namespace.

### format.py

Provides data packing/unpacking utilities.

#### pack class

Static methods for packing data to bytes:

```python
fmt.pack.int16l(value)    # 16-bit signed int (little-endian)
fmt.pack.int32l(value)    # 32-bit signed int (little-endian)
fmt.pack.float32l(value)  # 32-bit float (little-endian)
fmt.pack.float16l(value)  # 16-bit float (little-endian)
fmt.pack.byte(value)      # Single byte (0-255)
```

#### unpack class

Static methods for unpacking bytes to values:

```python
fmt.unpack.int16l(data)    # 16-bit signed int (little-endian)
fmt.unpack.int32l(data)    # 32-bit signed int (little-endian)
fmt.unpack.float32l(data)  # 32-bit float (little-endian)
fmt.unpack.float16l(data)  # 16-bit float (little-endian)
fmt.unpack.byte(data)      # Single byte
```

**Usage in config:**
```json
"readAs": "x : float(fmt.unpack.int16l(x)/100)"
```

**Note on `subscribe` flag:** The `subscribe` characteristic option is currently a marker only. The actual BLE notification callback code exists but is commented out (marked `FIXME`). Data is read via polling at the `updateInterval` rate.

### hmac_sign.py

Provides HMAC-SHA256 signing for secure BLE writes.

#### Functions

**`get_salt(self)`**
- Async function to retrieve salt from device
- Requires "Salt" service with "salt" characteristic
- Returns: bytes

**`sign_postfix(self, msg)`**
- Async function to sign a message with HMAC
- Appends HMAC signature to message
- Parameters:
  - `self`: Characteristics instance
  - `msg`: bytes to sign
- Returns: msg + hmac_signature (bytes)

**Requirements:**
- Device must have `secretKey` configured
- Device must have "Salt" service with "salt" characteristic

**Usage in config:**
```json
"writeAs": "x, self : await extensions.hmac_sign.sign_postfix(self, fmt.pack.int16l(int(x*100)))"
```

### Creating Custom Extensions

1. Create a `.py` file in `extensions/` directory
2. Implement your functions
3. Access via `extensions.your_module.function_name()` in config

**Example extension:**

```python
# extensions/my_extension.py

def custom_transform(data):
    """Transform data in some way"""
    return data * 2

async def async_operation(self, value):
    """Perform async operation"""
    # self is the Characteristics instance
    device = self._parent_link._parent_link
    # Your logic here
    return result
```

**Usage:**
```json
"readAs": "x : extensions.my_extension.custom_transform(x)"
```

---

## Usage Examples

### Example 1: Simple Temperature Sensor

**Device Configuration:**
```json
"devices": {
  "TempSensor1": {
    "address": "AA:BB:CC:DD:EE:FF",
    "updateInterval": 10,
    "services": {
      "Environmental": {
        "uuid": "0000181a-0000-1000-8000-00805f9b34fb",
        "characteristics": {
          "temperature": {
            "uuid": "00002a6e-0000-1000-8000-00805f9b34fb",
            "readAs": "x : float(fmt.unpack.int16l(x)/100)"
          }
        }
      }
    }
  }
}
```

**MQTT Output:**
```json
"toSendTo": {
  "sensors/temperature": {
    "payload": "Devices.TempSensor1.Environmental.temperature.getValue()",
    "sendOn": [
      {
        "interval": 30,
        "equation": "Devices.TempSensor1.Environmental.temperature.value is not None"
      }
    ]
  }
}
```

### Example 2: Smart Thermostat (Read & Write)

**Device Configuration:**
```json
"devices": {
  "Thermostat1": {
    "address": "AA:BB:CC:DD:EE:FF",
    "updateInterval": 5,
    "services": {
      "Climate": {
        "uuid": "0000181a-0000-1000-8000-00805f9b34fb",
        "characteristics": {
          "currentTemp": {
            "uuid": "00002a6e-0000-1000-8000-00805f9b34fb",
            "readAs": "x : float(fmt.unpack.int16l(x)/100)",
            "subscribe": true
          },
          "targetTemp": {
            "uuid": "00002a6f-0000-1000-8000-00805f9b34fb",
            "readAs": "x : float(fmt.unpack.int16l(x)/100)",
            "writeAs": "x, self : fmt.pack.int16l(int(x*100))"
          }
        }
      }
    }
  }
}
```

**MQTT Configuration:**
```json
"mqtt": {
  "topics": {
    "toSendTo": {
      "home/thermostat/status": {
        "payload": {
          "'current'": "Devices.Thermostat1.Climate.currentTemp.getValue()",
          "'target'": "Devices.Thermostat1.Climate.targetTemp.getValue()"
        },
        "sendOn": [
          {
            "onUpdate": ["Devices.Thermostat1.Climate.currentTemp"]
          }
        ]
      }
    },
    "toSubscribeTo": {
      "home/thermostat/setpoint": {
        "onReceive": [
          "x : await Devices.Thermostat1.Climate.targetTemp.write(float(x))"
        ]
      }
    }
  }
}
```

### Example 3: Conditional Publishing

Publish only when temperature exceeds threshold:

```json
"toSendTo": {
  "alerts/high-temperature": {
    "payload": {
      "'temperature'": "Devices.TempSensor1.Environmental.temperature.getValue()",
      "'alert'": "'HIGH TEMPERATURE'"
    },
    "sendOn": [
      {
        "equation": "Devices.TempSensor1.Environmental.temperature.value > 30.0",
        "interval": 60
      }
    ]
  }
}
```

### Example 4: Multiple Actions on Receive

```json
"toSubscribeTo": {
  "control/sync-all": {
    "onReceive": [
      "x : await Devices.Device1.Service1.char1.write(float(x))",
      "x : await Devices.Device2.Service1.char1.write(float(x))",
      "x : print(f'Synced all devices to: {x}')"
    ]
  }
}
```

### Example 5: With HMAC Signing

**Device Configuration:**
```json
"devices": {
  "SecureDevice": {
    "address": "AA:BB:CC:DD:EE:FF",
    "secretKey": "my-secret-key",
    "services": {
      "Salt": {
        "uuid": "0000181a-0000-1000-8000-00805f9b34fb",
        "characteristics": {
          "salt": {
            "uuid": "8e87024a-52fd-4d54-9891-27b248a6a0d8",
            "readAs": "x : bytes(x)",
            "subscribe": true
          }
        }
      },
      "Control": {
        "uuid": "0000181b-0000-1000-8000-00805f9b34fb",
        "characteristics": {
          "value": {
            "uuid": "00002a6e-0000-1000-8000-00805f9b34fb",
            "writeAs": "x, self : await extensions.hmac_sign.sign_postfix(self, fmt.pack.int16l(int(x)))"
          }
        }
      }
    }
  }
}
```

---

## Troubleshooting

### Common Issues

#### 1. Connection Failures

**Symptom:** Device won't connect or constantly reconnects

**Solutions:**
- Verify MAC address is correct
- Ensure device is powered on and in range
- Check Bluetooth adapter is working: `hciconfig`
- Reset Bluetooth: `sudo systemctl restart bluetooth`
- Check for interference from other devices

#### 2. Characteristic Not Found

**Symptom:** Warning about characteristic UUID not found

**Solutions:**
- Verify UUID is correct
- Use BLE scanner app to discover correct UUIDs
- Check service UUID is correct
- Ensure device firmware is compatible

#### 3. Read/Write Transformation Errors

**Symptom:** Failed to evaluate characteristic error

**Solutions:**
- Check syntax of readAs/writeAs expressions
- Verify data length matches expected format
- Add error handling: `"readAs": "x : float(fmt.unpack.int16l(x)) if len(x) == 2 else None"`
- Check available functions in scope

#### 4. MQTT Connection Issues

**Symptom:** Can't connect to MQTT broker

**Solutions:**
- Verify server address and port
- Check username/password
- Test with MQTT client: `mosquitto_sub -h <host> -t test`
- Check firewall rules
- Verify broker is running

#### 5. Triggers Not Firing

**Symptom:** No messages published despite data updates

**Solutions:**
- Check equation syntax
- Verify characteristic paths are correct
- Add logging to see trigger evaluation
- Check interval isn't too long
- Ensure is_updated flag logic matches expectations

#### 6. Long-term Stability Issues

**Symptom:** Application becomes unstable after hours/days

**Solutions:**
- Complete power cycle (shutdown, wait, restart)
- Replug Bluetooth adapter
- Add memory monitoring
- Check for memory leaks in custom extensions
- Update bleak library: `pip install --upgrade bleak`

### Debug Mode

Enable debug logging in config:

```json
"logger": {
  "level": "DEBUG"
}
```

### Testing Individual Components

**Test BLE connection:**
```python
python -c "
import asyncio
from bleak import BleakScanner

async def scan():
    devices = await BleakScanner.discover()
    for d in devices:
        print(f'{d.name}: {d.address}')

asyncio.run(scan())
"
```

**Test MQTT connection:**
```bash
mosquitto_pub -h <broker> -u <user> -P <pass> -t test -m "hello"
```

---

## API Reference

### DeviceCollection

```python
devices = DeviceCollection(config: dict, logger: logging.Logger)
```

**Attributes:**
- `devices`: Dict mapping device names to BleDevice instances
- `devices_corutines`: List of `read_values_loop()` coroutines for all devices

**Methods:**
- `set_send_mqtt_message_handle(handle)`: Set the async function used to publish MQTT messages
- `get_corutines()`: Returns `devices_corutines` list
- `send_mqtt_message(topic, message)`: Async method to send MQTT message via configured handle

**Attribute Access:**
```python
devices.DeviceName  # Returns BleDevice instance via __getattr__
```

### BleDevice

**Attributes:**
- `name`: Device name (from config key)
- `address`: BLE MAC address
- `is_connected`: Current connection state boolean
- `has_connected_previously`: Tracks if device ever connected (for `notifyOnFirstConnect` logic)
- `services`: Dict mapping service names to Service instances
- `secret_key`: Bytes of secret key (for HMAC), or `b'None'` if not configured
- `update_interval`: Seconds between read cycles
- `reconnect_interval`: Seconds between reconnection attempts
- `ble_client`: The underlying BleakClient instance

**Key Methods:**
- `read_values()`: Read all readable characteristics
- `read_values_loop()`: Main coroutine - loops forever reading values
- `check_connection()`: Reconnection loop - runs until connected
- `send_mqtt_message(topic, message)`: Send message via parent DeviceCollection

**Attribute Access:**
```python
device.ServiceName  # Returns Service instance via __getattr__
```

### Service

**Attributes:**
- `name`: Service name (from config key)
- `uuid`: Service UUID string
- `characteristics`: Dict mapping characteristic names to Characteristics instances

**Attribute Access:**
```python
service.characteristic_name  # Returns Characteristics instance via __getattr__
```

### Characteristics

**Attributes:**
- `name`: Characteristic name (from config key)
- `uuid`: Characteristic UUID string
- `value`: Last read value (after `readAs` transformation)
- `is_updated`: `True` after any `load_value()` call, cleared by `get_value()`
- `is_changed`: `True` if value changed from previous, cleared by `get_value()`
- `can_read`: `True` if `readAs` function exists
- `can_write`: `True` if `writeAs` function exists
- `can_subscribe`: Boolean from config `subscribe` field
- `wait_write_response`: Boolean from config

**Methods:**
- `read()`: Read raw bytes from BLE, process through `readAs`, update flags, run callbacks
- `write(value)`: Transform through `writeAs`, write to BLE characteristic
- `get_value()` / `getValue()`: Return current `value` and clear `is_updated`/`is_changed` flags
- `load_value(data)`: Process raw bytes through `readAs`, set flags, run callbacks
- `add_on_update_callback(coro)`: Register async callback for any update
- `add_on_change_callback(coro)`: Register async callback for value changes

### InputTopicCollection

```python
topics = InputTopicCollection(
    config: dict,
    client: aiomqtt.Client,
    local_context: dict,
    logger: logging.Logger
)
```

**Methods:**
- `run_subcribe()`: Subscribe to all topics (coroutine)
- `run_routing()`: Route incoming messages (coroutine)

### OutputTopicCollection

```python
topics = OutputTopicCollection(
    config: dict,
    client: aiomqtt.Client,
    local_context: dict,
    logger: logging.Logger
)
```

**Methods:**
- `get_coroutines()`: Get all trigger coroutines

### Context Variables

Available in expressions:

**In `readAs`/`writeAs` (characteristics):**
- `x`: Raw bytes (for read) or value to transform (for write)
- `self`: The Characteristics instance (access parent via `self._parent_link._parent_link` for BleDevice)
- `fmt`: Format extension module
- `extensions`: All extension modules

**In `payload` and `equation` (MQTT output topics):**
- `Devices`: DeviceCollection instance (access via `Devices.DeviceName.ServiceName.CharName`)
- `client`: aiomqtt.Client instance
- All Python globals

**In `onReceive` actions (MQTT input topics):**
- `x`: Message payload as string
- `Devices`: DeviceCollection instance
- `client`: aiomqtt.Client instance
- All Python globals

---

## Security Considerations
I hope for abscence of ignorance and basic intuition from users of this software


## Performance Optimization

### 1. Update Intervals
- Set appropriate `updateInterval` per device (5-60 seconds typical)
- Longer intervals reduce BLE traffic and power consumption
- Shorter intervals provide more real-time data

### 2. Trigger Optimization
- Use `onUpdate` instead of polling with `interval` when possible
- Combine related characteristics in single message
- Use `interval` to rate-limit high-frequency updates

### 3. Connection Management
- Set reasonable `reconnectInterval` (10-60 seconds)
- Monitor connection quality

### 4. MQTT QoS
- Default QoS 0 (fire and forget) for most sensor data
- Consider QoS 1 for important commands
- Note: Current implementation uses default QoS
---

## Future Enhancements

Potential improvements:
- [ ] BLE notification callbacks (code exists but is commented out with `FIXME`)
- [ ] MQTT TLS support
- [ ] Configuration validation on startup
- [ ] Web UI for configuration
- [ ] Docker container support
- [ ] Multi-broker support
- [ ] Persistent storage for device state
- [ ] Metrics and monitoring endpoints
- [ ] Home Assistant auto-discovery
---

