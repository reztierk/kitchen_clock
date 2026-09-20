import gc
import json
import time
from secrets import secrets  # type: ignore

import adafruit_connection_manager
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import microcontroller

gc.collect()  # compact before clock.parse pulls in displayio/adafruit_display_shapes

import clock.dog as Dog
import clock.parse as Parse
import clock.reset_log as ResetLog
import clock.shared as Shared
import clock.stats as Stats
import clock.wifi as Wifi

mqtt_subs = {
    f"{Shared.topic_prefix}/ping": Parse.ping,
    f"{Shared.topic_prefix}/brightness": Parse.brightness,
    f"{Shared.topic_prefix}/neopixel": Parse.neopixel,
    f"{Shared.topic_prefix}/blinkrate": Parse.blinkrate,
    f"{Shared.topic_prefix}/msg": Parse.msg_message,
    f"{Shared.topic_prefix}/img": Parse.img,
    "/aio/local_time": Parse.localtime_message,
    "homeassistant/local_time": Parse.localtime_message,
    f"{Shared.topic_prefix}/time": Parse.localtime_message,
    "/sensor/temperature_outside": Parse.temperature_outside,
}


def getMQTTClient():
    # Initialize MQTT interface with the esp interface
    socket_pool = adafruit_connection_manager.get_radio_socketpool(Shared.esp)

    # Set up a MiniMQTT Client
    client = MQTT.MQTT(
        broker=secrets["broker"],
        port=secrets.get("broker_port") or 1883,
        username=secrets["broker_user"],
        password=secrets["broker_pass"],
        socket_pool=socket_pool,
        socket_timeout=1.0,
        connect_retries=1,
    )

    # Connect callback handlers to client
    client.on_connect = connect
    client.on_disconnect = disconnected
    client.on_subscribe = subscribe
    client.on_publish = publish
    client.on_message = message

    return client


def setup():
    Shared.client = getMQTTClient()

    print(f"Attempting to MQTT connect to {Shared.client.broker}")
    try:
        Shared.client.connect()
        Stats.inc_counter("connect")
    except Exception as e:
        print(f"Unable to connect to MQTT broker {Shared.client.broker} during setup: {e}")
        print("Continuing boot; will retry connecting in background.")
        Stats.inc_counter("fail_initial_connect")


# ------------- MQTT Functions ------------- #


# Define callback methods which are called when events occur
# pylint: disable=unused-argument, redefined-outer-name
def connect(client, userdata, flags, rc):
    # This function will be called when the client is connected
    # successfully to the broker.
    print("Connected to MQTT Broker!", end=" ")
    print(f"mqtt_msg: {client.mqtt_msg}", end=" ")
    print(f"Flags: {flags} RC: {rc}")
    for mqtt_sub in mqtt_subs:
        print(f"Subscribing to {mqtt_sub}")
        client.subscribe(mqtt_sub)
    Stats.inc_counter("connect")

    # Publish reset reason and recent restart history to Home Assistant immediately upon connect
    try:
        reset_reason_val = str(getattr(Shared, "reset_reason", "unknown")).replace("microcontroller.ResetReason.", "")
        client.publish(f"{Shared.topic_prefix}/last_reset_reason", reset_reason_val, retain=True)
        recent_resets = ResetLog.get_recent_resets()
        client.publish(f"{Shared.topic_prefix}/restart_history", json.dumps(recent_resets), retain=True)
        print(f"Reported reset reason ({reset_reason_val}) to MQTT")
    except Exception as e:
        print(f"Error publishing reset reason: {e}")

    # Trigger local time refresh immediately upon connection
    try:
        print("Requesting time sync...")
        client.publish("homeassistant/local_time/refresh", "refresh")
        client.publish(f"{Shared.topic_prefix}/time/refresh", "refresh")
    except Exception as e:
        print(f"Error requesting time refresh: {e}")


last_reconnect_attempt = -10  # allow an immediate first reconnect attempt


def reconnect():
    global last_reconnect_attempt
    now = time.monotonic()
    if now - last_reconnect_attempt < 10:
        return False
    last_reconnect_attempt = now

    Dog.feed()
    if not Wifi.ensure_connected():
        return False

    print("Attempting MQTT reconnect...")
    Dog.feed()
    try:
        Shared.client.disconnect()
    except Exception:
        pass

    try:
        Dog.feed()
        Shared.client.connect()
        Dog.feed()
        print("MQTT reconnected successfully!")
        Stats.inc_counter("reconnect")
        return True
    except Exception as err:
        Dog.feed()
        print(f"MQTT reconnect failed: {err}")
        Stats.inc_counter("fail_reconnect")
        return False


def disconnected(_client, _userdata, rc):
    # This method is called when the client is disconnected
    print(f"Disconnected from MQTT Broker! RC: {rc}")
    Stats.inc_counter("disconnected")


def subscribe(_client, _userdata, topic, granted_qos):
    # This method is called when the client subscribes to a new feed
    print(f"Subscribed to {topic} with QOS level {granted_qos}")
    Stats.inc_counter("subscribe")


def publish(_client, userdata, topic, pid):
    # This method is called when the client publishes data to a feed
    print(f"Published to {topic} with PID {pid}")
    Stats.inc_counter("publish")


def message(_client, topic, message):
    # This method is called when the subscribed feed has a new value
    if topic in mqtt_subs:
        mqtt_subs[topic](topic, message)
