"""
Who to pick up, who to drop for him, and what to bid.

The question a waiver claim really asks is not "is this free agent good?"
but "does my team score more for the rest of the season with him instead of
somebody I already have?" Those are different questions. A decent running
back is worth nothing to you if he would never crack your lineup, and a
mediocre tight end can be worth a lot if yours is on bye in three weeks.

So every possible swap -- add this free agent, drop that player of mine -- is
measured the same way: play out each remaining regular-season week, solve for
the best legal lineup in each one (using the same solver as start/sit), and
add up the points. The pickup's value is how much that total goes up. That
one number automatically accounts for:

  * whether he would actually start for you,
  * bye weeks (a backup is worth exactly the weeks he fills in),
  * your league's slots, including the second flex in The Boyz are Back.

What a player is worth in a given week:

  * The first week the pickup could play: this week's projections, ESPN and
    FantasyPros averaged, injuries applied -- exactly what start/sit uses.
    That is where fresh news shows up.
  * Every week after: his season per-game average. Early on that is mostly
    ESPN's projection; as games are played, what he has actually scored
    takes over a little more each week (see `per_game_value`).

FACTS VOTE, PROSE DOES NOT -- the same rule as the rest of the project.
Projections, points scored, bye weeks and injury designations move the
numbers. Nothing a writer said does.

The FAAB bid is a heuristic, and says so. As of Week 1 there were only six
real claims across all three leagues, which is nothing to learn from. The
bid should be recalibrated once the season has produced some bid history.
"""

import lineup
import rankings


# How many games of real scoring it takes before a player's actual per-game
# average counts as much as his projection. Low enough that a genuine
# breakout shows up within a few weeks; high enough that one big game does
# not send a backup to the top of the list.
PROJECTION_WEIGHT_IN_GAMES = 4

# Kickers and defenses swing wildly from game to game -- a defense scores 18
# one week off two fluky touchdowns and 2 the next -- so their real scoring
# needs far more games before it is allowed to outweigh the projection.
NOISY_POSITIONS = {"K", "D/ST"}
NOISY_PROJECTION_WEIGHT_IN_GAMES = 10

# Weeks a player on injured reserve or suspended is assumed to miss. ESPN
# does not publish a return date, so this is a deliberately rough guess --
# which is why these players are flagged rather than trusted.
ASSUMED_WEEKS_MISSED = 4

# A pickup has to add at least this many points a week to be worth a claim.
# Below it, the difference is inside the error of the projections, and every
# claim spends budget and churns your roster.
WORTH_A_CLAIM = 0.5

# How much of your REMAINING budget to bid, by how many points a week the
# pickup adds. Rough on purpose -- see the note at the top.
BID_TIERS = [
    (5.0, 0.25),   # a real difference-maker
    (3.0, 0.15),
    (1.5, 0.08),
    (WORTH_A_CLAIM, 0.02),
]

# A player already rostered in over half of ESPN leagues is one other people
# in your league probably want too, so the bid is nudged up to win him.
POPULAR_OWNERSHIP = 50.0
POPULAR_BID_BOOST = 1.5

# How deep into the free-agent pool to look. Sorted by how widely owned they
# are, so this comfortably covers anyone who could matter.
FREE_AGENT_POOL = 150


# ---------------------------------------------------------------------------
# What a player is worth, week by week
# ---------------------------------------------------------------------------

def per_game_value(player):
    """
    What he should score in a normal week for the rest of the season.

    His projection and his actual per-game average, blended. Before he has
    played, it is all projection. After four games it is half and half, and
    it leans further toward what he has really done after that.
    """
    projected = player.get("season_projected_avg") or 0.0
    actual = player.get("season_actual_avg")
    games = player.get("games_played") or 0
    if not games or actual is None:
        return projected
    if player.get("position") in NOISY_POSITIONS:
        weight = NOISY_PROJECTION_WEIGHT_IN_GAMES
    else:
        weight = PROJECTION_WEIGHT_IN_GAMES
    return (weight * projected + games * actual) / (weight + games)


def value_in_week(player, week, first_week):
    """One player's expected points in one future week, or 0 if he sits."""
    if player.get("bye_week") == week:
        return 0.0

    status = player.get("injury_status") or "ACTIVE"
    if status in {"INJURY_RESERVE", "SUSPENSION"}:
        if week < first_week + ASSUMED_WEEKS_MISSED:
            return 0.0

    if week == first_week and player.get("score") is not None:
        # This week's number already has experts, injuries and practice
        # reports folded in by the start/sit scoring.
        return player["score"]

    return per_game_value(player)


