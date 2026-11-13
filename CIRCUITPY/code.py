"""Display Scores of Followed Fantasy Football Leagues."""

# normal Python
import os
import ssl
import time

# CircuitPython specific
import adafruit_json_stream as json_stream
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

    class League(AbstractLogger):
        """Fantasy Football League"""

        class Matchup:
            """Data from a weekly matchup"""

            def __init__(self, h_logo_fpath: str = "", h_abbv: str = "", h_score: float = 0.0, a_logo_fpath: str = "",
                         a_abbv: str = "",
                         a_score: float = 0.0, week: int = 1):
                self.home_logo_fpath = h_logo_fpath
                self.home_abbv = h_abbv
                self.home_score = h_score
                self.away_logo_fpath = a_logo_fpath
                self.away_abbv = a_abbv
                self.away_score = a_score
                self.week_num = week

        def __init__(self, league_id: int, network: "Network"):
            super().__init__()
            self._network = network
            self._league_id = league_id
            self._headers = {"cookie": f"SWID={os.getenv('SWID')}; espn_s2={os.getenv('ESPN_S2')}"}
            self._year = ""
            self._update_year()
            self._matchups = self._fetch_matchups()

        def _fetch_matchups(self) -> list["Matchup"]:
            teams = self._fetch_teams()
            week = teams["week"]
            r = self._network.get(self._matchup_url, headers=self._headers)
            if not (r.status_code == 200):
                self.logger.error(f"Failed to query ESPN Matchup API ({r.status_code})")
                return []

            match_data = json_stream.load(r.iter_content(32))
            matches_data = []
            for m in match_data["schedule"]:
                if m["matchupPeriodId"] != week:
                    continue
                matches_data.append(m)
                break

            matchups = []
            for idx, match in enumerate(match_data):
                matchups.append(self.Matchup(week=week))
                matchup = matchups[idx]

                home_team_id = match["home"]["teamId"]
                matchup.home_logo_fpath = f"logos/{self._league_id}_{home_team_id}.bmp"
                matchup.home_abbv = teams[int(home_team_id)]

                away_team_id = match["away"]["teamId"]
                matchup.away_logo_fpath = f"logos/{self._league_id}_{away_team_id}.bmp"
                matchup.away_abbv = teams[int(away_team_id)]
                if match["winner"] != "UNDECIDED":
                    pass
                matchup.home_score = 0.0
                matchup.away_score = 0.0

            print(m)
            self.logger.info(m)

        def _fetch_teams(self) -> dict:
            self.logger.debug("Fetching matchups...")
            r = self._network.get(self._league_url, headers=self._headers)
            if not (r.status_code == 200):
                self.logger.error(f"Failed to query ESPN League API ({r.status_code}) ({self._league_url})")
                return {}
            data = r.json()
            teams_data = {"week": data["scoringPeriodId"]}
            [teams_data.update({team["id"]: team["abbrev"]}) for team in data["teams"]]
            r.close()
            return teams_data

        def _update_year(self) -> None:
            r = self._network.get(self._base_url, headers=self._headers)
            if not (r.status_code == 200):
                self._year = "2026"
            self._year = r.json()[0]["abbrev"][-4:]

        @property
        def _base_url(self) -> str:
            return "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"

        @property
        def _league_url(self) -> str:
            return self._base_url + f"{self._year}/segments/0/leagues/{self._league_id}/"

        @property
        def _matchup_url(self) -> str:
            return self._league_url + "?view=mMatchup"


    def __init__(self, env: Env, network: "Network"):
        self._leagues = []
        self._league_idx = 0
        self._num_leagues = len(env.league_ids)
        self._env = env
        self._network = network

    def update(self):
        self._leagues = []
        for league_id in self._env.league_ids:
            self._leagues.append(self.League(league_id, self._network))


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

    def get(self, url: str, headers: dict[str, str]) -> adafruit_requests.Response:
        return self._requests.get(url, headers=headers)


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
        self._ff_data = FantasyData(env, Network(env))
        self.ui = UI(self._ff_data)

        self._fetch_timer = 300
        self._status_led = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness = 0.3, auto_write=True)

    def run(self) -> None:
        self.ui.splash()
        self._ff_data.update()
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