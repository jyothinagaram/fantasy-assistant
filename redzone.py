"""
Who gets the ball near the end zone.

Touchdowns are the most random part of fantasy scoring -- except that they
are not random about WHO gets the chances. A running back who takes every
carry inside the 5-yard line will score far more than one who does all the
work between the 20s and watches the goal-line back finish the drive. Red-
zone opportunity is the best free predictor of future touchdowns there is.

From nflverse's free play-by-play (every snap of the season), for each
player:

  * red-zone opportunities -- carries plus targets inside the opponent's 20
  * goal-line opportunities -- the same inside the 5
  * his share of his team's red-zone opportunities

These are merged into the usage summary from `usage.py`, so they show up
wherever a player's usage line does. In the under-the-radar list a big red-
zone share is a small extra vote -- volume where touchdowns happen.
"""

import csv
import gzip
import io
import os
import time

import requests

import usage


URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz"
CACHE_HOURS = 6
RED_ZONE = 20
GOAL_LINE = 5


def download(season):
    path = os.path.join(usage.CACHE_DIR, f"nflverse_pbp_{season}.csv.gz")
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_HOURS * 3600
    if not fresh:
        try:
            response = requests.get(URL.format(season=season), timeout=120)
            response.raise_for_status()
            os.makedirs(usage.CACHE_DIR, exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(response.content)
        except Exception:
            if not os.path.exists(path):
                return None
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return handle.read()


def build(pbp_text, players_text):
    """{espn_id: red-zone summary}. Pure, for testing."""
    by_gsis, _ = usage.id_maps(players_text)
    players, teams = {}, {}   # gsis -> counts ; team -> red-zone opportunities

    reader = csv.DictReader(io.StringIO(pbp_text)) if pbp_text else []
    for play in reader:
        if play.get("season_type") != "REG":
            continue
        yardline = usage.number(play.get("yardline_100"))
        if yardline is None or yardline > RED_ZONE:
            continue
        if play.get("play_type") == "run" and play.get("rusher_player_id"):
            who = play["rusher_player_id"]
        elif play.get("play_type") == "pass" and play.get("receiver_player_id"):
            who = play["receiver_player_id"]
        else:
            continue
        team = play.get("posteam")
        counts = players.setdefault(who, {"red_zone": 0, "goal_line": 0, "team": team})
        counts["red_zone"] += 1
        if yardline <= GOAL_LINE:
            counts["goal_line"] += 1
        counts["team"] = team
        teams[team] = teams.get(team, 0) + 1

    out = {}
    for gsis, counts in players.items():
        espn = by_gsis.get(gsis)
        if espn is None:
            continue
        team_total = teams.get(counts["team"]) or 0
        out[espn] = {
            "red_zone_opps": counts["red_zone"],
            "goal_line_opps": counts["goal_line"],
            "red_zone_share": round(counts["red_zone"] / team_total, 3) if team_total else None,
        }
    return out


def load(season):
    players = usage.download("players", season)
    if not players:
        return {}
    return build(download(season), players)
