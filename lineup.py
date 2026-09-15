"""
Who should be in your starting lineup this week.

The job here is narrow on purpose: take your roster, work out what each
player is worth on Sunday, and then work out the best legal arrangement of
them. Two separate problems, and the second one is easy to get wrong by
eyeballing it -- with two flex spots there are a lot of combinations, and
"start my highest projected players" is not the same thing as "start the
best lineup" once positional slots get in the way.

How a player's weekly value is worked out:

  * ESPN's projection for the week, and
  * FantasyPros' projection for the week (the consensus of ~100 analysts).

Both are in points, so they can simply be averaged -- no rank juggling
needed. They get equal weight. ESPN is slow to react to news; the experts
are faster but noisier. Neither deserves to win by default.

The gap between the two is kept, not thrown away. That gap IS the signal:
where ESPN and a hundred analysts disagree about the same player in the
same week, somebody knows something, and it is worth putting in front of
you rather than averaging into silence.

Design rule inherited from the draft board -- FACTS VOTE, PROSE DOES NOT.
Numbers (both projections, the expert spread, how far his rank moved) are
allowed to move a player's score. Injury designations are structured facts,
so they vote too. Written sentences are shown to you and never scored.
"""

from collections import defaultdict

import rankings


# Equal weight. See the note above: neither source has earned the tiebreak.
ESPN_WEIGHT = 0.5
EXPERT_WEIGHT = 0.5

# What ESPN's injury designations are worth as a multiplier on a player's
# projection. These are not guesses about medicine -- they are the historical
# reality of what each designation means for whether a man plays at all.
#
# QUESTIONABLE deliberately sits at 1.0. ESPN and FantasyPros have both
# already discounted a questionable player inside the projections we just
# averaged, so applying our own haircut on top would charge him twice for the
# same ankle. It is flagged loudly instead, because the risk is real even
# though the points have already been adjusted.
INJURY_MULTIPLIERS = {
    "ACTIVE": 1.0,
    "NORMAL": 1.0,
    "PROBABLE": 1.0,
    "QUESTIONABLE": 1.0,
    "DOUBTFUL": 0.35,
    "OUT": 0.0,
    "INJURY_RESERVE": 0.0,
    "SUSPENSION": 0.0,
}

# Designations that mean "he is not playing", so the tool should never leave
# him in your lineup no matter how good he is.
CANNOT_PLAY = {"OUT", "INJURY_RESERVE", "SUSPENSION", "DOUBTFUL"}

# Which positions each lineup slot will accept. Only the slots your leagues
# actually use are listed; anything else is treated as bench.
SLOT_ELIGIBILITY = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "K": {"K"},
    "D/ST": {"D/ST"},
    "RB/WR": {"RB", "WR"},
    "WR/TE": {"WR", "TE"},
    "RB/WR/TE": {"RB", "WR", "TE"},
    "OP": {"QB", "RB", "WR", "TE"},
}

# Slots that hold players who are not playing this week.
BENCH_SLOTS = {"BE", "IR", "ER"}


# ---------------------------------------------------------------------------
# Reading your roster
# ---------------------------------------------------------------------------

def my_team(league, team_id):
    """Finds your team in the league, by the ID ESPN gave it."""
    for team in league.teams:
        if team.team_id == team_id:
            return team
    raise LookupError(f"no team {team_id} in {league.settings.name}")


def rosters_for_week(league, week):
    """
    Every team's roster as ESPN sees it for one specific week.

    The rosters the ESPN library loads on connecting carry projections for
    the CURRENT week only. Asking about next week from those gives every
    rostered player zero -- which quietly made every free agent look like an
    upgrade and emptied next week's start/sit. So rosters are re-read for the
    week actually being planned. Falls back to the loaded rosters for the
    current week, or if ESPN will not answer.

    Returns {team_id: [ESPN player objects]}.
    """
    loaded = {team.team_id: team.roster for team in league.teams}
    if week == league.current_week:
        return loaded
    try:
        from espn_api.football.player import Player

        data = league.espn_request.league_get(
            params={"view": ["mRoster"], "scoringPeriodId": week}
        )
        return {
            team["id"]: [Player(entry, league.year) for entry in team["roster"]["entries"]]
            for team in data.get("teams") or []
        } or loaded
    except Exception:
        return loaded


