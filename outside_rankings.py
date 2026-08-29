"""
Brings in what the experts think, from outside ESPN.

Up to now every number this tool produced came from ESPN itself. That is a
real blind spot: ESPN's projections are one opinion, and they are famously
slow to react to news. This file adds a second opinion -- the FantasyPros
"expert consensus ranking" (ECR), which is roughly a hundred fantasy
analysts' draft boards averaged together.

Three things come back that ESPN cannot tell us:

  1. Where the experts rank a player overall.
  2. How much the experts DISAGREE about him. FantasyPros publishes the
     highest and lowest rank any single expert gave, plus the spread. A
     player everyone ranks around 40th is a safe pick; a player ranked
     anywhere from 20th to 90th is a gamble. That is worth knowing before
     you spend a pick.
  3. A sanity check on ESPN. Where ESPN's projections and the experts
     disagree sharply, that is usually news ESPN has not priced in yet.

Rankings are pulled per scoring format, because a full-PPR board and a
half-PPR board are genuinely different lists -- which matters to you, since
D.C.F. is full PPR and your other two leagues are half.

If FantasyPros cannot be reached, everything here fails quietly and the tool
falls back to the ESPN-only board it has always produced. Nothing about the
draft should ever depend on a website being up.
"""

import json
import os
import re
import threading
import time

import requests


# FantasyPros publishes a separate cheat sheet per scoring format. The
# rankings themselves are embedded in the page as a chunk of JSON.
SCORING_URLS = {
    "PPR": "https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php",
    "HALF": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php",
    "STD": "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
}

CACHE_DIR = "cache"

# How long a download stays good for. Expert rankings move over a season but
# not minute to minute, and on draft day you want the tool starting fast and
# not depending on a website. Re-run with force_refresh to override.
CACHE_HOURS = 12

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

# ESPN and FantasyPros spell two teams differently. Left is FantasyPros.
TEAM_ALIASES = {"JAC": "JAX", "WAS": "WSH", "LA": "LAR"}

# FantasyPros' robots.txt asks automated visitors to leave five seconds
# between requests, so we do. In practice this costs nothing -- a session
# downloads at most two or three pages and then reuses them for hours -- but
# being a well-behaved guest on someone else's website is worth five seconds.
CRAWL_DELAY_SECONDS = 5

_last_request_at = 0.0
_request_lock = threading.Lock()


def polite_get(url):
    """
    Fetches a page, never sooner than five seconds after the last one
    finished.

    The wait is measured from the END of the previous request, so there are
    always a full five quiet seconds in between. The lock is held across the
    whole fetch, so two boards being built at the same time queue up rather
    than firing together.
    """
    global _last_request_at
    with _request_lock:
        waiting = CRAWL_DELAY_SECONDS - (time.time() - _last_request_at)
        if waiting > 0:
            time.sleep(waiting)
        try:
            return requests.get(url, headers=BROWSER_HEADERS, timeout=30)
        finally:
            _last_request_at = time.time()


# ---------------------------------------------------------------------------
# Which list to pull
# ---------------------------------------------------------------------------

def scoring_key(league):
    """
    Works out which FantasyPros list matches this league, from what the
    league pays for a reception.
    """
    reception_points = next(
        (
            rule["points"]
            for rule in league.settings.scoring_format
            if rule.get("abbr") == "REC"
        ),
        0.0,
    )
    if reception_points >= 1.0:
        return "PPR"
    if reception_points > 0:
        return "HALF"
    return "STD"


# ---------------------------------------------------------------------------
# Getting the rankings, with a cache so draft day never waits on a website
# ---------------------------------------------------------------------------

def cache_path(scoring, season):
    return os.path.join(CACHE_DIR, f"fantasypros_{scoring.lower()}_{season}.json")


def read_cache(scoring, season, max_age_hours):
    """Returns cached rankings if they exist and are recent enough."""
    path = cache_path(scoring, season)
    try:
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        if age_hours > max_age_hours:
            return None
        with open(path) as handle:
            return json.load(handle)["players"]
    except (OSError, ValueError, KeyError):
        return None


def write_cache(scoring, season, players):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path(scoring, season), "w") as handle:
            json.dump({"scoring": scoring, "season": season, "players": players}, handle)
    except OSError:
        pass  # a cache we cannot write is an inconvenience, not a failure


