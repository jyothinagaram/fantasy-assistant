"""
How generous each defence is to each position.

"He plays a bad defence" is the most common start/sit argument, and it is
usually made from memory. This puts a number on it: the fantasy points each
defence has allowed per game to quarterbacks, running backs, receivers and
tight ends, and where that ranks among the 32.

Built from nflverse's weekly player stats (the same free files as
`usage.py`): every player's fantasy points, credited to the defence he
played against. Points are computed in the league's own format -- full PPR,
half PPR or standard -- from nflverse's standard and PPR totals.

SHOWN, NEVER SCORED. ESPN's and FantasyPros' projections already account for
the opponent, so adding a matchup bonus on top would count the same defence
twice -- the same trap as discounting a questionable player twice (see
CLAUDE.md). This is here to read, and to break a close call.

Early in the season one game is mostly noise -- a defence that faced Ja'Marr
Chase in week 1 looks terrible against receivers. So until a defence has
played a few games, its number is pulled toward the league average, and the
page says how many games it is based on.
"""

import statistics

import outside_rankings
import usage


POSITIONS = ("QB", "RB", "WR", "TE")

# Games before a defence's own record counts as much as the league average.
PRIOR_GAMES = 3

# Ranks at or beyond these are worth calling out as a good or bad matchup.
SOFT_RANK = 8     # among the 8 most generous
TOUGH_RANK = 25   # among the 8 stingiest

# A defence is only labelled soft or tough once it has this many games.
# After one game the ranking is mostly who it happened to play.
GAMES_TO_LABEL = 2


def fantasy_points(row, scoring):
    standard = usage.number(row.get("fantasy_points")) or 0.0
    ppr = usage.number(row.get("fantasy_points_ppr"))
    if ppr is None:
        return standard
    if scoring == "PPR":
        return ppr
    if scoring == "HALF":
        return (standard + ppr) / 2
    return standard


def build(stats_text, scoring, before_week=None):
    """
    {defence team: {position: {...}}}, from nflverse weekly stats.

    `before_week` limits it to games already played before that week, so a
    number never includes the game it is being used to preview.
    """
    allowed = {}   # (defence, position, week) -> points
    for row in usage.rows(stats_text):
        position = row.get("position")
        if row.get("season_type") != "REG" or position not in POSITIONS:
            continue
        week = usage.number(row.get("week"))
        defence = outside_rankings.normalize_team(row.get("opponent_team"))
        if week is None or not defence or (before_week and week >= before_week):
            continue
        key = (defence, position, int(week))
        allowed[key] = allowed.get(key, 0.0) + fantasy_points(row, scoring)

    per_game = {}  # (defence, position) -> [weekly totals]
    for (defence, position, _), points in allowed.items():
        per_game.setdefault((defence, position), []).append(points)

    out = {}
    for position in POSITIONS:
        teams = {d: weeks for (d, p), weeks in per_game.items() if p == position}
        if not teams:
            continue
        league_average = statistics.mean(p for weeks in teams.values() for p in weeks)

        adjusted = {}
        for defence, weeks in teams.items():
            games = len(weeks)
            raw = sum(weeks) / games
            adjusted[defence] = (
                (raw * games + league_average * PRIOR_GAMES) / (games + PRIOR_GAMES),
                raw,
                games,
            )

        ordered = sorted(adjusted, key=lambda d: adjusted[d][0], reverse=True)
        for rank, defence in enumerate(ordered, start=1):
            value, raw, games = adjusted[defence]
            out.setdefault(defence, {})[position] = {
                "allowed_per_game": round(raw, 1),
                "adjusted": round(value, 1),
                "vs_average": round(value - league_average, 1),
                "rank": rank,            # 1 = gives up the most points
                "teams": len(ordered),
                "games": games,
            }
    return out


def load(scoring, season, before_week=None):
    """Every defence's record, or {} if nflverse cannot be reached."""
    return build(usage.download("stats", season), scoring, before_week)


def describe(opponent, position, table):
    """'vs PIT: allows 28.1 pts/game to WRs, 5th most (1 game)' -- or None."""
    entry = (table.get(outside_rankings.normalize_team(opponent)) or {}).get(position)
    if not entry:
        return None
    rank, teams = entry["rank"], entry["teams"]
    if rank <= SOFT_RANK:
        label = f"{ordinal(rank)} most"
    elif rank >= TOUGH_RANK:
        label = f"{ordinal(teams - rank + 1)} fewest"
    else:
        label = f"ranked {ordinal(rank)} of {teams}"
    games = entry["games"]
    return (
        f"vs {opponent}: allows {entry['allowed_per_game']:.1f} pts/game to {position}s, "
        f"{label} ({games} game{'s' if games != 1 else ''})"
    )


def matchup_quality(opponent, position, table):
    """'soft', 'tough' or None -- for colouring a matchup, never for scoring."""
    entry = (table.get(outside_rankings.normalize_team(opponent)) or {}).get(position)
    if not entry or entry["games"] < GAMES_TO_LABEL:
        return None
    if entry["rank"] <= SOFT_RANK:
        return "soft"
    if entry["rank"] >= TOUGH_RANK:
        return "tough"
    return None


def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def attach(players, table, opponents):
    """
    Writes `matchup` (the sentence) and `matchup_quality` onto each player.
    `opponents` is {team code: opponent code} for the week being planned.
    """
    for player in players:
        team = outside_rankings.normalize_team(player.get("pro_team") or player.get("team"))
        opponent = opponents.get(team)
        position = player.get("position")
        if not opponent or position not in POSITIONS:
            player["matchup"] = player["matchup_quality"] = None
            continue
        player["matchup"] = describe(opponent, position, table)
        player["matchup_quality"] = matchup_quality(opponent, position, table)
    return players


def attach_for_league(league, season, week, players):
    """Convenience: load the table and this week's opponents, then attach."""
    import status as game_status

    try:
        table = load(outside_rankings.scoring_key(league), season, before_week=week)
        opponents = {
            team: game.get("opponent")
            for team, game in game_status.kickoffs(season, week).items()
        }
        attach(players, table, opponents)
    except Exception:
        for player in players:
            player.setdefault("matchup", None)
            player.setdefault("matchup_quality", None)
