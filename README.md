# kitchen_clock

#### CircuitPython based project for Adafruit MatrixPortal controlled via MQTT

This repo is a snapshot of all files and python script
needed to have time and messages displayed on a MatrixPortal.
This project uses an MQTT broker for obtaining the time as well as
displaying custom messages. There is also support for using
[Bitmap Pixel Art and Animation](https://learn.adafruit.com/pixel-art-matrix-display).
If you rather use a PyPortal, check out the [pyportal_station](https://github.com/flavio-fernandes/pyportal_station)
project.

[![Kitchen Clock Show-and-Tell](https://live.staticflickr.com/65535/52251360538_e63c498a2d_z.jpg)](https://youtu.be/DB5dh_nL3hY?t=1666)

### Libraries

Designed for **CircuitPython 10.3.1** on the MatrixPortal M4 (see boot_out.txt for the
firmware currently in use). The following libraries are **frozen into the 10.3.1 firmware**
for this board, so they are intentionally not bundled in [lib/](lib):

```
adafruit_connection_manager, adafruit_esp32spi, adafruit_portalbase,
adafruit_requests, neopixel
```

The libraries in [lib/](lib) come from the
[10.x mpy bundle](https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/latest)
(bundle release 20260919):

```
adafruit_bitmap_font==2.4.3
adafruit_bus_device==5.2.17
adafruit_display_shapes==2.10.6
adafruit_display_text==5.0.5
adafruit_matrixportal==3.2.12
adafruit_minimqtt==8.1.0
```

Note: the code reaches into MatrixPortal/PortalBase internals (`_text`, `_scrolling_index`,
`_get_next_scrollable_text_index`); this was validated against matrixportal 3.2.12 with
portalbase 3.5.2 (frozen). If you upgrade those libraries, re-test text positioning and
scrolling.

### Hardware

The key components are the [Adafruit Matrix Portal](https://www.adafruit.com/product/4745) and the
[64x32 RGB LED Matrix - 6mm pitch](https://www.adafruit.com/product/2276) from Adafruit. 

Plugging the MatrixPortal directly on the HUB 75 socket made it stick out and that was not
well suited for this project. I had to come up with an adaptor.
Take a look at [thingiverse 4850550](https://www.thingiverse.com/thing:4850550) for info on
the brackets I made and printed for the clock, as well as the accessories used.

### secrets.py

Make sure to create a file called secrets.py to include info on the wifi as well as the MQTT
broker you will connect to. Use [**secrets.py.sample**](https://github.com/flavio-fernandes/kitchen_clock/blob/main/secrets.py.sample)
as reference.


### Removing _all_ files from CIRCUITPY drive

```
# NOTE: Do not do this before backing up all files!!!
>>> import storage ; storage.erase_filesystem()
```

### Copying files from cloned repo to CIRCUITPY drive
```
# First, get to the REPL prompt so the board will not auto-restart as
# you copy files into it

# Assuming that MatrixPortal is mounted under /Volumes/CIRCUITPY
$  cd ${THIS_REPO_DIR}
$  [ -d /Volumes/CIRCUITPY/ ] && \
   rm -rf /Volumes/CIRCUITPY/* && \
   (tar czf - *) | ( cd /Volumes/CIRCUITPY ; tar xzvf - ) && \
   echo ok || echo not_okay
```

### Time

Once MQTT is connected, this code expects an MQTT message to be sent
to it -- at least once -- so it can learn what the local time is.
See [**localtime_message()**](https://github.com/flavio-fernandes/kitchen_clock/blob/main/clock/parse.py)
for an example of what that looks like

```text
topic: /aio/local_time  payload: 2021-05-18 23:23:36.339 015 5 -0500 EST
```

### Topics

These are the MQTT topics you can publish to the clock:

```python
mqtt_topic = secrets.get("topic_prefix") or "/matrixportal"
mqtt_pub_status = f"{mqtt_topic}/status"

mqtt_subs = {
    f"{mqtt_topic}/ping": _parse_ping,
    f"{mqtt_topic}/brightness": _parse_brightness,
    f"{mqtt_topic}/neopixel": _parse_neopixel,
    f"{mqtt_topic}/blinkrate": _parse_blinkrate,
    f"{mqtt_topic}/msg": _parse_msg_message,
    f"{mqtt_topic}/img": _parse_img,
    "/aio/local_time": _parse_localtime_message,
    "/sensor/temperature_outside": _parse_temperature_outside,
}
```

Example commands

```bash
PREFIX='matrix_portal'
MQTT=192.168.10.238

# Subscribing to status messages
mosquitto_sub -F '@Y-@m-@dT@H:@M:@S@z : %q : %t : %p' -h $MQTT -t "${PREFIX}/status"

# Request general info
mosquitto_pub -h $MQTT -t "${PREFIX}/ping" -r -n

# Turn screen on/off
mosquitto_pub -h $MQTT -t "${PREFIX}/brightness" -m on
mosquitto_pub -h $MQTT -t "${PREFIX}/brightness" -m off

# Neopixel control
mosquitto_pub -h $MQTT -t "${PREFIX}/neopixel" -m 0        ; # off
mosquitto_pub -h $MQTT -t "${PREFIX}/neopixel" -m 0xff     ; # blue
mosquitto_pub -h $MQTT -t "${PREFIX}/neopixel" -m 0xff00   ; # green
mosquitto_pub -h $MQTT -t "${PREFIX}/neopixel" -m 0xff0000 ; # red

# On board led blink
mosquitto_pub -h $MQTT -t "${PREFIX}/blinkrate" -m 0    ; # off
mosquitto_pub -h $MQTT -t "${PREFIX}/blinkrate" -m 0.1  ; # 100ms

# Messages
mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -m foo

mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -m \
  '{"msg": "hello", "text_color": "#595dff", "timeout": 40, "x": "center"}'

mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -m \
  '{"msg": "hi", "no_scroll": "True", "x": -10}'

mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -m '{"msg": "hi scroll"}'

mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -n ; # clear

# Animations
mosquitto_pub -h $MQTT -t "${PREFIX}/img" -m 'parrot'

mosquitto_pub -h $MQTT -t "${PREFIX}/img" -m '{"img": "sine.bmp" }'

mosquitto_pub -h $MQTT -t "${PREFIX}/img" -m '{"img": "bmps/rings.bmp", "timeout": 10 }'

for x in cat fireworks hop parrot rings ruby sine ; do \
  mosquitto_pub -h $MQTT -t "${PREFIX}/img" -m $x
  sleep 10
done

mosquitto_pub -h $MQTT -t "${PREFIX}/img" -n ; # clear
```