def download(scoring):
    """
    Fetches one FantasyPros cheat sheet and pulls the rankings out of it.

    The page ships its rankings as a JavaScript variable called ecrData, so
    we ask for the page and lift the JSON straight out of the source rather
    than trying to read the rendered table.
    """
    response = polite_get(SCORING_URLS[scoring])
    response.raise_for_status()

    match = re.search(r"var\s+ecrData\s*=\s*(\{.*?\});\s*\n", response.text, re.S)
    if not match:
        raise RuntimeError("FantasyPros changed their page layout")

    players = json.loads(match.group(1)).get("players") or []
    if not players:
        raise RuntimeError("FantasyPros returned an empty list")
    return players


def expert_rankings(scoring, season, max_age_hours=CACHE_HOURS, force_refresh=False):
    """
    The expert consensus list for one scoring format.

    Returns None -- never raises -- if the rankings cannot be had at all, so
    that a website being down can never stop you drafting.
    """
    if not force_refresh:
        cached = read_cache(scoring, season, max_age_hours)
        if cached:
            return cached

    try:
        players = download(scoring)
    except Exception:
        # Out of date is far better than nothing, so fall back to any cache
        # we have regardless of age.
        return read_cache(scoring, season, max_age_hours=10 ** 6)

    write_cache(scoring, season, players)
    return players


# ---------------------------------------------------------------------------
# Matching FantasyPros players to ESPN players
# ---------------------------------------------------------------------------

# Suffixes that one site prints and the other does not.
SUFFIXES = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def normalize_name(name):
    """
    Reduces a name to something both sites will agree on: lowercase, no
    punctuation, no Jr/III. "Ja'Marr Chase" and "JaMarr Chase" both become
    "jamarr chase".
    """
    text = name.lower().replace("&", "and")
    text = re.sub(r"[.'`’-]", "", text)
    text = SUFFIXES.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_team(code):
    code = (code or "").upper()
    return TEAM_ALIASES.get(code, code)


def build_lookup(experts):
    """
    Two ways to find an expert entry: by name for real players, and by team
    for defenses.

    Defenses need their own path because the two sites name them completely
    differently -- ESPN calls it "Broncos D/ST" and FantasyPros calls it
    "Denver Broncos" -- but they agree on the team code, and a team only has
    one defense.
    """
    by_name, by_defense_team = {}, {}

    for entry in experts:
        position = (entry.get("player_position_id") or "").upper()
        if position == "DST":
            by_defense_team.setdefault(normalize_team(entry.get("player_team_id")), entry)
        else:
            by_name.setdefault(normalize_name(entry.get("player_name") or ""), entry)

    return by_name, by_defense_team


def attach(players, experts):
    """
    Writes the expert numbers onto each ESPN player, in place.

    Players the experts do not rank at all get counted as ranked just past
    the end of the list. That is deliberate rather than neutral: if a hundred
    analysts all left someone off a 500-deep board, that is a real opinion
    about him, not missing data.

    Returns a small summary so callers can tell you how it went.
    """
    by_name, by_defense_team = build_lookup(experts)
    unranked_rank = len(experts) + 1
    matched = 0

    for player in players:
        if player["position"] == "D/ST":
            entry = by_defense_team.get(normalize_team(player["pro_team"]))
        else:
            entry = by_name.get(normalize_name(player["name"]))

        if entry is None:
            player["ecr"] = unranked_rank
            player["ecr_best"] = None
            player["ecr_worst"] = None
            player["ecr_spread"] = None
            player["ecr_pos_rank"] = None
            player["expert_ranked"] = False
            continue

        matched += 1
        player["ecr"] = to_number(entry.get("rank_ecr"), unranked_rank)
        player["ecr_best"] = to_number(entry.get("rank_min"), None)
        player["ecr_worst"] = to_number(entry.get("rank_max"), None)
        player["ecr_spread"] = to_number(entry.get("rank_std"), None)
        player["ecr_pos_rank"] = entry.get("pos_rank")
        player["expert_ranked"] = True

    return {
        "matched": matched,
        "total": len(players),
        "experts_listed": len(experts),
        "unranked_rank": unranked_rank,
    }


def to_number(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_for_league(league, season, force_refresh=False):
    """
    Convenience wrapper: the right list for this league's scoring, or None.
    """
    scoring = scoring_key(league)
    return scoring, expert_rankings(scoring, season, force_refresh=force_refresh)