def weekly_projection(player, week):
    """
    ESPN's projection for one player in one week.

    ESPN keys its per-week stats by scoring period, and a player with no
    entry for the week is projected for nothing -- which is exactly what a
    bye week looks like, and is the right answer in that case anyway.
    """
    stats = getattr(player, "stats", None) or {}
    detail = stats.get(week) or stats.get(str(week)) or {}
    try:
        return float(detail.get("projected_points") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def roster(league, team_id, week, rosters=None, byes=None):
    """
    Your roster as plain dictionaries, in the same shape the rest of this
    project already uses, so the existing commentary and signal code can
    read them without translation.
    """
    rosters = rosters or rosters_for_week(league, week)
    if byes is None:
        # ESPN's real bye table. Never guess a bye from a zero projection:
        # ESPN also projects zero for a player it expects to miss the game
        # (Kyler Murray in the concussion protocol, week 2), and calling
        # that a bye hides the real reason he is out.
        import waivers
        byes = waivers.bye_weeks(league)
    if team_id not in rosters:
        raise LookupError(f"no team {team_id} in {league.settings.name}")
    players = []
    for player in rosters[team_id]:
        slot = getattr(player, "lineupSlot", "") or ""
        players.append(
            {
                "player_id": getattr(player, "playerId", None),
                "name": player.name,
                "position": player.position,
                "pro_team": player.proTeam,
                "espn_projection": round(weekly_projection(player, week), 2),
                "injury_status": rankings.clean_injury_status(player),
                "current_slot": slot,
                "currently_starting": slot not in BENCH_SLOTS and slot != "",
                "percent_owned": round(getattr(player, "percent_owned", 0.0) or 0.0, 1),
                "bye_week": byes.get(player.proTeam) if byes else rankings.find_bye_week(player),
            }
        )
    return players


# ---------------------------------------------------------------------------
# What a player is worth this week
# ---------------------------------------------------------------------------

def score(players, week):
    """
    Gives every player a single number for this week, in place.

    Also records how the number was arrived at, so the tool can always
    explain itself rather than handing you a figure and asking for trust.
    """
    for player in players:
        espn = player.get("espn_projection") or 0.0
        expert = player.get("weekly_projection")

        on_bye = player.get("bye_week") == week

        if on_bye:
            # A player on bye does not play. ESPN already projects him at
            # zero, but FantasyPros simply leaves him off its weekly list,
            # and averaging a real ESPN zero with a missing expert number
            # must not accidentally resurrect him.
            blended = 0.0
            basis = "on bye"
        elif expert is None:
            blended = espn
            basis = "ESPN only (experts do not rank him this week)"
        else:
            blended = ESPN_WEIGHT * espn + EXPERT_WEIGHT * expert
            basis = "ESPN and experts, averaged"

        status = player.get("injury_status") or "ACTIVE"
        multiplier = INJURY_MULTIPLIERS.get(status, 1.0)

        # For questionable players only, `status.py` may have found a practice
        # report -- which says whether this particular questionable player is
        # better or worse off than the average one the projections assumed.
        # It is 1.0 when there is no report, so this is a no-op without it.
        practice = player.get("practice_multiplier") or 1.0

        player["blended_projection"] = round(blended, 2)
        player["injury_multiplier"] = multiplier
        player["practice_multiplier"] = practice
        player["score"] = round(blended * multiplier * practice, 2)
        player["score_basis"] = basis
        player["on_bye"] = on_bye
        player["can_play"] = not on_bye and status not in CANNOT_PLAY

        # The disagreement between the two sources, in points. Positive means
        # the experts are higher on him than ESPN is.
        player["source_gap"] = (
            None if expert is None or on_bye else round(expert - espn, 2)
        )
    return players


# ---------------------------------------------------------------------------
# Solving for the best legal lineup
# ---------------------------------------------------------------------------

def open_slots(league):
    """
    The starting slots this league actually uses, one entry per slot.

    A league with two flex spots produces two separate 'RB/WR/TE' entries,
    because each one has to be filled by a different player.
    """
    counts = league.settings.position_slot_counts
    slots = []
    for name, count in counts.items():
        if name in SLOT_ELIGIBILITY:
            slots.extend([name] * int(count or 0))
    return slots


def best_lineup(players, slots):
    """
    Works out the highest-scoring legal lineup.

    The method is to fill the fussiest slots first: a slot that only accepts
    quarterbacks gets filled before a flex spot that would take almost
    anyone. That ordering matters. Filling the flex first can strand a
    dedicated slot with nobody left to fill it, and greedily handing the flex
    your best remaining player can quietly cost you points -- if your two
    best running backs both go into RB slots and your third-best is better
    than your third receiver, the flex should take the running back.

    Because every flexible slot here accepts a superset of what the stricter
    ones accept, filling in that order gives the genuinely best answer rather
    than merely a good one.

    Players who cannot play -- out, on injured reserve, suspended, on bye --
    are never assigned, even if their projection is the highest on the roster.
    """
    available = sorted(
        [p for p in players if p.get("can_play")],
        key=lambda p: p.get("score") or 0.0,
        reverse=True,
    )
    ordered = sorted(slots, key=lambda s: len(SLOT_ELIGIBILITY[s]))

    assigned = {}
    used = set()
    for slot in ordered:
        eligible = SLOT_ELIGIBILITY[slot]
        for player in available:
            key = id(player)
            if key in used or player["position"] not in eligible:
                continue
            assigned.setdefault(slot, []).append(player)
            used.add(key)
            break

    starters = [p for group in assigned.values() for p in group]
    bench = [p for p in players if id(p) not in used]
    return assigned, starters, bench


def lineup_total(starters):
    return round(sum(p.get("score") or 0.0 for p in starters), 2)


# ---------------------------------------------------------------------------
# What to actually change
# ---------------------------------------------------------------------------

def changes(players, recommended_starters):
    """
    The moves that turn your current lineup into the recommended one.

    Reported as pairs -- bench this man, start that one -- matched up by
    position where possible, because that is how you will actually make the
    change in the ESPN app.
    """
    recommended = {id(p) for p in recommended_starters}
    benching = [
        p for p in players if p.get("currently_starting") and id(p) not in recommended
    ]
    starting = [
        p for p in players if not p.get("currently_starting") and id(p) in recommended
    ]

    benching.sort(key=lambda p: p.get("score") or 0.0)
    starting.sort(key=lambda p: p.get("score") or 0.0, reverse=True)

    pairs, spare_out, spare_in = [], list(benching), list(starting)
    for candidate in list(spare_in):
        match = next(
            (p for p in spare_out if p["position"] == candidate["position"]), None
        )
        if match:
            pairs.append((match, candidate))
            spare_out.remove(match)
            spare_in.remove(candidate)

    # Anything left over is a cross-position move -- benching a receiver for a
    # running back in a flex spot, say -- so pair them off in order.
    while spare_out and spare_in:
        pairs.append((spare_out.pop(0), spare_in.pop(0)))

    return pairs


def current_starters(players):
    return [p for p in players if p.get("currently_starting")]


# ---------------------------------------------------------------------------
# Why the tool thinks what it thinks
# ---------------------------------------------------------------------------

def reasons(player):
    """
    Short, plain-language notes explaining a player's number.

    Only checkable facts appear here -- projections, designations, rank
    movement, expert disagreement. Nothing in this list is an opinion the
    tool formed by reading prose.
    """
    notes = []

    if player.get("on_bye"):
        notes.append("on bye this week")
        return notes

    status = player.get("injury_status")
    if status in CANNOT_PLAY:
        notes.append(f"{status.replace('_', ' ').lower()} -- cannot play")
    elif status == "QUESTIONABLE":
        import status as game_status

        practice = game_status.describe_practice(player)
        if practice:
            # The practice report is the useful half of "questionable".
            # Coaches list players questionable partly to keep the other team
            # guessing; whether he actually practised is much harder to fake.
            notes.append(f"questionable -- {practice}")
        else:
            notes.append("questionable -- confirm before kickoff")

        moved = player.get("practice_multiplier") or 1.0
        if moved < 1.0:
            notes.append(f"scored down {(1 - moved) * 100:.0f}% on that practice report")
        elif moved > 1.0:
            notes.append(f"scored up {(moved - 1) * 100:.0f}% on that practice report")

    gap = player.get("source_gap")
    if gap is not None and abs(gap) >= 2.0:
        who = "experts higher than ESPN" if gap > 0 else "ESPN higher than experts"
        notes.append(f"{who} by {abs(gap):.1f} pts")

    delta = player.get("weekly_delta")
    if delta is not None and abs(delta) >= 5:
        way = "up" if delta > 0 else "down"
        notes.append(f"experts moved him {way} {abs(int(delta))} spots this week")

    spread = player.get("weekly_spread")
    if spread is not None and spread >= 8:
        notes.append(f"experts split on him (spread {spread:.0f})")

    if player.get("weekly_pos_rank"):
        notes.append(f"expert rank {player['weekly_pos_rank']}")

    if player.get("weather"):
        notes.append(player["weather"])

    if player.get("matchup_quality"):
        # Shown only. The projections above already price the opponent in.
        notes.append(f"{player['matchup_quality']} matchup -- {player['matchup']}")

    return notes


# ---------------------------------------------------------------------------
# The whole thing, end to end
# ---------------------------------------------------------------------------

def build(league, team_id, week, season, use_experts=True, force_refresh=False):
    """
    Reads your roster, values it, and solves for the best lineup.

    Returns everything the callers need to print or serve, including a note
    on whether the expert numbers actually arrived -- so a quiet failure to
    reach FantasyPros can be reported rather than hidden.
    """
    import status as game_status
    import weekly_rankings

    players = roster(league, team_id, week)

    # Kickoff times and practice reports, before scoring -- the practice
    # report feeds into the score, so it has to arrive first.
    try:
        game_status.attach(players, season, week)
    except Exception:
        pass  # the countdown and the notes are a bonus, not the board

    try:
        import usage
        usage.attach(players, usage.load(season))
    except Exception:
        pass  # snap and target data is shown, never scored here

    import defense
    defense.attach_for_league(league, season, week, players)  # shown, never scored
    import weather
    weather.attach(players, season, week)  # shown, never scored

    expert_summary = None
    scoring = None
    if use_experts:
        scoring, by_position = weekly_rankings.load_for_league(
            league, season, week, force_refresh=force_refresh
        )
        if by_position:
            expert_summary = weekly_rankings.attach(players, by_position)
            expert_summary["positions_loaded"] = sorted(by_position)

    if expert_summary is None:
        for player in players:
            player.setdefault("weekly_projection", None)
            player.setdefault("weekly_pos_rank", None)
            player.setdefault("weekly_spread", None)
            player.setdefault("weekly_delta", None)
            player.setdefault("weekly_grade", None)
            player.setdefault("opponent", None)

    score(players, week)
    slots = open_slots(league)
    assigned, starters, bench = best_lineup(players, slots)

    return {
        "league_name": league.settings.name,
        "week": week,
        "scoring": scoring,
        "players": players,
        "slots": slots,
        "assigned": assigned,
        "starters": starters,
        "bench": bench,
        "recommended_total": lineup_total(starters),
        "current_total": lineup_total(current_starters(players)),
        "changes": changes(players, starters),
        "expert_summary": expert_summary,
    }
