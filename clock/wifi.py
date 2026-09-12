from secrets import secrets  # type: ignore

import board
import busio
from adafruit_esp32spi import adafruit_esp32spi, adafruit_esp32spi_wifimanager
from digitalio import DigitalInOut

import clock.dog as Dog
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
        Shared.esp, secrets, None, attempts=1
    )

    print("Connecting to WiFi...")
    Shared.wifi.connect()
    try:
        print("My IP address is", Shared.wifi.ip_address())
    except Exception as e:
        print(f"Could not get IP address: {e}")


def ensure_connected():
    if not Shared.esp.is_connected:
        print("WiFi lost, attempting reconnect...")
        Dog.feed()
        try:
            Shared.wifi.connect()
            Dog.feed()
            print("Reconnected to WiFi, IP:", Shared.wifi.ip_address())
            return True
        except Exception as e:
            Dog.feed()
            print(f"Failed to reconnect WiFi: {e}")
            return False
    return True
