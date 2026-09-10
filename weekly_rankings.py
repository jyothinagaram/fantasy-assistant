"""
What the experts think about THIS WEEK.

`outside_rankings.py` pulls FantasyPros' season-long draft board. That was
the right list in August and it is the wrong list now: nobody setting a
Week 1 lineup cares where a player was drafted, they care who he plays on
Sunday and whether he is healthy.

So this pulls FantasyPros' *weekly* rankings instead -- a different list,
rebuilt every week by the same ~100 analysts, one page per position.

Three things come back that ESPN's projection cannot tell us:

  1. A second projection. FantasyPros publishes its own point estimate
     (`r2p_pts`) next to each player. Where that disagrees with ESPN, one
     of them is reacting to news the other has not priced in yet -- and
     the experts are usually the faster of the two.
  2. How much the experts disagree about him this week (the spread between
     the highest and lowest rank any single analyst gave). A wide spread on
     a Sunday means the people who watch this player for a living cannot
     agree whether he plays, or whether he matters.
  3. Which way his stock is moving (`player_ecr_delta`) -- how far his rank
     shifted since the list was last rebuilt. A player who jumped 15 spots
     in three days is a player something happened to.

Same manners as the draft version: the polite five-second crawl delay is
reused from `outside_rankings`, results are cached, and if FantasyPros
cannot be reached this fails quietly and the board falls back to ESPN's
numbers alone. A website being down should never stop you setting a lineup.
"""

import json
import os
import re
import time

import outside_rankings as season_rankings


# One page per position. FantasyPros only varies the scoring format for the
# positions where receptions actually matter -- a quarterback's ranking is
# the same list whether or not the league pays for catches -- so QB, K and
# D/ST have a single page each.
PAGES = {
    "QB": "qb.php",
    "K": "k.php",
    "D/ST": "dst.php",
    "RB": {"PPR": "ppr-rb.php", "HALF": "half-point-ppr-rb.php", "STD": "rb.php"},
    "WR": {"PPR": "ppr-wr.php", "HALF": "half-point-ppr-wr.php", "STD": "wr.php"},
    "TE": {"PPR": "ppr-te.php", "HALF": "half-point-ppr-te.php", "STD": "te.php"},
}

BASE_URL = "https://www.fantasypros.com/nfl/rankings/"

# Weekly rankings go stale much faster than draft rankings -- analysts update
# them all week as practice reports come in, and they matter most on Sunday
# morning. Three hours keeps us current without hammering the site.
CACHE_HOURS = 3


def page_url(position, scoring):
    """The right FantasyPros page for one position in this league's format."""
    page = PAGES.get(position)
    if page is None:
        return None
    if isinstance(page, dict):
        page = page[scoring]
    return BASE_URL + page


def cache_path(position, scoring, season, week):
    # The slash in "D/ST" would look like a directory to the filesystem.
    safe = position.replace("/", "")
    name = f"weekly_{safe.lower()}_{scoring.lower()}_{season}_wk{week}.json"
    return os.path.join(season_rankings.CACHE_DIR, name)


def read_cache(position, scoring, season, week, max_age_hours):
    path = cache_path(position, scoring, season, week)
    try:
        if (time.time() - os.path.getmtime(path)) / 3600 > max_age_hours:
            return None
        with open(path) as handle:
            return json.load(handle)["players"]
    except (OSError, ValueError, KeyError):
        return None


def write_cache(position, scoring, season, week, players):
    try:
        os.makedirs(season_rankings.CACHE_DIR, exist_ok=True)
        with open(cache_path(position, scoring, season, week), "w") as handle:
            json.dump({"players": players}, handle)
    except OSError:
        pass  # a cache we cannot write is an inconvenience, not a failure


def download(position, scoring, week):
    """
    Fetches one position's weekly page and lifts the rankings out of it.

    Like the draft version, the rankings ship inside the page as a
    JavaScript variable rather than as a table we would have to read.

    We check the week the page reports back. FantasyPros serves the current
    week by default and rolls over to the next one once the week's games are
    done, so asking for a week it is no longer publishing would otherwise
    hand us the wrong list without saying so.
    """
    url = page_url(position, scoring)
    if url is None:
        return None

    response = season_rankings.polite_get(url)
    response.raise_for_status()

    match = re.search(r"var\s+ecrData\s*=\s*(\{.*?\});\s*\n", response.text, re.S)
    if not match:
        raise RuntimeError("FantasyPros changed their page layout")

    data = json.loads(match.group(1))

    served_week = season_rankings.to_number(data.get("week"), None)
    if served_week is not None and int(served_week) != int(week):
        raise RuntimeError(
            f"asked FantasyPros for week {week}, got week {int(served_week)}"
        )

    players = data.get("players") or []
    if not players:
        raise RuntimeError("FantasyPros returned an empty list")
    return players