def team_value(players, slots, weeks, first_week):
    """
    Total points your best lineup would score across these weeks.

    Solves a fresh lineup for every week, because the best lineup changes
    whenever someone is on bye or hurt.
    """
    total = 0.0
    for week in weeks:
        weekly = []
        for player in players:
            points = value_in_week(player, week, first_week)
            weekly.append(
                {
                    "position": player["position"],
                    "score": points,
                    "can_play": points > 0,
                }
            )
        _, starters, _ = lineup.best_lineup(weekly, slots)
        total += lineup.lineup_total(starters)
    return round(total, 2)


# ---------------------------------------------------------------------------
# Finding the best swaps
# ---------------------------------------------------------------------------

def droppable(player):
    """
    Players who could make room for a pickup.

    Someone sitting in your IR slot is not taking a roster spot, so dropping
    him frees nothing -- he is left out rather than suggested.
    """
    return player.get("current_slot") != "IR"


def best_swaps(my_players, free_agents, slots, weeks, first_week, roster_full=True):
    """
    For every free agent, the best player of yours to drop for him, and how
    much the swap is worth in total points and points per week.

    If you have an empty roster spot, the pickup can simply be added with no
    drop, and that is tried too.

    Returns a list sorted best first, only including swaps that help.
    """
    baseline = team_value(my_players, slots, weeks, first_week)
    candidates = [p for p in my_players if droppable(p)]
    week_count = max(1, len(weeks))

    swaps = []
    for pickup in free_agents:
        options = [] if roster_full else [None]
        options.extend(candidates)

        best = None
        for drop in options:
            new_roster = [p for p in my_players if p is not drop] + [pickup]
            gain = round(team_value(new_roster, slots, weeks, first_week) - baseline, 2)
            # Ties are common: a bench player who never starts costs the same
            # to drop as a better one who also never starts. On a tie, drop
            # the weaker player -- the better one is the injury insurance.
            weakness = -per_game_value(drop) if drop else float("inf")
            if best is None or (gain, weakness) > (best[1], best[2]):
                best = (drop, gain, weakness)

        if best and best[1] > 0:
            drop, gain, _ = best
            swaps.append(
                {
                    "add": pickup,
                    "drop": drop,
                    "total_gain": round(gain, 2),
                    "gain_per_week": round(gain / week_count, 2),
                }
            )

    swaps.sort(key=lambda s: s["total_gain"], reverse=True)
    return swaps


def bye_weeks_covered(pickup, my_players, weeks):
    """
    Weeks where the pickup plays and one of your starters at his position is
    on bye -- the plainest reason a backup is worth having.
    """
    covered = []
    for week in weeks:
        if pickup.get("bye_week") == week:
            continue
        if any(
            p["position"] == pickup["position"] and p.get("bye_week") == week
            for p in my_players
        ):
            covered.append(week)
    return covered


# ---------------------------------------------------------------------------
# What to bid
# ---------------------------------------------------------------------------

def suggest_bid(gain_per_week, budget_left, minimum_bid, percent_owned=0.0):
    """
    A FAAB bid in dollars. A heuristic, not a model -- see the top of file.

    A share of what you have LEFT, not of the starting budget, so the bids
    naturally shrink as the season goes on and you spend.
    """
    if budget_left <= 0:
        return 0
    if gain_per_week < WORTH_A_CLAIM:
        return min(minimum_bid, budget_left)

    share = next(s for threshold, s in BID_TIERS if gain_per_week >= threshold)
    if (percent_owned or 0.0) >= POPULAR_OWNERSHIP:
        share *= POPULAR_BID_BOOST

    bid = round(share * budget_left)
    return int(min(budget_left, max(minimum_bid, bid)))


# ---------------------------------------------------------------------------
# Reading ESPN
# ---------------------------------------------------------------------------

def bye_weeks(league):
    """Every NFL team's bye week, keyed by team code, from one ESPN call."""
    from espn_api.football.constant import PRO_TEAM_MAP

    try:
        data = league.espn_request.get_pro_schedule()
    except Exception:
        return {}
    out = {}
    for team in (data.get("settings") or {}).get("proTeams") or []:
        code = PRO_TEAM_MAP.get(team.get("id"))
        if code and team.get("byeWeek"):
            out[code] = int(team["byeWeek"])
    return out


def waiver_settings(league):
    """
    This league's waiver rules as ESPN reports them.

    ESPN gives the processing hour as a bare number. Which timezone it is in
    has NOT been confirmed against a real processed claim, so callers must
    say so rather than present it as a firm deadline.
    """
    try:
        data = league.espn_request.league_get(params={"view": "mSettings"})
        acquisition = data["settings"]["acquisitionSettings"]
    except Exception:
        acquisition = {}

    order = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    days = sorted(acquisition.get("waiverProcessDays") or [], key=order.index)
    return {
        "budget": acquisition.get("acquisitionBudget") or league.settings.acquisition_budget,
        "uses_faab": acquisition.get("isUsingAcquisitionBudget", league.settings.faab),
        "minimum_bid": acquisition.get("minimumBid", 0),
        "process_days": [d.title()[:3] for d in days],
        "process_hour": acquisition.get("waiverProcessHour"),
    }


