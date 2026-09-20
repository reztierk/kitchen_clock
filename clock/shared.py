import os
import time
from collections import namedtuple

import board
import digitalio
import rtc


def _getenv_bool(key, default):
    # os.getenv() always returns strings (or None), so booleans need manual parsing
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off")


ENABLE_DOG = _getenv_bool("ENABLE_DOG", True)
MSG_TIME_IDX = 0
MSG_TXT_IDX = 1
MSG_POS = [(0, 5), (0, 26)]
TIME_FONT = "clock/time_font.bdf"
SECS_COLOR = 0x404040
SECS_WIDTH = 4
LED_BLINK = "led_blink"
LED_BLINK_DEFAULT = 60
TS = namedtuple("TS", "interval fun")  # tss routines
TS_INTERVALS = {}

matrixportal = None
client = None
wifi = None
esp = None
cached_mins = None
outside_temp = None
img_index = None
seconds_line = None
seconds_index = None
pixels = None

dog_is_enabled = False
display_needs_refresh = True

msg_state = {}
counters = {}
img_state = {}
tss = {}

global_rtc = rtc.RTC()  # Real Time Clock
start_time = time.monotonic()
board_led = digitalio.DigitalInOut(board.L)  # Or board.D13
topic_prefix = os.getenv("TOPIC_PREFIX") or "/matrixportal"
pub_status_topic = f"{topic_prefix}/status"
reset_reason = None
