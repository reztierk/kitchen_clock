from microcontroller import watchdog as wd
from watchdog import WatchDogMode

import clock.shared as Shared


def setup():
    if Shared.ENABLE_DOG:
        print("--------------------------------------------------------")
        print("IMPORTANT: watch dog is enabled! To disable it, set")
        print("ENABLE_DOG = false in settings.toml, or do:")
        print("from microcontroller import watchdog as wd ; wd.deinit()")
        print("--------------------------------------------------------")
        wd.timeout = 16  # timeout in seconds (SAMD51 max hardware timeout)
        wd.mode = WatchDogMode.RESET
        Shared.dog_is_enabled = True
    else:
        print("NOTE: watch dog is disabled")
        no_dog()


def no_dog():
    try:
        wd.mode = None
    except Exception:
        pass
    try:
        wd.deinit()
    except Exception:
        pass
    Shared.dog_is_enabled = False
    return not Shared.dog_is_enabled


def pause():
    if Shared.dog_is_enabled:
        try:
            wd.mode = None
        except Exception:
            try:
                wd.deinit()
            except Exception:
                pass


def resume():
    if Shared.ENABLE_DOG:
        try:
            feed()
            wd.timeout = 16
            wd.mode = WatchDogMode.RESET
            Shared.dog_is_enabled = True
        except Exception:
            pass


def feed():
    if Shared.dog_is_enabled:
        try:
            wd.feed()
        except Exception:
            pass
