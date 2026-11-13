"""Display Scores of Followed Fantasy Football Leagues."""

# normal Python
import os
import ssl

from espn_api.football import League

# CircuitPython specific
import adafruit_requests
import board
import displayio
import framebufferio
import neopixel
import rgbmatrix
import socketpool
import wifi


class Env:
    """Access host environment variables"""

    @property
    def espn_s2(self) -> str | None:
        return os.getenv("ESPN_S2")

    @property
    def swid(self) -> str | None:
        return os.getenv("SWID")

    @property
    def league_ids(self) -> list[int]:
        ids_str =  os.getenv("LEAGUE_IDS")
        ids_str = ids_str.replace("[", "")
        ids_str = ids_str.replace("]", "")
        ids = ids_str.split(",")
        return [int(i.strip()) for i in ids]

    @property
    def wifi_ssid(self) -> str | None:
        return os.getenv("CIRCUITPY_WIFI_SSID")

    @property
    def wifi_pw(self) -> str | None:
        return os.getenv("CIRCUITPY_WIFI_PASSWORD")


class FantasyData:
    """Fantasy Football Data"""

    def __init__(self, env: Env):
        self._leagues = []
        for league_id in env.league_ids:
            self._leagues.append(League(league_id=league_id, year=2026, espn_s2=env.espn_s2, swid=env.swid))

class Display:
    """Driver of RGB Matrix."""

    def __init__(self):
        print("Initializing Display class...")
        displayio.release_displays()

        self.font_color = 0xFFFFFF
        self._refresh_timer = 300

        # RGB Matrix setup
        self._base_width = 64
        self._base_height = 32
        self._chain_across = 2
        self._tile_down = 2
        self._width = self._base_width * self._chain_across
        self._height = self._base_height * self._tile_down
        self._matrix = rgbmatrix.RGBMatrix(
            width=self._width, height=self._height, bit_depth=3,
            rgb_pins=[
                board.MTX_R1,
                board.MTX_G1,
                board.MTX_B1,
                board.MTX_R2,
                board.MTX_G2,
                board.MTX_B2
            ],
            addr_pins=[
                board.MTX_ADDRA,
                board.MTX_ADDRB,
                board.MTX_ADDRC,
                board.MTX_ADDRD
            ],
            clock_pin=board.MTX_CLK,
            latch_pin=board.MTX_LAT,
            output_enable_pin=board.MTX_OE,
            tile=self._tile_down, serpentine=True,
            doublebuffer=False
        )
        self.framebuffer = framebufferio.FramebufferDisplay(self._matrix)

    @property
    def refresh_timer(self) -> int:
        return self._refresh_timer

    def set_refresh_timer(self, period: int) -> None:
        self._refresh_timer = period


class Network:
    """WIFI, BLE, etc."""

    def __init__(self, env: Env):
        print("Initializing Network class...")
        wifi.radio.connect(env.wifi_ssid, env.wifi_pw)
        print(f"Connected to {env.wifi_ssid}")

        context = ssl.create_default_context()
        pool = socketpool.SocketPool(wifi.radio)
        self._requests = adafruit_requests.Session(pool, context)


class UI:
    """User Interface"""
    def __init__(self, ffdata: FantasyData):
        self._display = Display()
        self._ff_data = ffdata

    def splash(self) -> None:
        print("Fantasy Football     Ticker")
        for league in self._ff_data._leagues:
            print(league)


class App:
    """Main Application Software"""

    def __init__(self, env: Env) -> None:
        self._ff_data = FantasyData(env)
        self.ui = UI(self._ff_data)

        self._fetch_timer = 300
        self._status_led = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness = 0.3, auto_write=True)

    def run(self) -> None:
        self.ui.splash()

    @property
    def fetch_timer(self) -> int:
        return self._fetch_timer

    def set_fetch_timer(self, period: int) -> None:
        self._fetch_timer = period


if __name__ == "__main__":
    environ = Env()
    app = App(environ)
    app.run()
    while 1:
        pass