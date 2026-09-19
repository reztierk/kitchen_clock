import gc
import json
import time

import clock.display as Display
import clock.dog as Dog
import clock.mqtt as MQTT
import clock.parse as Parse
import clock.shared as Shared
import clock.stats as Stats

# ------------- Iteration routines ------------- #


def interval_one_sec():
    Dog.feed()

    # Process MQTT messages (non-blocking when scrolling, responsive when messages arrive)
    try:
        if Shared.client and Shared.client.is_connected():
            sock = getattr(Shared.client, "_sock", None)
            has_data = False
            if sock and hasattr(sock, "_available"):
                try:
                    avail = sock._available()
                    has_data = avail is not None and avail > 0
                except Exception:
                    has_data = True
            else:
                has_data = True

            is_scrolling = Shared.matrixportal._scrolling_index is not None
            if has_data or not is_scrolling:
                Shared.client.loop(timeout=1.0)
        elif Shared.client:
            MQTT.reconnect()
    except Exception as e:
        print(f"MQTT loop/reconnect error: {e}")
        Stats.inc_counter("fail_loop")

    # If time has not synced yet, periodically request it
    if "local_time" not in Shared.counters:
        if int(time.monotonic()) % 10 == 0:
            try:
                if Shared.client and Shared.client.is_connected():
                    print("Requesting time sync...")
                    Shared.client.publish("homeassistant/local_time/refresh", "refresh")
            except Exception:
                pass

    # Manage timeouts
    if Shared.msg_state:
        curr_timeout = Shared.msg_state.get("timeout")
        if isinstance(curr_timeout, int):
            if curr_timeout <= 0:
                Shared.matrixportal._text[Shared.MSG_TXT_IDX]["scrolling"] = False
                Shared.matrixportal._scrolling_index = None
                Shared.matrixportal.set_text(val=" ", index=Shared.MSG_TXT_IDX)
                Shared.display_needs_refresh = True
                Shared.msg_state.clear()
            else:
                Shared.msg_state["timeout"] = curr_timeout - 1

    if Shared.img_state:
        curr_timeout = Shared.img_state.get("timeout")
        if isinstance(curr_timeout, int):
            if curr_timeout <= 0:
                Parse.img(None, message="")
                if Shared.seconds_line is not None:
                    Shared.seconds_line.hidden = False
            else:
                Shared.img_state["timeout"] = curr_timeout - 1

        if Shared.img_state.get("img_only"):
            return

    if Shared.matrixportal.display.brightness:
        # check if scroll needs to be started
        if Shared.matrixportal._scrolling_index is None:
            Shared.matrixportal.scroll()

        Display.main()

    # Periodic garbage collection once a minute to prevent heap fragmentation
    if Shared.global_rtc.datetime.tm_sec == 0:
        gc.collect()


def advance_img():
    if not Shared.img_state or not Shared.matrixportal.display.brightness:
        return

    img_curr_frame = Shared.img_state.get("img_curr_frame", 0)
    Shared.matrixportal.splash[Shared.img_index][0] = img_curr_frame
    Shared.img_state["img_curr_frame"] = (img_curr_frame + 1) % Shared.img_state[
        "img_frame_count"
    ]


def scroll_msg():
    if not Shared.img_state and Shared.matrixportal._scrolling_index is not None:
        # Scroll the text block, but only if there is work
        # There is an explicit in a less frequent interval (one_sec_tick)
        Shared.matrixportal.scroll()


def interval_one_decasec():
    advance_img()
    scroll_msg()


def interval_send_status():
    Dog.feed()
    ip = None
    try:
        if Shared.esp and Shared.esp.is_connected and Shared.wifi:
            ip = Shared.wifi.ip_address
    except Exception as e:
        print(f"send_status: could not read IP: {e}")

    value = {
        "uptime_mins": int(time.monotonic() - Shared.start_time) // 60,
        "brightness": Shared.matrixportal.display.brightness,
        "ip": str(ip),
        "counters": str(Shared.counters),
        "mem_free": gc.mem_free(),
        "reset_reason": str(getattr(Shared, "reset_reason", "unknown")),
    }
    print(f"send_status: {Shared.pub_status_topic}: {value}")
    try:
        if Shared.client and Shared.client.is_connected():
            Shared.client.publish(Shared.pub_status_topic, json.dumps(value))
            Shared.client.publish("homeassistant/local_time/refresh", "refresh")
    except Exception as e:
        print(f"send_status: publish failed: {e}")
    Dog.feed()
    gc.collect()


def interval_led_blink():
    Shared.board_led.value = not Shared.board_led.value


def setup(intervals):
    Shared.TS_INTERVALS.update(intervals)
    Shared.tss.update({interval: None for interval in Shared.TS_INTERVALS})
