"""
How much a player's weekly score swings.

Two receivers can both average 12 points: one scores 10, 12, 14 every week,
the other 2, 25, 4, 22. Over a season they are worth the same. In ONE week
they are not: if you are a big favourite you want the steady one (a floor
you can count on), and if you are a big underdog you want the swingy one
(the ceiling is your only way to win). `matchup.py` uses this for exactly
that call.

Built from nflverse's free weekly stats for this season and last, in the
league's own scoring format, over a player's most recent games:

  * floor   -- a bad week for him (his 20th-percentile score)
  * ceiling -- a great week for him (his 80th-percentile score)
  * swing   -- how big his swings are compared with his average (the
               coefficient of variation); a label of steady / normal /
               boom-or-bust comes from this

Shown, never scored into projections: the average is already in the
projection, and swings do not change it. Swings only matter for choosing
between players whose projections are close, which is where they are used.
"""

import statistics

import defense
import usage


# Most recent games used -- a season's worth, spanning last year if needed.
RECENT_GAMES = 17

# Fewer games than this and a player's swings are not measured at all.
MIN_GAMES = 6

# Only games where he actually played a real part count; a 1-snap cameo or
# an early injury exit would otherwise make everyone look boom-or-bust.
MIN_POINTS_TO_COUNT = 0.5

STEADY_SWING = 0.45
VOLATILE_SWING = 0.75


def build(stats_by_season, players_text, scoring):
    """
    {espn_id: profile}. `stats_by_season` is [(season, csv text), ...].
    Pure, so it can be tested without the network.
    """
    by_gsis, _ = usage.id_maps(players_text)
    games = {}
    for season, text in stats_by_season:
        for row in usage.rows(text):
            if row.get("season_type") != "REG":
                continue
            espn = by_gsis.get(row.get("player_id"))
            week = usage.number(row.get("week"))
            if espn is None or week is None:
                continue
            points = defense.fantasy_points(row, scoring)
            if points < MIN_POINTS_TO_COUNT:
                continue
            games.setdefault(espn, []).append(((int(season), int(week)), points))

    out = {}
    for espn, played in games.items():
        recent = [points for _, points in sorted(played)[-RECENT_GAMES:]]
        profile = profile_from(recent)
        if profile:
            out[espn] = profile
    return out


def profile_from(points):
    if len(points) < MIN_GAMES:
        return None
    mean = statistics.mean(points)
    if mean <= 0:
        return None
    swing = statistics.pstdev(points) / mean
    ordered = sorted(points)
    return {
        "games": len(points),
        "average": round(mean, 1),
        "floor": round(usage_percentile(ordered, 0.2), 1),
        "ceiling": round(usage_percentile(ordered, 0.8), 1),
        "swing": round(swing, 2),
        "label": "steady" if swing <= STEADY_SWING else "boom-or-bust" if swing >= VOLATILE_SWING else "normal",
    }


def usage_percentile(ordered, share):
    index = share * (len(ordered) - 1)
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def load(scoring, season):
    players = usage.download("players", season)
    if not players:
        return {}
    texts = [(s, usage.download("stats", s)) for s in (season - 1, season)]
    return build([(s, t) for s, t in texts if t], players, scoring)


def attach(players, table):
    for player in players:
        player["consistency"] = table.get(player.get("player_id"))
    return players


def describe(profile):
    """'steady: usually 8-16 pts (17 games)'"""
    if not profile:
        return None
    return (
        f"{profile['label']}: usually {profile['floor']:.0f}-{profile['ceiling']:.0f} pts "
        f"({profile['games']} games)"
    )
