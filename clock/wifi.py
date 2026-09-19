from secrets import secrets  # type: ignore

import board
import busio
from adafruit_esp32spi import adafruit_esp32spi, adafruit_esp32spi_wifimanager
from digitalio import DigitalInOut

import clock.dog as Dog
import clock.shared as Shared


def get_ip():
    try:
        if Shared.wifi:
            if callable(getattr(Shared.wifi, "ip_address", None)):
                return Shared.wifi.ip_address()
            return getattr(Shared.wifi, "ip_address", None)
    except Exception:
        pass
    return None


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
    try:
        Shared.wifi.connect()
        print("My IP address is", get_ip())
    except Exception as e:
        print(f"Initial WiFi connection failed: {e}")


def ensure_connected():
    if not Shared.esp.is_connected:
        print("WiFi lost, attempting reconnect...")
        Dog.feed()
        try:
            Shared.wifi.connect()
            Dog.feed()
            print("Reconnected to WiFi, IP:", get_ip())
            return True
        except Exception as e:
            Dog.feed()
            print(f"Failed to reconnect WiFi: {e}")
            return False
    return True