def rankings_for_position(position, scoring, season, week, force_refresh=False):
    """One position's weekly list, or None if it cannot be had at all."""
    if not force_refresh:
        cached = read_cache(position, scoring, season, week, CACHE_HOURS)
        if cached:
            return cached

    try:
        players = download(position, scoring, week)
    except Exception:
        # Out of date beats nothing, but only within the same week -- last
        # week's rankings are worse than no rankings, and the cache is keyed
        # by week so this can only ever return the right week's list.
        return read_cache(position, scoring, season, week, max_age_hours=10 ** 6)

    if players:
        write_cache(position, scoring, season, week, players)
    return players


def weekly_rankings(scoring, season, week, positions=None, force_refresh=False):
    """
    Every position's weekly list, keyed by position.

    Missing positions are simply absent, so one page failing costs us that
    position and nothing else.
    """
    wanted = positions or list(PAGES)
    out = {}
    for position in wanted:
        players = rankings_for_position(position, scoring, season, week, force_refresh)
        if players:
            out[position] = players
    return out


# ---------------------------------------------------------------------------
# Matching FantasyPros players to ESPN players
# ---------------------------------------------------------------------------

def build_lookup(by_position):
    """
    Same two-track matching as the draft board: real players by name,
    defenses by team code -- because ESPN says "Eagles D/ST" where
    FantasyPros says "Philadelphia Eagles", but both agree it is PHI.

    Names are looked up within a position rather than globally, so an
    unlucky name collision between, say, a receiver and a tight end can
    never hand one player the other's ranking.
    """
    by_name, by_defense_team = {}, {}

    for position, entries in by_position.items():
        for entry in entries:
            if position == "D/ST":
                team = season_rankings.normalize_team(entry.get("player_team_id"))
                by_defense_team.setdefault(team, entry)
            else:
                key = (position, season_rankings.normalize_name(entry.get("player_name") or ""))
                by_name.setdefault(key, entry)

    return by_name, by_defense_team


def attach(players, by_position):
    """
    Writes this week's expert numbers onto each player, in place.

    Unlike the draft board, a player who is missing here is left blank
    rather than being pushed to the bottom. On a draft board being unranked
    is an opinion -- a hundred analysts left him off on purpose. In a weekly
    list it usually just means FantasyPros publishes 60 running backs and
    your bench guy is the 61st, which says nothing about Sunday.

    Returns a short summary so callers can report how the matching went.
    """
    by_name, by_defense_team = build_lookup(by_position)
    matched = 0

    for player in players:
        position = player.get("position")
        if position == "D/ST":
            entry = by_defense_team.get(season_rankings.normalize_team(player.get("pro_team")))
        else:
            entry = by_name.get(
                (position, season_rankings.normalize_name(player.get("name") or ""))
            )

        if entry is None:
            player.update(
                {
                    "weekly_ecr": None,
                    "weekly_pos_rank": None,
                    "weekly_projection": None,
                    "weekly_spread": None,
                    "weekly_delta": None,
                    "weekly_grade": None,
                    "weekly_note": None,
                    "opponent": None,
                    "expert_ranked_this_week": False,
                }
            )
            continue

        matched += 1
        number = season_rankings.to_number
        player.update(
            {
                "weekly_ecr": number(entry.get("rank_ecr"), None),
                "weekly_pos_rank": entry.get("pos_rank"),
                "weekly_projection": number(entry.get("r2p_pts"), None),
                "weekly_spread": number(entry.get("rank_std"), None),
                # Positive delta means his rank number got bigger, i.e. the
                # experts moved him DOWN. Flipped here so that in this tool a
                # positive number always means good news.
                "weekly_delta": -number(entry.get("player_ecr_delta"), 0.0),
                "weekly_grade": entry.get("start_sit_grade") or None,
                "weekly_note": (entry.get("note") or "").strip() or None,
                "opponent": (entry.get("player_opponent") or "").strip() or None,
                "expert_ranked_this_week": True,
            }
        )

    return {"matched": matched, "total": len(players)}


def load_for_league(league, season, week, positions=None, force_refresh=False):
    """Convenience wrapper: this week's lists in this league's scoring format."""
    scoring = season_rankings.scoring_key(league)
    return scoring, weekly_rankings(scoring, season, week, positions, force_refresh)
