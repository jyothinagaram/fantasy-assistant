"""
Who each player faces when your fantasy playoffs are played.

A trade in October is really a bet on December. Two receivers worth the same
now are not worth the same to a playoff team if one plays three soft
defences in weeks 15-17 and the other plays three good ones -- or is on BYE
in the semi-final.

For each league this works out the fantasy playoff weeks from its own
settings (regular-season length, playoff teams, weeks per round), then for
every player lists his NFL opponent in each of those weeks from ESPN's
season schedule, and:

  * flags a BYE in a playoff week loudly -- that is a guaranteed zero;
  * once defences have played enough games to mean something, rates the
    run of opponents using `defense.py`: soft, tough or neutral.

Early in the season the defence ratings are mostly noise (one game tells you
who a defence happened to play), so until MIN_GAMES_FOR_RATING the opponents
are listed without a rating.

Shown in trades -- where a December schedule should tip a close decision --
and never scored into the lineup maths, which still values the regular
season only.
"""

import math
import statistics

import defense
import outside_rankings


# Defences need this many games before their playoff-week matchups are rated.
MIN_GAMES_FOR_RATING = 4

# Average rank (1 = most generous) at or better / worse than these marks a
# playoff schedule as soft or tough.
SOFT_AVERAGE_RANK = 12
TOUGH_AVERAGE_RANK = 21


def playoff_weeks(league):
    """The NFL weeks this league's playoffs use, from its own settings."""
    settings = league.settings
    teams = max(2, int(settings.playoff_team_count or 2))
    rounds = math.ceil(math.log2(teams))
    length = int(getattr(settings, "playoff_matchup_period_length", 1) or 1)
    first = int(settings.reg_season_count) + 1
    return list(range(first, first + rounds * length))


def nfl_schedule(league):
    """{team code: {week: opponent code or 'BYE'}} for the whole season."""
    from espn_api.football.constant import PRO_TEAM_MAP

    data = league.espn_request.get_pro_schedule()
    out = {}
    for team in (data.get("settings") or {}).get("proTeams") or []:
        code = outside_rankings.normalize_team(PRO_TEAM_MAP.get(team.get("id")))
        if not code or code == "NONE":
            continue
        weeks = {}
        for week, games in (team.get("proGamesByScoringPeriod") or {}).items():
            for game in games:
                other = game["awayProTeamId"] if game["homeProTeamId"] == team["id"] else game["homeProTeamId"]
                prefix = "" if game["homeProTeamId"] == team["id"] else "@"
                weeks[int(week)] = prefix + outside_rankings.normalize_team(PRO_TEAM_MAP.get(other))
        if team.get("byeWeek"):
            weeks[int(team["byeWeek"])] = "BYE"
        out[code] = weeks
    return out


def outlook(team, position, weeks, schedule, table):
    """One player's playoff run: opponents, bye weeks, and a rating when possible."""
    games = schedule.get(outside_rankings.normalize_team(team)) or {}
    opponents = [(week, games.get(week)) for week in weeks]
    byes = [week for week, opponent in opponents if opponent == "BYE"]

    ranks, enough = [], True
    for _, opponent in opponents:
        if not opponent or opponent == "BYE":
            continue
        entry = (table.get(opponent.lstrip("@")) or {}).get(position)
        if not entry or entry["games"] < MIN_GAMES_FOR_RATING:
            enough = False
            continue
        ranks.append(entry["rank"])

    rating = None
    if enough and ranks:
        average = statistics.mean(ranks)
        rating = "soft" if average <= SOFT_AVERAGE_RANK else "tough" if average >= TOUGH_AVERAGE_RANK else "neutral"

    return {
        "weeks": weeks,
        "opponents": [opponent or "?" for _, opponent in opponents],
        "byes": byes,
        "rating": rating,
    }


def describe(result):
    """'playoffs (wks 15-17): @DEN, KC, LV -- soft' / '... -- BYE in week 16'"""
    if not result or not result["weeks"]:
        return None
    weeks = result["weeks"]
    span = f"wk {weeks[0]}" if len(weeks) == 1 else f"wks {weeks[0]}-{weeks[-1]}"
    text = f"playoffs ({span}): {', '.join(result['opponents'])}"
    if result["byes"]:
        text += f" -- BYE in week {', '.join(map(str, result['byes']))}"
    elif result["rating"]:
        text += f" -- {result['rating']} schedule"
    return text


def attach(league, season, players):
    """`playoffs` (a sentence) and `playoff_bye` on each player, best-effort."""
    try:
        weeks = playoff_weeks(league)
        schedule = nfl_schedule(league)
        table = defense.load(outside_rankings.scoring_key(league), season)
    except Exception:
        for player in players:
            player.setdefault("playoffs", None)
            player.setdefault("playoff_bye", False)
        return players
    for player in players:
        result = outlook(player.get("pro_team") or player.get("team"), player.get("position"),
                         weeks, schedule, table)
        player["playoffs"] = describe(result)
        player["playoff_bye"] = bool(result["byes"])
    return players
