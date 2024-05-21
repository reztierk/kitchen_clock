import json
import os
import time
import displayio

from adafruit_display_shapes.line import Line

import clock.shared as Shared
import clock.intervals as Intervals
import clock.stats as Stats
import clock.display as Display

def ping(_topic, _message):
    Intervals.tss["send_status"] = None  # clear to force send status now
    Stats.inc_counter("ping")


def brightness(topic, message):
    print("_parse_brightness: {0} {1} {2}".format(len(message), topic, message))
    Display.set_brightness(message)
    Stats.inc_counter("brightness")


def neopixel(_topic, message):
    global pixels
    try:
        value = int(message)
    except ValueError as e:
        print(f"bad neo value: {e}")
        return
    pixels[0] = ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
    Stats.inc_counter("neo")


def blinkrate(_topic, message):
    message = message.lower()
    value_map = {"off": 0, "no": 0, "on": None, "yes": None, "": Intervals.LED_BLINK_DEFAULT}
    try:
        if message.startswith("-") or message in value_map:
            value = value_map.get(message)
        else:
            value = float(message)
    except ValueError as e:
        print(f"bad blink value given {message}: {e}")
        return

    if value:
        Intervals.TS_INTERVALS[Intervals.LED_BLINK] = Intervals.TS(value, Intervals.interval_led_blink)
        Intervals.tss[Intervals.LED_BLINK] = None
    else:
        # Stop blinking. Turn off if value is 0. Turn on if value is None.
        try:
            del Intervals.TS_INTERVALS[Intervals.LED_BLINK]
            del Intervals.tss[Intervals.LED_BLINK]
        except KeyError:
            pass
        Shared.board_led.value = value is None
    Stats.inc_counter("blink")


def localtime_message(topic, message):
    # /aio/local_time : 2021-01-15 23:07:36.339 015 5 -0500 EST
    try:
        print(f"Local time mqtt: {message}")
        times = message.split(" ")
        the_date = times[0]
        the_time = times[1]
        year_day = int(times[2])
        week_day = int(times[3])
        is_dst = None  # no way to know yet
        year, month, mday = [int(x) for x in the_date.split("-")]
        the_time = the_time.split(".")[0]
        hours, minutes, seconds = [int(x) for x in the_time.split(":")]
        now = time.struct_time(
            (year, month, mday, hours, minutes, seconds, week_day, year_day, is_dst)
        )
        Shared.global_rtc.datetime = now
        Stats.inc_counter("local_time")
    except Exception as e:
        print("Error in _parse_localtime_message -", e)
        Stats.inc_counter("local_time_failed")


def temperature_outside(topic, message):
    Shared.outside_temp = int(message)
    Stats.inc_counter("outside_temp")


def msg_message(topic, message):

    print(f"msg_message: {message}")
    Stats.inc_counter("msg_message")
    try:
        Shared.msg_state = json.loads(message)
    except ValueError:
        Shared.msg_state = {"msg": message, "timeout": 20}

    Shared.display_needs_refresh = True
    if not Shared.msg_state.get("msg"):
        Shared.msg_state.clear()
        return

    # timeout
    timeout = Shared.msg_state.get("timeout")
    if timeout is not None:
        Shared.msg_state["timeout"] = int(timeout)

    color = Shared.msg_state.get("text_color") or Shared.msg_state.get("color")
    if color:
        Shared.msg_state["text_color"] = Shared.matrixportal.html_color_convert(color)

    no_scroll = Shared.msg_state.get("no_scroll")
    if no_scroll is not None:
        scrolling = str(no_scroll).lower() != "true"
    else:
        scrolling = True

    x_position = Shared.msg_state.get("x")
    if str(x_position).lower() == "center":
        Display.set_text_center(
            val=Shared.msg_state.get("msg"),
            index=Shared.MSG_TXT_IDX,
            text_color=Shared.msg_state.get("text_color"),
        )
        return

    text_position = (64, Shared.MSG_POS[Shared.MSG_TXT_IDX][1])
    if x_position is not None:
        try:
            text_position = (int(x_position), Shared.MSG_POS[Shared.MSG_TXT_IDX][1])
        except Exception as e:
            print(f"Failed to parse position {x_position}: {e}")

    Shared.matrixportal._text[Shared.MSG_TXT_IDX]["scrolling"] = scrolling
    if Shared.matrixportal._scrolling_index is None and scrolling:
        Shared.matrixportal._scrolling_index = Shared.matrixportal._get_next_scrollable_text_index()

    Shared.matrixportal._text[Shared.MSG_TXT_IDX]["position"] = text_position
    Shared.matrixportal.set_text(val=Shared.msg_state.get("msg"), index=Shared.MSG_TXT_IDX)
    if Shared.msg_state.get("text_color") is not None:
        Shared.matrixportal.set_text_color(Shared.msg_state.get("text_color"), Shared.MSG_TXT_IDX)


def img(_topic, message=""):
    print(f"img: {message}")
    Stats.inc_counter("img_message")
    try:
        img_params = json.loads(message)
    except ValueError:
        img_params = {"img": message, "timeout": 20}

    if Shared.img_index:
        del Shared.matrixportal.splash[Shared.img_index]
        Shared.img_index = None

    img_file = Shared.img_state.get("img_file")
    if img_file:
        img_file.close()

    Shared.img_state.clear()

    if not img_params.get("img"):
        Shared.display_needs_refresh = True
        return

    for filename in (
        "bmps/" + img_params["img"] + ".bmp",
        "bmps/" + img_params["img"],
        img_params["img"],
        img_params["img"] + ".bmp",
    ):
        try:
            os.stat(filename)
            break
        except OSError:
            pass
    print(f"opening image: {filename}")
    Shared.img_state["img_file"] = open(filename, "rb")
    img_bitmap = displayio.OnDiskBitmap(Shared.img_state["img_file"])
    Shared.img_state["img_frame_count"] = int(img_bitmap.height / Shared.matrixportal.display.height)
    img_sprite = displayio.TileGrid(
        img_bitmap,
        pixel_shader=getattr(img_bitmap, "pixel_shader", displayio.ColorConverter()),
        tile_width=img_bitmap.width,
        tile_height=Shared.matrixportal.display.height,
        x=max(Shared.matrixportal.display.width - img_bitmap.width, 0) // 2,
        y=0,
    )
    Shared.img_index = len(Shared.matrixportal.splash)
    Shared.matrixportal.splash.append(img_sprite)

    # timeout
    timeout = img_params.get("timeout")
    if timeout is not None:
        Shared.img_state["timeout"] = int(timeout)

    img_only = img_params.get("img_only")
    if img_only is not None:
        img_only = str(img_only).lower() == "true"
    else:
        img_only = True
    Shared.img_state["img_only"] = img_only
    if img_only:
        Shared.matrixportal.set_text(" ", Shared.MSG_TIME_IDX)
        Shared.matrixportal.set_text(" ", Shared.MSG_TXT_IDX)
        if Shared.seconds_index is not None:
            # Clear seconds line
            Shared.matrixportal.splash[Shared.seconds_index] = Line(0, 1, 0, 1, 0x00)

