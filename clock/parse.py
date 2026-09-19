import json
import os
import time

import displayio
from adafruit_display_shapes.line import Line

import clock.display as Display
import clock.shared as Shared
import clock.stats as Stats


def ping(_topic, _message):
    Shared.tss["send_status"] = None  # clear to force send status now
    Stats.inc_counter("ping")


def brightness(topic, message):
    print("_parse_brightness: {0} {1} {2}".format(len(message), topic, message))
    Display.set_brightness(message)
    Stats.inc_counter("brightness")


def neopixel(_topic, message):
    try:
        value = int(message)
    except ValueError as e:
        print(f"bad neo value: {e}")
        return
    Shared.pixels[0] = ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
    Stats.inc_counter("neo")


def blinkrate(_topic, message):
    message = message.lower()
    value_map = {
        "off": 0,
        "no": 0,
        "on": None,
        "yes": None,
        "": Shared.LED_BLINK_DEFAULT,
    }
    try:
        if message.startswith("-") or message in value_map:
            value = value_map.get(message)
        else:
            value = float(message)
    except ValueError as e:
        print(f"bad blink value given {message}: {e}")
        return

    if value:
        Shared.TS_INTERVALS[Shared.LED_BLINK] = Shared.TS(
            value, Shared.interval_led_blink
        )
        Shared.tss[Shared.LED_BLINK] = None
    else:
        # Stop blinking. Turn off if value is 0. Turn on if value is None.
        try:
            del Shared.TS_INTERVALS[Shared.LED_BLINK]
            del Shared.tss[Shared.LED_BLINK]
        except KeyError:
            pass
        Shared.board_led.value = value is None
    Stats.inc_counter("blink")


def localtime_message(topic, message):
    # Formats supported:
    # 1) Adafruit IO: "2021-01-15 23:07:36.339 015 5 -0500 EST"
    # 2) Home Assistant / ISO-8601: "2024-04-16T15:30:00-04:00" or with subseconds/Z
    # 3) Plain datetime string: "2024-04-16 15:30:00"
    # 4) JSON wrapper: {"datetime": "..."}
    # 5) Unix epoch integer/float
    try:
        print(f"Local time mqtt: {message}")
        msg = message.strip()
        if (msg.startswith('"') and msg.endswith('"')) or (msg.startswith("'") and msg.endswith("'")):
            msg = msg[1:-1].strip()

        # Handle JSON payload if Home Assistant sends JSON
        if msg.startswith("{") and msg.endswith("}"):
            try:
                data = json.loads(msg)
                for k in ("datetime", "date_time", "time", "local_time", "state", "value"):
                    if k in data and isinstance(data[k], str):
                        msg = data[k].strip()
                        break
            except Exception:
                pass

        # Handle unix timestamp
        try:
            val = float(msg)
            if val > 1000000000:
                now = time.localtime(int(val))
                Shared.global_rtc.datetime = now
                Shared.display_needs_refresh = True
                Stats.inc_counter("local_time")
                return
        except (ValueError, TypeError):
            pass

        times = msg.split()
        the_date = times[0]
        the_time = times[1] if len(times) > 1 else ""

        if "T" in the_date:
            parts = the_date.split("T")
            the_date = parts[0]
            if not the_time:
                the_time = parts[1]

        year, month, mday = [int(x) for x in the_date.split("-")[:3]]

        # Clean time: strip subseconds and timezone offsets (+00:00, -04:00, Z)
        if "." in the_time:
            the_time = the_time.split(".")[0]
        for tz_char in ("+", "Z", "z"):
            if tz_char in the_time:
                the_time = the_time.split(tz_char)[0]
        if "-" in the_time:
            the_time = the_time.split("-")[0]

        time_parts = [int(x) for x in the_time.split(":")[:3]]
        hours = time_parts[0] if len(time_parts) > 0 else 0
        minutes = time_parts[1] if len(time_parts) > 1 else 0
        seconds = time_parts[2] if len(time_parts) > 2 else 0

        # Calculate weekday (0=Mon, 6=Sun) and day of year
        y = year if month >= 3 else year - 1
        t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
        week_day = (y + y // 4 - y // 100 + y // 400 + t[month - 1] + mday + 6) % 7
        days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
            days[1] = 29
        year_day = sum(days[:month - 1]) + mday

        if len(times) > 2:
            try:
                year_day = int(times[2])
            except ValueError:
                pass
        if len(times) > 3:
            try:
                week_day = int(times[3])
            except ValueError:
                pass

        now = time.struct_time(
            (year, month, mday, hours, minutes, seconds, week_day, year_day, -1)
        )
        Shared.global_rtc.datetime = now
        Shared.display_needs_refresh = True
        Stats.inc_counter("local_time")
    except Exception as e:
        print("Error in _parse_localtime_message -", e)
        Stats.inc_counter("local_time_failed")


def temperature_outside(topic, message):
    try:
        Shared.outside_temp = int(round(float(message)))
        Stats.inc_counter("outside_temp")
    except (ValueError, TypeError) as e:
        print(f"bad outside_temp {message}: {e}")


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
        Shared.matrixportal._scrolling_index = (
            Shared.matrixportal._get_next_scrollable_text_index()
        )

    Shared.matrixportal._text[Shared.MSG_TXT_IDX]["position"] = text_position
    Shared.matrixportal.set_text(
        val=Shared.msg_state.get("msg"), index=Shared.MSG_TXT_IDX
    )
    if Shared.msg_state.get("text_color") is not None:
        Shared.matrixportal.set_text_color(
            Shared.msg_state.get("text_color"), Shared.MSG_TXT_IDX
        )


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
    Shared.img_state["img_frame_count"] = int(
        img_bitmap.height / Shared.matrixportal.display.height
    )
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
        if Shared.seconds_line is not None:
            Shared.seconds_line.hidden = True
