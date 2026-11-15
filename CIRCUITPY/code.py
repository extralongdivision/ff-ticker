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


class FantasyData(AbstractLogger):
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

            def __str__(self) -> str:
                return f"{self.home_abbv} ({self.home_score}) - ({self.away_score}) {self.away_abbv}"

        def __init__(self, league_id: int, network: "Network"):
            super().__init__()
            self._network = network
            self._league_id = league_id
            self._headers = {"cookie": f"SWID={os.getenv('SWID')}; espn_s2={os.getenv('ESPN_S2')}"}
            self._year = ""
            self._update_year()
            self.matchups = self._fetch_matchups()

        def _fetch_matchups(self) -> list["Matchup"]:
            teams = self._fetch_teams()
            week = teams["week"] - 1 # TODO make this show current week live scores
            r = self._network.get(self._matchup_url, headers=self._headers)
            if not (r.status_code == 200):
                self.logger.error(f"Failed to query ESPN Matchup API ({r.status_code})")
                return []

            match_data = json_stream.load(r.iter_content(4096))
            matchups = []
            for m in match_data["schedule"]:
                # have to access this first or else I'll get KeyError
                away_team_id = m["away"]["teamId"]
                away_total_points = m["away"]["totalPoints"]
                try:
                    away_points_by = m["away"]["pointsByScoringPeriod"][week]
                except KeyError:  # the match is still UNDECIDED or not this week's matchup
                    away_points_by = None

                home_team_id = m["home"]["teamId"]
                home_total_points = m["home"]["totalPoints"]
                try:
                    home_points_by = m["home"]["pointsByScoringPeriod"][week]
                except KeyError:  # the match is still UNDECIDED or not this week's matchup
                    home_points_by = None

                if m["matchupPeriodId"] != week:
                    continue

                matchup = self.Matchup(week=week)
                matchup.away_score = away_total_points if away_points_by is None else away_points_by
                matchup.away_logo_fpath = f"logos/{self._league_id}_{away_team_id}.bmp"
                matchup.away_abbv = teams[int(away_team_id)]
                matchup.home_score = home_total_points if home_points_by is None else home_points_by
                matchup.home_logo_fpath = f"logos/{self._league_id}_{home_team_id}.bmp"
                matchup.home_abbv = teams[int(home_team_id)]
                matchups.append(matchup)
            r.close()
            return matchups

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
        super().__init__()
        self._leagues = []
        self._league_idx = 0
        self._num_leagues = len(env.league_ids)
        self._matchup_idx = 0
        self._num_matchups = 0
        self._env = env
        self._network = network

    def fetch(self):
        """New data from external APIs"""
        self._leagues = []
        for league_id in self._env.league_ids:
            self._leagues.append(self.League(league_id, self._network))
        self._num_matchups = len(self._current_league.matchups)
        self.logger.debug(f"Num leagues is {self._num_matchups}")

        self.update()

    def update(self):
        """Store current matchups"""
        self.home_logo_fpath = self._current_matchup.home_logo_fpath
        self.home_abbv = self._current_matchup.home_abbv
        self.home_score = self._current_matchup.home_score
        self.away_logo_fpath = self._current_matchup.away_logo_fpath
        self.away_abbv = self._current_matchup.away_abbv
        self.away_score = self._current_matchup.away_score
        self.week_num = self._current_matchup.week_num

    def next_league(self):
        new_idx = self._league_idx + 1
        self.logger.debug(f"New idx is {new_idx}")
        if new_idx >= self._num_leagues:
            self._league_idx = 0
        else:
            self._league_idx = new_idx
        self.logger.debug(f"New league idx is {self._league_idx}")
        self.update()

    def next_matchup(self):
        new_idx = self._matchup_idx + 1
        self.logger.debug(f"New idx is {new_idx}")
        if new_idx >= self._num_matchups:
            self._matchup_idx = 0
            self.next_league()
        else:
            self._matchup_idx = new_idx
            self.update()
        self.logger.debug(f"New matchup idx is {self._matchup_idx}")

    @property
    def _current_league(self) -> League:
        return self._leagues[self._league_idx]

    @property
    def _current_matchup(self) -> "Matchup":
        return self._current_league.matchups[self._matchup_idx]


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
    def __init__(self):
        self._display = Display()
        # self._ff_data = ffdata

    @staticmethod
    def splash() -> None:
        print("Fantasy Football     Scoreboard")

    def box_score(self, data: FantasyData) -> None:
        home_logo_fpath = data.home_logo_fpath
        home_abbv = data.home_abbv
        home_score = data.home_score
        away_logo_fpath = data.away_logo_fpath
        away_abbv = data.away_abbv
        away_score = data.away_score
        week_num = data.week_num

        group = displayio.Group()
        team_name_y = 37

        # "Home" team logo
        home_bitmap = displayio.OnDiskBitmap(home_logo_fpath)
        home_grid = displayio.TileGrid(home_bitmap, pixel_shader=home_bitmap.pixel_shader, x=0)
        group.append(home_grid)

        # "Home" team text
        home_text = Label(terminalio.FONT, color=self._display.font_color, text=home_abbv)
        home_text.anchor_point = (0.0, 0.5)
        home_text.anchored_position = (1, team_name_y)
        group.append(home_text)

        # "Away" team logo
        away_bitmap = displayio.OnDiskBitmap(away_logo_fpath)
        away_grid = displayio.TileGrid(away_bitmap, pixel_shader=away_bitmap.pixel_shader, x=94)
        group.append(away_grid)

        # "Away" team text
        away_text = Label(terminalio.FONT, color=self._display.font_color, text=away_abbv)
        away_text.anchor_point = (1.0, 0.5)
        away_text.anchored_position = (128, team_name_y)
        group.append(away_text)

        # Home score text
        home_score_text = Label(terminalio.FONT, color=self._display.font_color, text=str(home_score))
        home_score_text.anchor_point = (1, 0.5)
        home_score_text.anchored_position = ((self._display.width / 2) - 4, team_name_y)
        group.append(home_score_text)

        # Dash text
        dash_text = Label(terminalio.FONT, color=self._display.font_color, text=f"-")
        dash_text.anchor_point = (0.5, 0.5)
        dash_text.anchored_position = (self._display.width / 2, team_name_y)
        group.append(dash_text)

        # Away score text
        away_score_text = Label(terminalio.FONT, color=self._display.font_color, text=str(away_score))
        away_score_text.anchor_point = (0, 0.5)
        away_score_text.anchored_position = ((self._display.width / 2) + 4, team_name_y)
        group.append(away_score_text)

        # Week text
        week_text = Label(terminalio.FONT, color=self._display.font_color, text=f"Week {week_num}")
        week_text.anchor_point = (0.5, 0.5)
        week_text.anchored_position = (self._display.width / 2, 14)
        group.append(week_text)

        self._display.framebuffer.root_group = group


class App:
    """Main Application Software"""

    def __init__(self, env: Env) -> None:
        self._ff_data = FantasyData(env, Network(env))
        self.ui = UI()

        self._fetch_timer = 300
        self._status_led = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness = 0.3, auto_write=True)

    def run(self) -> None:
        self.ui.splash()
        self._ff_data.fetch()
        while True:
            self.ui.box_score(self._ff_data)
            time.sleep(5)  # FIXME track time instead of sleeping
            self._ff_data.next_matchup()

    @property
    def fetch_timer(self) -> int:
        return self._fetch_timer

    def set_fetch_timer(self, period: int) -> None:
        self._fetch_timer = period


if __name__ == "__main__":
    environ = Env()
    app = App(environ)
    app.run()