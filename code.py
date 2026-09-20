# Enable the hardware watchdog as early as possible so even an import-time
# hang self-recovers (clock.dog.setup() runs later and honors enable_dog too)
try:
    from secrets import secrets

    if secrets.get("enable_dog", True):
        from microcontroller import watchdog as wd
        from watchdog import WatchDogMode

        wd.timeout = 16  # SAMD51 max hardware timeout
        wd.mode = WatchDogMode.RESET
except Exception:
    pass

try:
    import clock.main  # noqa: F401
except Exception as e:
    print(f"Fatal error starting clock.main: {e}")
    # Disarm the watchdog armed above, otherwise it would reset the board
    # every 16s while sitting at the REPL, cycling the USB drive
    try:
        from microcontroller import watchdog as wd

        wd.mode = None
        wd.deinit()
    except Exception:
        pass
    # Never auto-reset: a crash that resets would unmount the USB drive and
    # loop forever, making recovery impossible. Instead, drop to the REPL so
    # the drive stays mounted and the error stays visible.
    raise

