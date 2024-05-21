import rtc
import time
import digitalio
import board

from secrets import secrets  # type: ignore

ENABLE_DOG = True
MSG_TIME_IDX = 0
MSG_TXT_IDX = 1
MSG_POS = [(0, 5), (0, 26)]
TIME_FONT = "time_font.bdf"
SECS_COLOR = 0x404040
SECS_WIDTH = 4

matrixportal = None
client = None
wifi = None
esp = None
cached_mins = None
outside_temp = None
img_index = None

dog_is_enabled = False
display_needs_refresh = True

msg_state = {}
counters = {}
img_state = {}

global_rtc = rtc.RTC() # Real Time Clock
start_time = time.monotonic()
board_led = digitalio.DigitalInOut(board.L)  # Or board.D13
topic_prefix = secrets.get("topic_prefix") or "/matrixportal"
pub_status_topic = f"{topic_prefix}/status"
