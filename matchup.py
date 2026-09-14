"""
This week's head-to-head: am I the favourite, and should that change who I
start?

Start/sit picks the lineup with the most projected points. That is the right
answer almost always -- but not in close calls. Fantasy is won by beating
ONE opponent, not by scoring the most on average:

  * As a big FAVOURITE, a steady player's floor protects a likely win. A
    boom-or-bust player mostly adds ways to lose.
  * As a big UNDERDOG, averages lose. Only a player who can explode gives
    you a real chance, even if his average is slightly lower.

So this reads your opponent's roster, builds the lineup THEY should start
(assuming they set their best one), estimates your chance of winning, and
then looks only at close calls -- a bench player within a point and a half
of a starter -- and says which way to lean, using `consistency.py`.

It never overrides the recommended lineup. It adds "if you want to lean"
suggestions next to it, with the reason.

The win chance treats each side's total as a bell curve around its
projection, with the width built from each starter's own week-to-week
swings. It is an estimate, and is shown rounded to the nearest 5%.
"""

import math

import consistency
import lineup


# A bench player this close to a starter is a genuine coin flip on
# projection alone, so the matchup situation is allowed to decide it.
CLOSE_POINTS = 1.5

FAVOURITE = 0.65
UNDERDOG = 0.35

# Swing assumed for a player with too few games to measure.
DEFAULT_SWING = 0.6


def player_spread(player):
    """One player's week-to-week standard deviation, in points."""
    profile = player.get("consistency") or {}
    swing = profile.get("swing", DEFAULT_SWING)
    return swing * max(0.0, player.get("score") or 0.0)


def win_probability(my_starters, their_starters):
    """Chance my lineup outscores theirs, from projections and swings."""
    mine = sum(p.get("score") or 0.0 for p in my_starters)
    theirs = sum(p.get("score") or 0.0 for p in their_starters)
    variance = sum(player_spread(p) ** 2 for p in list(my_starters) + list(their_starters))
    if variance <= 0:
        return 1.0 if mine > theirs else 0.0 if mine < theirs else 0.5
    z = (mine - theirs) / math.sqrt(variance)
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def rounded(probability):
    """To the nearest 5%, as shown -- labels use this so they match the number."""
    return round(probability * 20) / 20


def situation(probability):
    probability = rounded(probability)
    if probability >= FAVOURITE:
        return "favourite"
    if probability <= UNDERDOG:
        return "underdog"
    return "toss-up"


def tiebreaks(assigned, bench, probability):
    """
    Close calls where the matchup should decide. Returns a list of
    {"start", "over", "slot", "reason"} -- never changes the lineup itself.
    """
    stance = situation(probability)
    if stance == "toss-up":
        return []

    suggestions, used = [], set()
    for slot, starters in assigned.items():
        eligible = lineup.SLOT_ELIGIBILITY.get(slot, set())
        for starter in starters:
            starter_profile = starter.get("consistency")
            if not starter_profile or starter.get("locked"):
                continue
            for option in bench:
                profile = option.get("consistency")
                if (id(option) in used or not profile or option.get("locked")
                        or not option.get("can_play") or option["position"] not in eligible):
                    continue
                gap = (starter.get("score") or 0) - (option.get("score") or 0)
                if gap < 0 or gap > CLOSE_POINTS:
                    continue
                if stance == "underdog" and profile["ceiling"] > starter_profile["ceiling"] + 2:
                    reason = (
                        f"you're the underdog: {option['name']}'s big weeks reach "
                        f"{profile['ceiling']:.0f} vs {starter_profile['ceiling']:.0f}, "
                        f"for {gap:.1f} projected pts"
                    )
                elif stance == "favourite" and profile["floor"] > starter_profile["floor"] + 2:
                    reason = (
                        f"you're the favourite: {option['name']}'s bad weeks still bring "
                        f"{profile['floor']:.0f} vs {starter_profile['floor']:.0f}, "
                        f"for {gap:.1f} projected pts"
                    )
                else:
                    continue
                used.add(id(option))
                suggestions.append({"start": option, "over": starter, "slot": slot, "reason": reason})
                break
    return suggestions


def opponent_for_week(league, team_id, week):
    team = lineup.my_team(league, team_id)
    schedule = getattr(team, "schedule", None) or []
    periods = getattr(league.settings, "matchup_periods", {}) or {}
    period = next((int(k) for k, v in periods.items() if week in v), week)
    if 1 <= period <= len(schedule):
        opponent = schedule[period - 1]
        return None if getattr(opponent, "team_id", None) == team_id else opponent
    return None


def build(league, team_id, week, season, my_board, use_experts=True, force_refresh=False):
    """
    The head-to-head for `week`, given my start/sit board from `lineup.build`.
    Returns None for a bye or when the opponent cannot be read.
    """
    opponent = opponent_for_week(league, team_id, week)
    if opponent is None:
        return None
    their_board = lineup.build(
        league, opponent.team_id, week, season,
        use_experts=use_experts, force_refresh=force_refresh,
    )

    table = consistency.load(_scoring(league), season)
    for board in (my_board, their_board):
        consistency.attach(board["players"], table)

    probability = win_probability(my_board["starters"], their_board["starters"])
    return {
        "opponent": opponent.team_name,
        "my_projected": my_board["recommended_total"],
        "their_projected": their_board["recommended_total"],
        "win_probability": probability,
        "situation": situation(probability),
        "their_lineup": their_board["assigned"],
        "tiebreaks": tiebreaks(my_board["assigned"], my_board["bench"], probability),
    }


def _scoring(league):
    import outside_rankings
    return outside_rankings.scoring_key(league)


def describe(result):
    if not result:
        return "No opponent this week."
    chance = round(rounded(result["win_probability"]) * 100)
    return (
        f"vs {result['opponent']}: you {result['my_projected']:.1f} - "
        f"{result['their_projected']:.1f} them, about a {chance}% chance to win "
        f"({result['situation']})"
    )
