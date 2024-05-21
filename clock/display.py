import time

from adafruit_display_shapes.line import Line

import clock.shared as Shared


def setup():
    global seconds_index, seconds_line
    seconds_line = Line(
        0, 0, Shared.matrixportal.display.width, Shared.matrixportal.display.height, 0xFF0000
    )
    seconds_index = len(Shared.matrixportal.splash)

    set_brightness("on")
    

def set_text_center(val, index, text_color=None):
    pixels_used = 0
    for chararcter in val:
        glyph = Shared.matrixportal._text[index]["label"]._font.get_glyph(ord(chararcter))
        pixels_used += glyph.shift_x
    if pixels_used >= Shared.matrixportal.display.width:
        new_x = 0
    else:
        new_x = int((Shared.matrixportal.display.width - pixels_used) / 2)

    Shared.matrixportal._text[index]["scrolling"] = False
    Shared.matrixportal._text[index]["position"] = (new_x, Shared.MSG_POS[index][1])
    Shared.matrixportal.set_text(val, index)
    if text_color is not None:
        Shared.matrixportal.set_text_color(text_color, index)


def show_date_and_temp():
    global outside_temp

    # roycbiv: https://en.m.wikipedia.org/wiki/ROYGBIV
    now = Shared.global_rtc.datetime
    week_days = [
        ("Mon", 0xFF0000),  # red
        ("Tue", 0xFF4500),  # orange
        ("Wed", 0xFFFF00),  # yellow
        ("Thu", 0x00FF00),  # green
        ("Fri", 0x0000FF),  # blue
        ("Sat", 0x595DFF),  # indigo
        ("Sun", 0x9F51FF),  # violet
    ]
    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    # info = f"{week_days[now.tm_wday][0]}|{months[now.tm_mon-1]}{now.tm_mday:02}"
    info = f"{now.tm_mday}/{months[now.tm_mon-1]}"

    if outside_temp is not None:
        info += f" {outside_temp}C"

    set_text_center(info, Shared.MSG_TXT_IDX, week_days[now.tm_wday][1])


def _pretty_hour(hour):
    if hour == 0:
        return 12
    if hour > 12:
        return hour - 12
    return hour


def main():
    now = Shared.global_rtc.datetime
    Shared.matrixportal.splash[seconds_index] = Line(
        now.tm_sec, 1, now.tm_sec + Shared.SECS_WIDTH, 1, Shared.SECS_COLOR
    )
    if "local_time" not in Shared.counters:
        set_text_center(str(int(time.monotonic())), Shared.MSG_TIME_IDX)
        return

    if Shared.cached_mins == now.tm_min and not Shared.display_needs_refresh:
        return

    set_text_center(f"{_pretty_hour(now.tm_hour)}:{now.tm_min:02}", Shared.MSG_TIME_IDX)

    if not Shared.msg_state:
        show_date_and_temp()

    Shared.cached_mins = now.tm_min
    Shared.display_needs_refresh = False

def set_brightness(val):
    global display_needs_refresh

    """Adjust the TFT backlight.
    :param val: The backlight brightness. Use a value between ``0`` and ``1``, where ``0`` is
                off, and ``1`` is 100% brightness. Can also be 'on' or 'off'
    """
    if isinstance(val, str):
        val = {
            "on": 1,
            "off": 0,
            "mid": 0.5,
            "min": 0.01,
            "max": 1,
            "yes": 1,
            "no": 0,
            "y": 1,
            "n": 0,
        }.get(val.lower(), val)
    try:
        val = float(val)
    except (ValueError, TypeError):
        return
    val = max(0, min(1.0, val))
    # matrixportal.display.auto_brightness = False
    Shared.matrixportal.display.brightness = val
    Shared.display_needs_refresh = True