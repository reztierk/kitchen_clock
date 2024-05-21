import clock.shared as Shared

# ------- Stats  ------- #

def inc_counter(name):
    curr_value = Shared.counters.get(name, 0)
    Shared.counters[name] = curr_value + 1