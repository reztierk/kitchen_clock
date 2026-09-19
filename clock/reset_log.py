import time

# The reset log lives entirely in alarm.sleep_memory (SAMD51 backup SRAM).
# It survives watchdog resets, system resets, and soft reloads -- the exact
# scenarios we want to diagnose -- and is cleared only on power-on. Unlike the
# filesystem or microcontroller.nvm (both flash-backed on SAMD51, ~10k erase
# cycles), RAM writes cause no flash wear and cannot trigger auto-reload.
#
# Layout:
#   bytes 0..15:   b"HB:" + 8-digit uptime + b"\x00" (heartbeat)
#   bytes 16..end: b"RST:" + b"REASON,boot_uptime,prev_uptime;..." entries
MAX_ENTRIES = 10
HB_OFFSET = 0
HB_LEN = 16
RST_OFFSET = 16

try:
    import alarm

    sleep_mem = alarm.sleep_memory
except Exception:
    sleep_mem = None  # Local desktop simulation/testing

_mem_fallback = []  # last-resort in-process list if sleep_memory is unavailable


def heartbeat(uptime_secs):
    """Record current session uptime so the next boot can see how long this
    session ran before it reset. RAM write -- no flash wear."""
    if sleep_mem is None:
        return
    try:
        payload = f"HB:{int(uptime_secs):08d}\x00".encode("utf-8")
        sleep_mem[HB_OFFSET : HB_OFFSET + len(payload)] = payload
    except Exception:
        pass


def _read_last_heartbeat():
    """Read the previous session's last heartbeat (None on power-on reset)."""
    if sleep_mem is None:
        return None
    try:
        hb_bytes = bytes(sleep_mem[HB_OFFSET : HB_OFFSET + HB_LEN])
        if hb_bytes.startswith(b"HB:"):
            raw = hb_bytes[3:].split(b"\x00")[0].decode("utf-8", "ignore")
            return int(raw) if raw.isdigit() else None
    except Exception:
        pass
    return None


def _read_log():
    if sleep_mem is None:
        return list(_mem_fallback)
    entries = []
    try:
        raw = bytes(sleep_mem[RST_OFFSET:])
        if raw.startswith(b"RST:"):
            raw_str = raw[4:].split(b"\x00")[0].decode("utf-8", "ignore")
            for item in raw_str.split(";"):
                parts = item.split(",")
                if len(parts) == 3 and parts[0]:
                    entries.append(
                        {
                            "reason": parts[0],
                            "boot_uptime": int(parts[1]) if parts[1].isdigit() else 0,
                            "prev_session_uptime": int(parts[2]) if parts[2].isdigit() else 0,
                        }
                    )
    except Exception:
        pass
    return entries


def _write_log(entries):
    if sleep_mem is None:
        _mem_fallback[:] = entries
        return
    try:
        while entries:
            compact = ";".join(
                f"{item['reason']},{item.get('boot_uptime', 0)},{item.get('prev_session_uptime', 0)}"
                for item in entries
            )
            payload = b"RST:" + compact.encode("utf-8")
            if len(payload) <= len(sleep_mem) - RST_OFFSET:
                padded = payload + b"\x00" * (len(sleep_mem) - RST_OFFSET - len(payload))
                sleep_mem[RST_OFFSET:] = padded
                return
            entries = entries[1:]  # payload too big: drop oldest entry, retry
    except Exception as e:
        print(f"Could not write reset log to backup RAM: {e}")


def record_reset(reset_reason):
    """Record this boot's reset reason in the RAM log (keeps at most MAX_ENTRIES)."""
    reason_str = str(reset_reason).replace("microcontroller.ResetReason.", "")
    boot_uptime = int(time.monotonic())
    if reason_str == "UNKNOWN" and boot_uptime > 10:
        # A soft reload restarts code.py without resetting the MCU, so the
        # reset_reason register reads UNKNOWN while monotonic time keeps going.
        reason_str = "SOFT_RELOAD"

    prev_uptime = _read_last_heartbeat()
    heartbeat(0)  # reset heartbeat for the new session

    entries = _read_log()
    entry = {"reason": reason_str, "boot_uptime": boot_uptime}
    if prev_uptime is not None:
        entry["prev_session_uptime"] = prev_uptime
    entries.append(entry)
    entries = entries[-MAX_ENTRIES:]
    _write_log(entries)

    print(f"Reset log ({len(entries)} entries): {entries}")
    return entries


def get_recent_resets():
    """Returns up to the last MAX_ENTRIES reset log entries (RAM-backed)."""
    return _read_log()[-MAX_ENTRIES:]
