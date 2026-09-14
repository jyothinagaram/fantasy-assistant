"""
How much each player is actually used: snaps, targets, and their shares.

Points are the result; usage is the cause. A receiver who played 90% of his
team's snaps and drew a quarter of the targets but scored 6 points is a far
better bet than one who scored 20 on two catches -- and usage shows up a
week or two before the points do. That is exactly the edge the
under-the-radar list is hunting for.

The source is nflverse (github.com/nflverse), a free, open collection of NFL
data maintained by the football analytics community:

  * snap counts per player per game (from Pro Football Reference), and
  * weekly player stats, including target share (his share of his team's
    targets), air-yards share (his share of the team's downfield passing)
    and WOPR, a standard blend of the two that tracks receiver value well.

Players are matched to ESPN by ESPN's own player ID, using nflverse's player
table -- never by name, so two players called Douglas cannot be confused.

nflverse updates these files a day or two after games, so the newest week
may be missing early in the week. Everything here is best-effort: if the
download fails, the tools simply fall back to ESPN's own numbers.
"""

import csv
import io
import os
import time

import requests


BASE = "https://github.com/nflverse/nflverse-data/releases/download/"
FILES = {
    "snaps": "snap_counts/snap_counts_{season}.csv",
    "stats": "stats_player/stats_player_week_{season}.csv",
    "players": "players/players.csv",
}
CACHE_DIR = "cache"
CACHE_HOURS = {"snaps": 6, "stats": 6, "players": 24 * 7}

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

# A jump in snap share this big, compared with his earlier games, is a role
# change -- not the normal wobble of a few plays either way.
SNAP_JUMP = 0.15


def download(kind, season):
    """One nflverse file, from the cache if it is fresh enough."""
    name = FILES[kind].format(season=season)
    path = os.path.join(CACHE_DIR, "nflverse_" + name.replace("/", "_"))
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_HOURS[kind] * 3600:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    try:
        response = requests.get(BASE + name, timeout=60)
        response.raise_for_status()
        text = response.text
    except Exception:
        # Stale data beats no data.
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


def rows(text):
    return list(csv.DictReader(io.StringIO(text))) if text else []


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def id_maps(players_text):
    """nflverse's two player IDs (stats and snap counts), each to ESPN's."""
    by_gsis, by_pfr = {}, {}
    for row in rows(players_text):
        espn = row.get("espn_id")
        if not espn:
            continue
        try:
            espn = int(float(espn))
        except ValueError:
            continue
        if row.get("gsis_id"):
            by_gsis[row["gsis_id"]] = espn
        if row.get("pfr_id"):
            by_pfr[row["pfr_id"]] = espn
    return by_gsis, by_pfr


def build(snaps_text, stats_text, players_text):
    """
    {espn_id: usage summary}. Pure function of the three files, so it can
    be tested without the network.
    """
    by_gsis, by_pfr = id_maps(players_text)
    weeks = {}  # espn_id -> {week: {...}}

    for row in rows(snaps_text):
        if row.get("game_type") != "REG" or row.get("position") not in SKILL_POSITIONS:
            continue
        espn = by_pfr.get(row.get("pfr_player_id"))
        week = number(row.get("week"))
        if espn is None or week is None:
            continue
        entry = weeks.setdefault(espn, {}).setdefault(int(week), {})
        entry["snap_pct"] = number(row.get("offense_pct"))
        entry["snaps"] = number(row.get("offense_snaps"))
        entry["team"] = row.get("team")

    for row in rows(stats_text):
        if row.get("season_type") != "REG" or row.get("position") not in SKILL_POSITIONS:
            continue
        espn = by_gsis.get(row.get("player_id"))
        week = number(row.get("week"))
        if espn is None or week is None:
            continue
        entry = weeks.setdefault(espn, {}).setdefault(int(week), {})
        entry.update(
            targets=number(row.get("targets")) or 0.0,
            carries=number(row.get("carries")) or 0.0,
            target_share=number(row.get("target_share")),
            air_yards_share=number(row.get("air_yards_share")),
            wopr=number(row.get("wopr")),
        )
        entry.setdefault("team", row.get("team"))

    return {espn: summarise(by_week) for espn, by_week in weeks.items()}


def average(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def summarise(by_week):
    """One player's weeks, boiled down to the numbers the tools use."""
    ordered = [by_week[w] for w in sorted(by_week)]
    latest = ordered[-1]
    earlier = ordered[:-1]

    snap_trend = None
    if earlier and latest.get("snap_pct") is not None:
        before = average(w.get("snap_pct") for w in earlier)
        if before is not None:
            snap_trend = latest["snap_pct"] - before

    recent = ordered[-2:]
    return {
        "weeks": sorted(by_week),
        "latest_week": sorted(by_week)[-1],
        "snap_pct": latest.get("snap_pct"),
        "snap_pct_avg": average(w.get("snap_pct") for w in ordered),
        "snap_trend": snap_trend,
        "target_share": average(w.get("target_share") for w in recent),
        "air_yards_share": average(w.get("air_yards_share") for w in recent),
        "wopr": average(w.get("wopr") for w in recent),
        "touches_per_game": average(
            (w.get("targets") or 0) + (w.get("carries") or 0) for w in ordered if "targets" in w
        ),
        "team": latest.get("team"),
    }


def load(season):
    """Everyone's usage for the season, or {} if nflverse cannot be reached."""
    players = download("players", season)
    if not players:
        return {}
    table = build(download("snaps", season), download("stats", season), players)
    try:
        import redzone
        for espn, red in redzone.load(season).items():
            if espn in table:
                table[espn].update(red)
    except Exception:
        pass  # red-zone numbers are extra; usage stands without them
    return table


def attach(players, by_espn_id):
    """Writes each player's usage onto him, in place. Missing players get None."""
    for player in players:
        player["usage"] = by_espn_id.get(player.get("player_id"))
    return players


def describe(summary):
    """'snaps 62% (up 18 pts) · 23% of targets · 31% of air yards'"""
    if not summary:
        return None
    parts = []
    if summary.get("snap_pct") is not None:
        text = f"snaps {summary['snap_pct']:.0%}"
        trend = summary.get("snap_trend")
        if trend is not None and abs(trend) >= 0.05:
            text += f" ({'up' if trend > 0 else 'down'} {abs(trend) * 100:.0f} pts)"
        parts.append(text)
    if (summary.get("target_share") or 0) > 0:
        parts.append(f"{summary['target_share']:.0%} of targets")
    # Short passes behind the line can make a running back's air-yards share
    # negative, which reads as nonsense -- only a positive share is shown.
    if (summary.get("air_yards_share") or 0) > 0:
        parts.append(f"{summary['air_yards_share']:.0%} of air yards")
    if summary.get("red_zone_opps"):
        text = f"{summary['red_zone_opps']} red-zone looks"
        if summary.get("red_zone_share"):
            text += f" ({summary['red_zone_share']:.0%} of team's)"
        if summary.get("goal_line_opps"):
            text += f", {summary['goal_line_opps']} inside the 5"
        parts.append(text)
    return " · ".join(parts) or None
