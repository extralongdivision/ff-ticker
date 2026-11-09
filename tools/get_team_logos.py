import datetime
import json
import os
import requests
import shutil

from espn_api.football import League


class Env:
    """Access host environment variables"""
    def __init__(self):
        self._env_filepath = ".env"
        self._espn_s2_key = "espn_s2"
        self._swid_key = "SWID"
        self._league_ids_key = "league_ids"

        self.espn_s2 = ""
        self.swid = ""
        self.league_ids = []

        self.read_env()

    def read_env(self) -> None:
        if not os.path.exists(self._env_filepath):
            raise RuntimeError("Rename .env.template and fill it with your credentials")

        with open(self._env_filepath) as fin:
            env_dict = json.load(fin)
            self.espn_s2 = env_dict[self._espn_s2_key]
            self.swid = env_dict[self._swid_key]
            self.league_ids = env_dict[self._league_ids_key]


if __name__ == "__main__":
    env = Env()
    leagues = []
    current_year = datetime.datetime.now().year

    base_dir = "logos"
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    for league_id in env.league_ids:
        league = League(league_id=league_id, year=current_year, espn_s2=env.espn_s2, swid=env.swid)
        for team in league.teams:
            img_url = team.logo_url
            cookies = {"espn_s2": env.espn_s2, "SWID": env.swid}
            response = requests.get(img_url, cookies=cookies, stream=True)
            if not response.ok:
                print(f"Could not download logo for {team.team_name}")
                continue

            filepath = os.sep.join([base_dir, f"{league_id}_{team.team_id}.png"])
            with open(filepath, "wb") as fout:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, fout)