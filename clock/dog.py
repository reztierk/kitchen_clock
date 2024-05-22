from microcontroller import watchdog as wd
from watchdog import WatchDogMode

import clock.shared as Shared


def setup():
    if Shared.ENABLE_DOG:
        print("--------------------------------------------------------")
        print("IMPORTANT: watch dog is enabled! To disable it, do:")
        print("from microcontroller import watchdog as wd ; wd.deinit()")
        print("--------------------------------------------------------")
        wd.timeout = 15  # timeout in seconds
        wd.mode = WatchDogMode.RESET
        Shared.dog_is_enabled = True
    else:
        print("NOTE: watch dog is disabled")
        no_dog()


def no_dog():
    try:
        wd.deinit()
        Shared.dog_is_enabled = False
    except Exception as e:
        print(f"could not disable watchdog: {e}")
    return not Shared.dog_is_enabled
