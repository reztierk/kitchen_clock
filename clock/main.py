# NOTE: Make sure you've created your secrets.py file before running this example
# https://learn.adafruit.com/adafruit-pyportal/internet-connect#whats-a-secrets-file-17-2
#

import gc
import time

import microcontroller

# Import the display module FIRST and set it up before anything else.
# The RGB matrix framebuffer is allocated from the port heap, and on
# CircuitPython 10.x the cumulative effect of importing the full
# display_text/minimqtt/esp32spi chain fragments that heap enough that the 4KB
# framebuffer can no longer be allocated. Building the display first, while the
# heap is still compact, is the only reliable ordering (verified empirically:
# every combination works alone, but the full chain fails if it imports first).
import clock.display as Display
import clock.shared as Shared

Display.setup()
gc.collect()

# gc.collect() between each import below: the minimqtt/esp32spi chain got
# heavier after the last library bump and now fragments the heap enough to
# fail a ~1.3KB allocation mid-import without these compaction points.
import clock.dog as Dog
gc.collect()
import clock.intervals as Intervals
gc.collect()
import clock.led as Led
gc.collect()
import clock.mqtt as MQTT
gc.collect()
import clock.reset_log as ResetLog
gc.collect()
import clock.stats as Stats
gc.collect()
import clock.wifi as Wifi
gc.collect()

reset_reason_str = "UNKNOWN"
boot_uptime = int(time.monotonic())
if hasattr(microcontroller, "cpu") and hasattr(microcontroller.cpu, "reset_reason"):
    reset_reason_str = str(microcontroller.cpu.reset_reason).replace("microcontroller.ResetReason.", "")
    if reset_reason_str == "UNKNOWN" and boot_uptime > 10:
        reset_reason_str = "SOFT_RELOAD"
    print(f"Board reset reason: {reset_reason_str}")
Shared.reset_reason = reset_reason_str
Stats.inc_counter(f"boot_{reset_reason_str}")
ResetLog.record_reset(reset_reason_str)

# Enable the watchdog before the network stack so a hang there self-recovers
Dog.setup()
Dog.feed()
Wifi.setup()
Dog.feed()
Led.setup()
MQTT.setup()
Dog.feed()
Intervals.setup(
    {
        "send_status": Shared.TS(10 * 60, Intervals.interval_send_status),
        Shared.LED_BLINK: Shared.TS(
            Shared.LED_BLINK_DEFAULT, Led.interval_led_blink
        ),  # may be overridden via mqtt
        "1sec": Shared.TS(1, Intervals.interval_one_sec),
        "decasec": Shared.TS(0.1, Intervals.interval_one_decasec),
    }
)

# ------------- Main loop ------------- #
while True:
    try:
        Dog.feed()
        now = time.monotonic()
        for ts_interval in list(Shared.TS_INTERVALS):
            if ts_interval not in Shared.TS_INTERVALS:
                continue
            interval_obj = Shared.TS_INTERVALS[ts_interval]
            last_ts = Shared.tss.get(ts_interval)
            if last_ts is None or now > last_ts + interval_obj.interval:
                try:
                    if interval_obj.interval >= 60:
                        lt = time.localtime()
                        print(
                            f"{lt.tm_hour}:{lt.tm_min}:{lt.tm_sec} Interval {ts_interval} triggered"
                        )
                    interval_obj.fun()
                except Exception as e:
                    is_runtime = isinstance(e, (ValueError, RuntimeError))
                    print(f"Failed {ts_interval}: {e}")
                    Stats.inc_counter("fail_runtime" if is_runtime else "fail_other")
                    if interval_obj.interval >= 10:
                        # Retry in 30s instead of waiting the full interval
                        Shared.tss[ts_interval] = (
                            now - interval_obj.interval
                        ) + 30
                        continue
                Shared.tss[ts_interval] = time.monotonic()
        # Yield briefly; the fastest tick is 0.1s (decasec), so 20ms keeps
        # timing tight while avoiding a busy spin
        time.sleep(0.02)
    except Exception as e:
        print(f"Unhandled exception in main loop: {e}")
        Stats.inc_counter("fail_main_loop")
        time.sleep(0.5)
        Dog.feed()
