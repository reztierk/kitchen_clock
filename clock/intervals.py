import gc
import json
import time

from microcontroller import watchdog as wd

import clock.display as Display
import clock.parse as Parse
import clock.shared as Shared

# ------------- Iteration routines ------------- #


def interval_one_sec():
    if Shared.dog_is_enabled:
        wd.feed()

    if Shared.matrixportal._scrolling_index is None and not Shared.img_state:
        Shared.client.loop(0.5)

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

    if Shared.img_state is not None:
        curr_timeout = Shared.img_state.get("timeout")
        if isinstance(curr_timeout, int):
            if curr_timeout <= 0:
                Parse.img(None, message="")
            else:
                Shared.img_state["timeout"] = curr_timeout - 1

        if Shared.img_state.get("img_only"):
            return

    if Shared.matrixportal.display.brightness:
        # check if scroll needs to be started
        if Shared.matrixportal._scrolling_index is None:
            Shared.matrixportal.scroll()

        Display.main()


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
    value = {
        "uptime_mins": int(time.monotonic() - Shared.start_time) // 60,
        "brightness": Shared.matrixportal.display.brightness,
        "ip": Shared.wifi.ip_address(),
        "counters": str(Shared.counters),
        "mem_free": gc.mem_free(),
    }
    Shared.client.publish(Shared.pub_status_topic, json.dumps(value))
    print(f"send_status: {Shared.pub_status_topic}: {value}")
    Shared.client.publish("homeassistant/local_time/refresh", "refresh")


def interval_led_blink():
    Shared.board_led.value = not Shared.board_led.value


def setup(intervals):
    Shared.TS_INTERVALS.update(intervals)
    Shared.tss.update({interval: None for interval in Shared.TS_INTERVALS})
