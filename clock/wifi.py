from secrets import secrets  # type: ignore

import board
import busio
from adafruit_esp32spi import adafruit_esp32spi, adafruit_esp32spi_wifimanager
from digitalio import DigitalInOut

import clock.shared as Shared


def setup():
    esp32_cs = DigitalInOut(board.ESP_CS)
    esp32_ready = DigitalInOut(board.ESP_BUSY)
    esp32_reset = DigitalInOut(board.ESP_RESET)
    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)

    Shared.esp = adafruit_esp32spi.ESP_SPIcontrol(
        spi, esp32_cs, esp32_ready, esp32_reset
    )
    Shared.wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(
        Shared.esp, secrets, None
    )

    print("Connecting to WiFi...")
    Shared.wifi.connect()
    print("My IP address is", Shared.wifi.ip_address)