def as_player(espn_player, week, byes):
    """An ESPN player object in the dictionary shape the rest of the code uses."""
    projected_avg = getattr(espn_player, "projected_avg_points", 0.0) or 0.0
    actual_total = getattr(espn_player, "total_points", 0.0) or 0.0
    actual_avg = getattr(espn_player, "avg_points", 0.0) or 0.0
    games = round(actual_total / actual_avg) if actual_avg else 0

    return {
        "player_id": getattr(espn_player, "playerId", None),
        "name": espn_player.name,
        "position": espn_player.position,
        "pro_team": espn_player.proTeam,
        "espn_projection": round(lineup.weekly_projection(espn_player, week), 2),
        "injury_status": rankings.clean_injury_status(espn_player),
        "current_slot": getattr(espn_player, "lineupSlot", "") or "",
        "percent_owned": round(getattr(espn_player, "percent_owned", 0.0) or 0.0, 1),
        "bye_week": byes.get(espn_player.proTeam),
        "season_projected_avg": round(projected_avg, 2),
        "season_actual_avg": round(actual_avg, 2) if games else None,
        "games_played": games,
    }


def first_playable_week(league, season):
    """
    The first week a player claimed today could score points for you.

    ESPN's 'current week' stays on a week until well after its games finish.
    Once any game in it has kicked off, the week is underway -- and none of
    your leagues process claims fast enough to help mid-week -- so a pickup's
    first real chance is the week after.
    """
    import status as game_status

    week = league.current_week
    games = game_status.kickoffs(season, week)
    if games and any(g.get("started") for g in games.values()):
        return week + 1
    return week


def build(league, team_id, season, week=None, use_experts=True, force_refresh=False):
    """
    Everything the waiver report needs for one league.

    `week` is the first week a pickup would play; left out, it is worked out
    from the NFL schedule.
    """
    import weekly_rankings

    first_week = week or first_playable_week(league, season)
    last_week = league.settings.reg_season_count
    weeks = list(range(first_week, last_week + 1))

    byes = bye_weeks(league)
    team = lineup.my_team(league, team_id)

    rosters = lineup.rosters_for_week(league, first_week)
    mine = [as_player(p, first_week, byes) for p in rosters.get(team_id, team.roster)]
    pool = league.free_agents(week=first_week, size=FREE_AGENT_POOL)
    slots = lineup.open_slots(league)
    free_agents = [
        as_player(p, first_week, byes)
        for p in pool
        if any(p.position in lineup.SLOT_ELIGIBILITY[s] for s in slots)
    ]

    everyone = mine + free_agents
    try:
        import usage
        usage.attach(everyone, usage.load(season))
    except Exception:
        pass  # snap and target data is shown, never required
    expert_summary = None
    if use_experts:
        _, by_position = weekly_rankings.load_for_league(
            league, season, first_week, force_refresh=force_refresh
        )
        if by_position:
            expert_summary = weekly_rankings.attach(everyone, by_position)
    if expert_summary is None:
        for player in everyone:
            player.setdefault("weekly_projection", None)
    lineup.score(everyone, first_week)

    roster_size = sum(
        int(count or 0) for count in league.settings.position_slot_counts.values()
    ) - int(league.settings.position_slot_counts.get("IR", 0) or 0)
    occupying = [p for p in mine if droppable(p)]
    roster_full = len(occupying) >= roster_size

    settings = waiver_settings(league)
    budget_left = (settings["budget"] or 0) - (team.acquisition_budget_spent or 0)
    opponents = [
        {
            "team": t.team_name,
            "budget_left": (settings["budget"] or 0) - (t.acquisition_budget_spent or 0),
        }
        for t in league.teams
        if t.team_id != team_id
    ]

    swaps = best_swaps(mine, free_agents, slots, weeks, first_week, roster_full)
    for swap in swaps:
        swap["bid"] = suggest_bid(
            swap["gain_per_week"],
            budget_left,
            settings["minimum_bid"],
            swap["add"].get("percent_owned"),
        )
        swap["bye_cover"] = bye_weeks_covered(swap["add"], mine, weeks)

    return {
        "league_name": league.settings.name,
        "first_week": first_week,
        "weeks": weeks,
        "settings": settings,
        "budget_left": budget_left,
        "opponents": sorted(opponents, key=lambda o: o["budget_left"], reverse=True),
        "swaps": swaps,
        "roster_full": roster_full,
        "expert_summary": expert_summary,
    }
