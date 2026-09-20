import time

from adafruit_display_shapes.line import Line
from adafruit_matrixportal.graphics import Graphics
from adafruit_matrixportal.matrixportal import MatrixPortal
from adafruit_portalbase import PortalBase

import clock.shared as Shared


class LeanMatrixPortal(PortalBase):
    """MatrixPortal without the network stack.

    matrixportal.MatrixPortal always constructs a Network, whose import chain
    (portalbase.network -> adafruit_io -> adafruit_requests) costs ~50KB of heap
    on 10.x -- enough that the RGB matrix framebuffer can no longer be
    allocated afterwards. This project's WiFi/MQTT is handled independently in
    clock/wifi.py and clock/mqtt.py, so we compose PortalBase + Graphics
    directly and skip Network entirely. Keeps the same add_text/set_text/scroll
    internals the rest of this module relies on.
    """

    def __init__(self, *, debug=False):
        graphics = Graphics(default_bg=0x000000, debug=debug)
        super().__init__(None, graphics, debug=debug)
        self._scrolling_index = None

    # --- scrolling helpers, mirroring matrixportal.MatrixPortal ---
    def _get_next_scrollable_text_index(self):
        index = self._scrolling_index
        while True:
            if index is None:
                index = 0
            else:
                index += 1
            if index >= len(self._text):
                index = 0
            if self._text[index]["scrolling"]:
                return index
            if index == self._scrolling_index:
                return None

    def scroll(self):
        """Scroll any scrolling text by one frame."""
        if self._scrolling_index is None:
            return
        self._text[self._scrolling_index]["label"].x -= 1
        line_width = (
            self._text[self._scrolling_index]["label"].bounding_box[2]
            * self._text[self._scrolling_index]["scale"]
        )
        if self._text[self._scrolling_index]["label"].x < -line_width:
            self._scrolling_index = self._get_next_scrollable_text_index()
            self._text[self._scrolling_index]["label"].x = self.graphics.display.width


def _use_tight_background(index):
    # adafruit_display_text.bitmap_label.Label defaults to background_tight=False,
    # which anchors on a "loose" box sized from the font's FONTBOUNDINGBOX
    # (ascent+descent -- ~28px for time_font.bdf) instead of the actual glyph
    # pixels. That pushes anchor_point=(0,0) labels far past their configured
    # y (time label lands ~y=20, on top of the date row). Forcing tight mode
    # anchors on the real per-string glyph bbox, matching the y=3/y=20 layout
    # this module was tuned against.
    label = Shared.matrixportal._text[index]["label"]
    if label is not None and not label._background_tight:
        label._background_tight = True
        label._reset_text()


def setup():
    # LeanMatrixPortal is functionally identical for this project but avoids
    # the ~50KB network import chain; the stock MatrixPortal is kept imported
    # above as a fallback if the lean path ever breaks on a library bump.
    try:
        Shared.matrixportal = LeanMatrixPortal(debug=True)
    except Exception as e:
        print(f"LeanMatrixPortal failed ({e}); falling back to MatrixPortal")
        Shared.matrixportal = MatrixPortal(debug=True, esp=Shared.esp)

    # Measured on-device glyph boxes (label.y = anchor_y + bbox_y):
    #   time font  "8:56" / "12:34" -> bbox (x=0, y=-5, w=41/51, h=16)
    #   terminal   "19/Sep 72C"       -> bbox (x=0, y=-6, w=60, h=12)
    # Layout on the 64x32 display, both top-left anchored and centered
    # horizontally by set_text_center(). Vertical bands, with clear gaps:
    #   seconds line: y=0 (top edge)
    #   time:  anchor_y=3  -> renders y=3..17
    #   date:  anchor_y=20 -> renders y=20..32 (bottom, small terminal font)
    Shared.matrixportal.add_text(
        text_font=Shared.TIME_FONT,
        text_position=(Shared.MSG_POS[Shared.MSG_TIME_IDX][0], 3),
        text_color=0xFFFFFF,
        text_anchor_point=(0, 0),
    )
    Shared.matrixportal.preload_font(b"0123456789:")
    Shared.matrixportal.set_text(" ", Shared.MSG_TIME_IDX)
    _use_tight_background(Shared.MSG_TIME_IDX)

    # status/messages (ID = MSG_TXT_IDX): small built-in terminal font so it
    # fits as a single row at the bottom of the display.
    Shared.matrixportal.add_text(
        text_position=(Shared.MSG_POS[Shared.MSG_TXT_IDX][0], 20),
        text_anchor_point=(0, 0),
    )
    Shared.matrixportal.set_text(" ", Shared.MSG_TXT_IDX)
    _use_tight_background(Shared.MSG_TXT_IDX)

    Shared.seconds_line = Line(
        0,
        0,
        Shared.SECS_WIDTH,
        0,
        Shared.SECS_COLOR,
    )
    Shared.seconds_line.y = 0
    Shared.seconds_line.x = 0
    Shared.seconds_index = len(Shared.matrixportal.splash)
    Shared.matrixportal.splash.append(Shared.seconds_line)

    set_brightness("on")


def set_text_center(val, index, text_color=None):
    # NOTE: relies on MatrixPortal/PortalBase internals (_text/label/_font);
    # validated against adafruit_matrixportal 3.2.12 + adafruit_portalbase 3.5.2
    pixels_used = 0
    font = Shared.matrixportal._text[index]["label"]._font
    for character in val:
        glyph = font.get_glyph(ord(character))
        if glyph:
            pixels_used += glyph.shift_x
        else:
            pixels_used += 6
    if pixels_used >= Shared.matrixportal.display.width:
        new_x = 0
    else:
        new_x = int((Shared.matrixportal.display.width - pixels_used) / 2)

    Shared.matrixportal._text[index]["scrolling"] = False
    # Keep the label's configured y (the time label uses an anchor-corrected y
    # of -2), only recenter horizontally.
    cur_y = Shared.matrixportal._text[index]["position"][1]
    Shared.matrixportal._text[index]["position"] = (new_x, cur_y)
    Shared.matrixportal.set_text(val, index)

    if text_color is not None:
        Shared.matrixportal.set_text_color(text_color, index)


def show_date_and_temp():
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

    month_idx = max(0, min(11, now.tm_mon - 1)) if now.tm_mon else 0
    info = f"{now.tm_mday}/{months[month_idx]}"

    if Shared.outside_temp is not None:
        info += f" {Shared.outside_temp}C"

    wday_idx = (now.tm_wday if (now.tm_wday is not None and 0 <= now.tm_wday < 7) else 0)
    set_text_center(info, Shared.MSG_TXT_IDX, week_days[wday_idx][1])


def _pretty_hour(hour):
    if hour == 0:
        return 12
    if hour > 12:
        return hour - 12
    return hour


def main():
    now = Shared.global_rtc.datetime
    if Shared.seconds_line is not None and not Shared.img_state.get("img_only"):
        Shared.seconds_line.hidden = False
        Shared.seconds_line.x = min(
            now.tm_sec, Shared.matrixportal.display.width - Shared.SECS_WIDTH - 1
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
