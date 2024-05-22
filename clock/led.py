import neopixel
import board

import clock.shared as Shared


def setup():
    # ref: https://www.devdungeon.com/content/pyportal-circuitpy-tutorial-adabox-011#toc-27
    pixels = neopixel.NeoPixel(board.NEOPIXEL, 1, auto_write=True)
    Shared.pixels = pixels
    Shared.pixels[0] = (0, 0, 0)
    Shared.board_led.switch_to_output()
