"""Time-of-day color schedule for the clock digits and seconds bar.

time_color() is a pure function. update() and handle_message()
are the display/MQTT glue; they live here (not in display.py/parse.py)
because those modules are compiled from source at boot and the heap is too
tight to let them grow. Every keyframe keeps its dominant channel >= 0x40,
because darker values band or disappear on the panel's limited bit depth.
"""

import clock.shared as Shared
import clock.stats as Stats

MINS_PER_DAY = 24 * 60
PREVIEW_STEP = 48  # schedule minutes per second: a full day sweeps in 30s

# (minute_of_day, (r, g, b)); the last entry must be at MINS_PER_DAY and match the first
KEYFRAMES = (
    (0, (0x40, 0x18, 0x00)),  # deep night: dim amber
    (5 * 60, (0x50, 0x20, 0x00)),
    (7 * 60, (0xFF, 0x90, 0x30)),  # sunrise: warm amber
    (9 * 60, (0xFF, 0xD8, 0xA0)),  # morning: soft warm white
    (12 * 60, (0xE0, 0xF0, 0xFF)),  # midday: cool white
    (16 * 60, (0xFF, 0xF4, 0xE0)),  # afternoon: neutral white
    (19 * 60, (0xFF, 0xC0, 0x40)),  # evening: warm yellow
    (21 * 60, (0xFF, 0x60, 0x10)),  # dusk: orange
    (23 * 60, (0x60, 0x28, 0x00)),
    (MINS_PER_DAY, (0x40, 0x18, 0x00)),
)


def _pack(r, g, b):
    return (r << 16) | (g << 8) | b


def time_color(minute_of_day):
    """Packed 0xRRGGBB for the given minute of the day (wraps past 24h)."""
    minute_of_day %= MINS_PER_DAY
    prev_min, prev_rgb = KEYFRAMES[0]
    for next_min, next_rgb in KEYFRAMES[1:]:
        if minute_of_day <= next_min:
            span = next_min - prev_min
            offset = minute_of_day - prev_min
            return _pack(
                *[
                    p + (n - p) * offset // span
                    for p, n in zip(prev_rgb, next_rgb)
                ]
            )
        prev_min, prev_rgb = next_min, next_rgb
    return _pack(*prev_rgb)


def update(now):
    """Apply the time-of-day color to the time digits and the seconds bar."""
    if Shared.ambient_preview is not None:
        minute = Shared.ambient_preview
        Shared.ambient_preview += PREVIEW_STEP
        if Shared.ambient_preview >= MINS_PER_DAY:
            Shared.ambient_preview = None
    else:
        minute = now.tm_hour * 60 + now.tm_min

    if Shared.ambient_override is not None:
        color = Shared.ambient_override
    elif Shared.ambient_enabled:
        color = time_color(minute)
    else:
        color = Shared.TIME_COLOR_DEFAULT

    if Shared.ambient_color == color:
        return
    Shared.matrixportal.set_text_color(color, Shared.MSG_TIME_IDX)
    if Shared.seconds_line is not None:
        Shared.seconds_line.color = color
    Shared.ambient_color = color


def handle_message(_topic, message):
    """MQTT: on/auto, off, preview, or a color such as 0xFFA040."""
    message = message.strip().lower()
    if message in ("", "on", "auto", "yes"):
        Shared.ambient_enabled = True
        Shared.ambient_override = None
        Shared.ambient_mode = "auto"
    elif message in ("off", "no"):
        Shared.ambient_enabled = False
        Shared.ambient_override = None
        Shared.ambient_mode = "off"
    elif message == "preview":
        Shared.ambient_enabled = True
        Shared.ambient_override = None
        Shared.ambient_mode = "auto"
        Shared.ambient_preview = 0
    else:
        try:
            value = int(message, 0)  # accepts decimal and 0x-prefixed hex
        except ValueError as e:
            print(f"bad ambient value: {e}")
            return
        Shared.ambient_override = value & 0xFFFFFF
        Shared.ambient_mode = "override"
    Shared.ambient_color = None  # force the display to re-apply colors
    Stats.inc_counter("ambient")
