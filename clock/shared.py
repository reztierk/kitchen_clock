import time
from collections import namedtuple
from secrets import secrets  # type: ignore

import board
import digitalio
import rtc

ENABLE_DOG = True
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
topic_prefix = secrets.get("topic_prefix") or "/matrixportal"
pub_status_topic = f"{topic_prefix}/status"
