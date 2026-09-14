"""
What the experts think about the REST OF THE SEASON.

Waivers and trades are rest-of-season decisions, but until now the only
rest-of-season number they had was ESPN's season projection -- one opinion,
and slow to react. A backup who just inherited a starting job keeps his
backup projection at ESPN for weeks.

FantasyPros publishes a rest-of-season consensus, one page per position,
rebuilt through the season by its panel of analysts. Crucially it comes with
their projected fantasy points for the rest of the season (`r2p_pts`), not
just a rank, so it can be put side by side with ESPN's number in the same
unit -- no guessing how many points "WR34" is worth.

That total is turned into points per game by dividing by the games the
player has left (remaining regular-season weeks, minus his bye if it is
still to come). `waivers.per_game_value` then averages it 50/50 with ESPN's
projection, exactly as start/sit averages the two weekly projections.

Same manners as the other FantasyPros readers: the five-second crawl delay,
a cache (12 hours -- these lists move over days, not hours), and a quiet
fall back to ESPN alone if the site cannot be reached.
"""

import json
import os
import re
import statistics
import time

import outside_rankings as season_rankings
import weekly_rankings


PAGES = {
    "QB": "ros-qb.php",
    "K": "ros-k.php",
    "D/ST": "ros-dst.php",
    "RB": {"PPR": "ros-ppr-rb.php", "HALF": "ros-half-point-ppr-rb.php", "STD": "ros-rb.php"},
    "WR": {"PPR": "ros-ppr-wr.php", "HALF": "ros-half-point-ppr-wr.php", "STD": "ros-wr.php"},
    "TE": {"PPR": "ros-ppr-te.php", "HALF": "ros-half-point-ppr-te.php", "STD": "ros-te.php"},
}

CACHE_HOURS = 12

# The NFL regular season, for counting games left.
LAST_NFL_WEEK = 18

# FantasyPros' totals run about 10% above ESPN's at every position (checked
# 2026-09-14 across two leagues: QB 1.10, RB 1.08-1.10, WR 1.10, TE 1.14, K
# 1.01) -- a difference of scale, not of opinion, most likely because the
# totals still include games already played. Left alone, every player the
# experts rank would get a free boost over the ones they do not. So the
# expert numbers are rescaled, per position, so that the typical player
# matches ESPN; what survives is the experts' actual opinion -- who they
# rate above or below ESPN.
MIN_PLAYERS_TO_CALIBRATE = 5
CALIBRATION_FLOOR = 5.0   # only players ESPN projects for real points


def page_url(position, scoring):
    page = PAGES.get(position)
    if page is None:
        return None
    if isinstance(page, dict):
        page = page[scoring]
    return weekly_rankings.BASE_URL + page


def cache_path(position, scoring, season):
    safe = position.replace("/", "").lower()
    return os.path.join(season_rankings.CACHE_DIR, f"ros_{safe}_{scoring.lower()}_{season}.json")


def read_cache(path, max_age_hours):
    try:
        if (time.time() - os.path.getmtime(path)) / 3600 > max_age_hours:
            return None
        with open(path) as handle:
            return json.load(handle)["players"]
    except (OSError, ValueError, KeyError):
        return None


def download(position, scoring):
    response = season_rankings.polite_get(page_url(position, scoring))
    response.raise_for_status()
    match = re.search(r"var\s+ecrData\s*=\s*(\{.*?\});\s*\n", response.text, re.S)
    if not match:
        raise RuntimeError("FantasyPros changed their page layout")
    data = json.loads(match.group(1))
    if data.get("ranking_type_name") not in (None, "ros"):
        raise RuntimeError(f"expected rest-of-season rankings, got {data.get('ranking_type_name')}")
    players = data.get("players") or []
    if not players:
        raise RuntimeError("FantasyPros returned an empty list")
    return players


def rankings_for_position(position, scoring, season, force_refresh=False):
    path = cache_path(position, scoring, season)
    if not force_refresh:
        cached = read_cache(path, CACHE_HOURS)
        if cached:
            return cached
    try:
        players = download(position, scoring)
    except Exception:
        return read_cache(path, max_age_hours=24 * 7)  # a few days old beats nothing
    try:
        os.makedirs(season_rankings.CACHE_DIR, exist_ok=True)
        with open(path, "w") as handle:
            json.dump({"players": players}, handle)
    except OSError:
        pass
    return players


def load_for_league(league, season, force_refresh=False):
    """Every position's rest-of-season list in this league's scoring format."""
    scoring = season_rankings.scoring_key(league)
    out = {}
    for position in PAGES:
        players = rankings_for_position(position, scoring, season, force_refresh)
        if players:
            out[position] = players
    return out


def games_left(first_week, bye_week):
    """Games a player still has to play, counting from `first_week`."""
    games = max(0, LAST_NFL_WEEK - first_week + 1)
    if bye_week and bye_week >= first_week:
        games -= 1
    return games


def attach(players, by_position, first_week):
    """
    Writes each player's rest-of-season expert numbers onto him, in place:
    `ros_expert_avg` (points per game), `ros_pos_rank` and `ros_spread`.
    Players FantasyPros does not rank get None, which leaves ESPN's
    projection standing alone.
    """
    by_name, by_defense_team = weekly_rankings.build_lookup(by_position)
    matched = 0
    for player in players:
        position = player.get("position")
        if position == "D/ST":
            entry = by_defense_team.get(season_rankings.normalize_team(player.get("pro_team")))
        else:
            entry = by_name.get(
                (position, season_rankings.normalize_name(player.get("name") or ""))
            )

        total = season_rankings.to_number(entry.get("r2p_pts"), None) if entry else None
        games = games_left(first_week, player.get("bye_week"))
        if entry is None or total is None or games <= 0:
            player.update(ros_expert_avg=None, ros_pos_rank=None, ros_spread=None)
            continue

        matched += 1
        player.update(
            ros_expert_avg=round(total / games, 2),
            ros_pos_rank=entry.get("pos_rank"),
            ros_spread=season_rankings.to_number(entry.get("rank_std"), None),
        )

    scales = calibrate(players)
    return {"matched": matched, "total": len(players), "scales": scales}


def calibrate(players):
    """
    Rescales `ros_expert_avg` in place so the typical player at each position
    matches ESPN's scale. Returns the factor removed per position.
    """
    ratios = {}
    for player in players:
        espn = player.get("season_projected_avg") or 0.0
        expert = player.get("ros_expert_avg")
        if expert and espn >= CALIBRATION_FLOOR:
            ratios.setdefault(player.get("position"), []).append(expert / espn)

    scales = {
        position: statistics.median(values)
        for position, values in ratios.items()
        if len(values) >= MIN_PLAYERS_TO_CALIBRATE
    }
    for player in players:
        scale = scales.get(player.get("position"))
        if scale and player.get("ros_expert_avg") is not None:
            player["ros_expert_avg"] = round(player["ros_expert_avg"] / scale, 2)
    return {position: round(scale, 3) for position, scale in scales.items()}
