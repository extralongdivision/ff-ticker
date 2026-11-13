"""Display Scores of Followed Fantasy Football Leagues."""

# normal Python
import os
import ssl
import time

# CircuitPython specific
import adafruit_logging as logging
import adafruit_requests
import board
import displayio
import framebufferio
import neopixel
import rgbmatrix
import socketpool
import terminalio
import wifi

from adafruit_display_text.label import Label

class AbstractLogger:
    """Base logging class"""
    def __init__(self):
        self.logger = logging.getLogger(str(self))
        self.logger.setLevel(logging.INFO)


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
        # for league_id in env.league_ids:
        #     self._leagues.append(League(league_id=league_id, year=2026, espn_s2=env.espn_s2, swid=env.swid))

        # FIXME
        self.home_logo_fpath = "logos/503377474_3.bmp"
        self.home_abbv = "PRX"
        self.home_score = 7.4
        self.away_logo_fpath = "logos/503377474_1.bmp"
        self.away_abbv = "JTS"
        self.away_score = 0.0
        self.week_num = 10


class Display(AbstractLogger):
    """Driver of RGB Matrix."""

    def __init__(self):
        super().__init__()
        self.logger.info("Initializing Display class...")
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

    @property
    def width(self) -> int:
        return self._width


class Network(AbstractLogger):
    """WIFI, BLE, etc."""

    def __init__(self, env: Env):
        super().__init__()
        self.logger.info("Initializing Network class...")
        wifi.radio.connect(env.wifi_ssid, env.wifi_pw)
        self.logger.info(f"Connected to {env.wifi_ssid}")

        context = ssl.create_default_context()
        pool = socketpool.SocketPool(wifi.radio)
        self._requests = adafruit_requests.Session(pool, context)


class UI:
    """User Interface"""
    def __init__(self, ffdata: FantasyData):
        self._display = Display()
        self._ff_data = ffdata

    @staticmethod
    def splash() -> None:
        print("Fantasy Football     Scoreboard")

    def box_scores(self) -> None:
        home_logo_fpath = self._ff_data.home_logo_fpath
        home_abbv = self._ff_data.home_abbv
        home_score = self._ff_data.home_score
        away_logo_fpath = self._ff_data.away_logo_fpath
        away_abbv = self._ff_data.away_abbv
        away_score = self._ff_data.away_score
        week_num = self._ff_data.week_num

        group = displayio.Group()
        team_name_y = 37

        # "Home" team logo
        home_bitmap = displayio.OnDiskBitmap(home_logo_fpath)
        home_grid = displayio.TileGrid(home_bitmap, pixel_shader=home_bitmap.pixel_shader, x=0)
        group.append(home_grid)

        # "Home" team text
        home_text = Label(terminalio.FONT, color=self._display.font_color, text=home_abbv)
        home_text.anchor_point = (0.0, 0.5)
        home_text.anchored_position = (5, team_name_y)
        group.append(home_text)

        # "Away" team logo
        away_bitmap = displayio.OnDiskBitmap(away_logo_fpath)
        away_grid = displayio.TileGrid(away_bitmap, pixel_shader=away_bitmap.pixel_shader, x=94)
        group.append(away_grid)

        # "Away" team text
        away_text = Label(terminalio.FONT, color=self._display.font_color, text=away_abbv)
        away_text.anchor_point = (1.0, 0.5)
        away_text.anchored_position = (124, team_name_y)
        group.append(away_text)

        # Score text
        score_text = Label(terminalio.FONT, color=self._display.font_color, text=f"{home_score} - {away_score}")
        score_text.anchor_point = (0.5, 0.0)
        score_text.anchored_position = (self._display.width / 2, 14)
        group.append(score_text)

        # Week text
        week_text = Label(terminalio.FONT, color=self._display.font_color, text=f"Week {week_num}")
        week_text.anchor_point = (0.5, 0.5)
        week_text.anchored_position = (self._display.width / 2, team_name_y)
        group.append(week_text)

        self._display.framebuffer.root_group = group


class App:
    """Main Application Software"""

    def __init__(self, env: Env) -> None:
        self._ff_data = FantasyData(env)
        self.ui = UI(self._ff_data)

        self._fetch_timer = 300
        self._status_led = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness = 0.3, auto_write=True)

    def run(self) -> None:
        self.ui.splash()
        time.sleep(5)
        self.ui.box_scores()
        while True:
            pass

    @property
    def fetch_timer(self) -> int:
        return self._fetch_timer

    def set_fetch_timer(self, period: int) -> None:
        self._fetch_timer = period


if __name__ == "__main__":
    environ = Env()
    app = App(environ)
    app.run()