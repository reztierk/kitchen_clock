# NOTE: Make sure you've created your secrets.py file before running this example
# https://learn.adafruit.com/adafruit-pyportal/internet-connect#whats-a-secrets-file-17-2
#

import time

import clock.display as Display
import clock.dog as Dog
import clock.intervals as Intervals
import clock.led as Led
import clock.mqtt as MQTT
import clock.shared as Shared
import clock.stats as Stats
import clock.wifi as Wifi

Wifi.setup()
Display.setup()
Led.setup()
MQTT.setup()
Dog.setup()
Intervals.setup(
    {
        "send_status": Shared.TS(10 * 60, Intervals.interval_send_status),
        Shared.LED_BLINK: Shared.TS(
            Shared.LED_BLINK_DEFAULT, Intervals.interval_led_blink
        ),  # may be overridden via mqtt
        "1sec": Shared.TS(1, Intervals.interval_one_sec),
        "decasec": Shared.TS(0.1, Intervals.interval_one_decasec),
    }
)

# ------------- Main loop ------------- #
while True:
    now = time.monotonic()
    for ts_interval in Shared.TS_INTERVALS:
        if (
            not Shared.tss[ts_interval]
            or now > Shared.tss[ts_interval] + Shared.TS_INTERVALS[ts_interval].interval
        ):
            try:
                if Shared.TS_INTERVALS[ts_interval].interval >= 60:
                    lt = time.localtime()
                    print(
                        f"{lt.tm_hour}:{lt.tm_min}:{lt.tm_sec} Interval {ts_interval} triggered"
                    )
                else:
                    pass
                Shared.TS_INTERVALS[ts_interval].fun()
            except (ValueError, RuntimeError) as e:
                print(f"Error in {ts_interval}, retrying in 10s: {e}")
                Shared.tss[ts_interval] = (
                    now - Shared.TS_INTERVALS[ts_interval].interval
                ) + 10
                Stats.inc_counter("fail_runtime")
                continue
            except Exception as e:
                print(f"Failed {ts_interval}: {e}")
                Stats.inc_counter("fail_other")
            Shared.tss[ts_interval] = time.monotonic()
