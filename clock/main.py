# NOTE: Make sure you've created your secrets.py file before running this example
# https://learn.adafruit.com/adafruit-pyportal/internet-connect#whats-a-secrets-file-17-2
#

import time
from secrets import secrets  # type: ignore

import board
import busio
import microcontroller
import neopixel

from adafruit_esp32spi import adafruit_esp32spi, adafruit_esp32spi_wifimanager
from adafruit_matrixportal.matrixportal import MatrixPortal
from digitalio import DigitalInOut
from microcontroller import watchdog as wd
from watchdog import WatchDogMode

import clock.shared as Shared
import clock.mqtt as MQTT
import clock.intervals as Intervals
import clock.stats as Stats
import clock.display as Display

esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)

Shared.esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
Shared.matrixportal = MatrixPortal(debug=True, esp=Shared.esp)
Shared.wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(Shared.esp, secrets, None)


print("Connecting to WiFi...")
Shared.wifi.connect()
print("My IP address is", Shared.wifi.ip_address)


def run_once():
    if Shared.ENABLE_DOG:
        print("--------------------------------------------------------")
        print("IMPORTANT: watch dog is enabled! To disable it, do:")
        print("from microcontroller import watchdog as wd ; wd.deinit()")
        print("--------------------------------------------------------")
        wd.timeout = 15  # timeout in seconds
        wd.mode = WatchDogMode.RESET
        Shared.dog_is_enabled = True
    else:
        print("NOTE: watch dog is disabled")
        no_dog()


def no_dog():
    try:
        wd.deinit()
        Shared.dog_is_enabled = False
    except Exception as e:
        print(f"could not disable watchdog: {e}")
    return not Shared.dog_is_enabled


# --------------- Text ----------------- #
# hour (ID = MSG_TIME_IDX)
Shared.matrixportal.add_text(
    text_font=Shared.TIME_FONT,
    text_position=Shared.MSG_POS[Shared.MSG_TIME_IDX],
    text_color=0xFFFFFF,
)
Shared.matrixportal.preload_font(b"0123456789:")
Shared.matrixportal.set_text(" ", Shared.MSG_TIME_IDX)

# status/messages (ID = MSG_TXT_IDX)
Shared.matrixportal.add_text(
    text_position=Shared.MSG_POS[Shared.MSG_TXT_IDX],
)
Shared.matrixportal.set_text(" ", Shared.MSG_TXT_IDX)
Shared.matrixportal.splash.append(Shared.seconds_line)


# ------- Leds  ------- #

# ref: https://www.devdungeon.com/content/pyportal-circuitpy-tutorial-adabox-011#toc-27
pixels = neopixel.NeoPixel(board.NEOPIXEL, 1, auto_write=True)
pixels[0] = (0, 0, 0)

Shared.board_led.switch_to_output()

# ------------- Network Connection ------------- #

Shared.client = MQTT.getMQTTClient()

print(f"Attempting to MQTT connect to {Shared.client.broker}")
try:
    Shared.client.connect()
    Stats.inc_counter("connect")
except Exception as e:
    print(f"FATAL! Unable to MQTT connect to {Shared.client.broker}: {e}")
    time.sleep(120)
    # bye bye cruel world
    microcontroller.reset()


Display.setup()

run_once()

Intervals.setup_intervals()

# ------------- Main loop ------------- #
while True:
    now = time.monotonic()
    for ts_interval in Intervals.TS_INTERVALS:
        if (
            not Intervals.tss[ts_interval]
            or now > Intervals.tss[ts_interval] + Intervals.TS_INTERVALS[ts_interval].interval
        ):
            try:
                if Intervals.TS_INTERVALS[ts_interval].interval >= 60:
                    lt = time.localtime()
                    print(
                        f"{lt.tm_hour}:{lt.tm_min}:{lt.tm_sec} Interval {ts_interval} triggered"
                    )
                else:
                    # print(".", end="")
                    pass
                Intervals.TS_INTERVALS[ts_interval].fun()
            except (ValueError, RuntimeError) as e:
                print(f"Error in {ts_interval}, retrying in 10s: {e}")
                Intervals.tss[ts_interval] = (now - Intervals.TS_INTERVALS[ts_interval].interval) + 10
                Stats.inc_counter("fail_runtime")
                continue
            except Exception as e:
                print(f"Failed {ts_interval}: {e}")
                Stats.inc_counter("fail_other")
            Intervals.tss[ts_interval] = time.monotonic()
