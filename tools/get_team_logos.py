"""Get the Fantasy Team Logos"""
import datetime
import json
import math
import os
import requests
import shutil

from cairosvg import svg2png
from espn_api.football import League
from PIL import Image, UnidentifiedImageError


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


class RGBify:
    """Make Images Better for LED Matrix"""

    def __init__(self):
        self._gamma = 2.6
        self._passthrough = ((0, 0, 0),
               (255, 0, 0),
               (255, 255, 0),
               (0, 255, 0),
               (0, 255, 255),
               (0, 0, 255),
               (255, 0, 255),
               (255, 255, 255))

    def process(self, fpath: str) -> None:
        """
        originally written by Phil B. for Adafruit Industries
        https://raw.githubusercontent.com/adafruit/Adafruit_Media_Converters/master/protomatter_dither.py
        """

        # resize and close
        try:
            img = Image.open(fpath)
        except UnidentifiedImageError:
            svg2png(file_obj = open(fpath, "rb"), write_to = f"{fpath}")
            img = Image.open(fpath)

        img_resized = img.resize((32, 32))
        img_resized.save(fpath)

        img_rbg = img_resized.convert("RGB")
        err_next_pixel = (0, 0, 0)
        err_next_row = [(0, 0, 0) for _ in range(img_rbg.size[0])]
        for row in range(img_rbg.size[1]):
            for column in range(img_rbg.size[0]):
                pixel = img_rbg.getpixel((column, row))
                want = (math.pow(pixel[0] / 255.0, self._gamma) * 31.0,
                        math.pow(pixel[1] / 255.0, self._gamma) * 63.0,
                        math.pow(pixel[2] / 255.0, self._gamma) * 31.0)
                if pixel in self._passthrough:
                    got = (pixel[0] >> 3,
                           pixel[1] >> 2,
                           pixel[2] >> 3)
                else:
                    got = (min(max(int(err_next_pixel[0] * 0.5 +
                                       err_next_row[column][0] * 0.25 +
                                       want[0] + 0.5), 0), 31),
                           min(max(int(err_next_pixel[1] * 0.5 +
                                       err_next_row[column][1] * 0.25 +
                                       want[1] + 0.5), 0), 63),
                           min(max(int(err_next_pixel[2] * 0.5 +
                                       err_next_row[column][2] * 0.25 +
                                       want[2] + 0.5), 0), 31))
                err_next_pixel = (want[0] - got[0],
                                  want[1] - got[1],
                                  want[2] - got[2])
                err_next_row[column] = err_next_pixel
                rgb565 = ((got[0] << 3) | (got[0] >> 2),
                          (got[1] << 2) | (got[1] >> 4),
                          (got[2] << 3) | (got[2] >> 2))
                img_rbg.putpixel((column, row), rgb565)

        img_rbg = img_rbg.convert('P', palette=Image.ADAPTIVE)
        img_rbg.save(os.path.splitext(fpath)[0] + ".bmp")
        os.remove(fpath)


if __name__ == "__main__":
    env = Env()
    leagues = []
    current_year = datetime.datetime.now().year
    rgbifier = RGBify()

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
            rgbifier.process(filepath)