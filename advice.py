"""
Decides who YOU should take next.

rankings.py answers "what is this player worth?" This file answers the
harder question you actually face when you are on the clock: given who is
already on your roster, who is still available, and how long until your
next turn -- who should you take right now?

Three things pull on that answer:

  1. Raw value (VOR). The starting point.
  2. What you still need. A fourth running back is worth less to you than
     a first tight end, no matter what the raw numbers say.
  3. Whether he will still be there next time. This is the part people get
     wrong. If four backs are left in a tier, you can take a receiver first
     and still get one of them. If one is left and you do not pick again for
     eighteen picks, he is gone -- take him now.

That third point is why this tool beats reading a static list.
"""

FLEX_POSITIONS = ("RB", "WR", "TE")
FILLER_POSITIONS = ("K", "D/ST")

# How loudly scarcity is allowed to shout. Higher means the tool pushes
# harder to grab the last player in a tier before he disappears.
URGENCY_WEIGHT = 0.9

# Kickers and defenses get drafted in the last couple of rounds, never before.
FILLER_ROUNDS_FROM_END = 2

# Late in the draft everyone left is below replacement level, so VOR stops
# telling them apart. This lets raw projected points break the tie.
DEPTH_TIEBREAK = 0.02

# How far the outside experts are allowed to move a player, at most: 30% up
# or down. They get a real say but never the final word, because they are
# ranking a generic league and we are drafting YOURS -- only our own VOR
# knows this league has two flex spots. Everything about tiers and scarcity
# stays driven by VOR for the same reason.
EXPERT_TILT = 0.30

# A disagreement of this many ranks counts as total disagreement. Beyond it
# the adjustment stops growing, so one weird outlier cannot run away with the
# board.
EXPERT_TILT_SPAN = 60

# Only mention the experts in the reasons when they differ from ESPN by more
# than this many spots -- below that it is noise, not insight.
EXPERT_NOTE_GAP = 20

# How much expert disagreement counts as "nobody knows what this guy is".
# FantasyPros publishes the standard deviation of every analyst's rank.
EXPERT_SPREAD_NOTE = 8.0


# ---------------------------------------------------------------------------
# What your roster is supposed to look like
# ---------------------------------------------------------------------------

def roster_plan(league):
    """Reads the league's roster rules into a simple shape we can reason about."""
    slots = league.settings.position_slot_counts

    starters = {
        "QB": slots.get("QB", 0),
        "RB": slots.get("RB", 0),
        "WR": slots.get("WR", 0),
        "TE": slots.get("TE", 0),
        "K": slots.get("K", 0),
        "D/ST": slots.get("D/ST", 0),
    }
    flex = slots.get("RB/WR/TE", 0)
    bench = slots.get("BE", 0)

    return {
        "starters": starters,
        "flex": flex,
        "bench": bench,
        "teams": league.settings.team_count,
        "total_rounds": sum(starters.values()) + flex + bench,
    }


def count_by_position(roster):
    counts = {}
    for player in roster:
        counts[player["position"]] = counts.get(player["position"], 0) + 1
    return counts


def open_starting_slots(roster, plan):
    """Which starting spots you still have nobody for."""
    counts = count_by_position(roster)
    open_slots = {}

    for position, needed in plan["starters"].items():
        missing = needed - counts.get(position, 0)
        if missing > 0:
            open_slots[position] = missing

    # Flex is whatever is left over from RB/WR/TE after their own slots fill.
    spare = sum(
        max(0, counts.get(position, 0) - plan["starters"].get(position, 0))
        for position in FLEX_POSITIONS
    )
    flex_open = max(0, plan["flex"] - spare)
    if flex_open:
        open_slots["FLEX"] = flex_open

    return open_slots


# ---------------------------------------------------------------------------
# Snake draft arithmetic -- when do you pick again?
# ---------------------------------------------------------------------------

def my_pick_numbers(draft_slot, teams, rounds):
    """
    Every overall pick number that belongs to you.

    A snake draft reverses each round: if you are 3rd of 12 you pick 3rd in
    round one, then 10th in round two (22nd overall), and so on. That is why
    the gap between your picks swings wildly -- and why "can I wait on him?"
    has a different answer depending on where you sit.
    """
    picks = []
    for round_number in range(1, rounds + 1):
        if round_number % 2 == 1:
            picks.append((round_number - 1) * teams + draft_slot)
        else:
            picks.append((round_number - 1) * teams + (teams - draft_slot + 1))
    return picks


def turn_info(draft_slot, plan, picks_made):
    """
    Where the draft stands relative to you: is it your turn, and if not,
    how many picks until it is?
    """
    teams = plan["teams"]
    rounds = plan["total_rounds"]
    mine = my_pick_numbers(draft_slot, teams, rounds)

    current_pick = picks_made + 1
    upcoming = [pick for pick in mine if pick >= current_pick]

    if not upcoming:
        return {
            "on_the_clock": False,
            "current_pick": current_pick,
            "round": rounds,
            "picks_until_turn": None,
            "picks_until_turn_after": None,
            "rounds_left": 0,
            "draft_over": True,
        }

    next_pick = upcoming[0]
    pick_after = upcoming[1] if len(upcoming) > 1 else None
    current_round = (current_pick - 1) // teams + 1

    return {
        "on_the_clock": next_pick == current_pick,
        "current_pick": current_pick,
        "round": min(current_round, rounds),
        "picks_until_turn": next_pick - current_pick,
        # How many other picks happen between this turn of yours and the next
        # one. This is the number that decides whether you can wait on a guy.
        "picks_until_turn_after": (pick_after - next_pick - 1) if pick_after else None,
        "rounds_left": len(upcoming),
        "draft_over": False,
    }


# ---------------------------------------------------------------------------
# Weighing a player against your roster
# ---------------------------------------------------------------------------

def roster_holes(roster, plan):
    """
    The starting spots you still have nobody for, split into the ones that
    win you games (QB/RB/WR/TE) and the two you just have to fill by the
    end (K and defense).
    """
    counts = count_by_position(roster)

    skill = {}
    filler = 0
    for position, required in plan["starters"].items():
        missing = required - counts.get(position, 0)
        if missing <= 0:
            continue
        if position in FILLER_POSITIONS:
            filler += missing
        else:
            skill[position] = missing

    spare = sum(
        max(0, counts.get(position, 0) - plan["starters"].get(position, 0))
        for position in FLEX_POSITIONS
    )
    return {
        "skill": skill,
        "skill_total": sum(skill.values()),
        "filler_total": filler,
        "flex_open": max(0, plan["flex"] - spare),
    }


def need_multiplier(position, roster, plan, rounds_left):
    """
    How much your roster wants this position right now, as a multiplier on
    raw value. Above 1 means "you need this"; below means "you are stocked".

    The rule that matters most: fill your mandatory starting spots before
    you take a fourth running back. A great bench player scores you zero
    points; a mediocre starter scores you every week.
    """
    counts = count_by_position(roster)
    have = counts.get(position, 0)
    required = plan["starters"].get(position, 0)
    holes = roster_holes(roster, plan)

    # Kickers and defenses score about the same no matter which one you get,
    # so spending an early pick on one wastes it. Suppress them almost to
    # nothing, then make them urgent once you are nearly out of picks.
    if position in FILLER_POSITIONS:
        if have >= required:
            return 0.0  # never take a second one
        if rounds_left <= holes["filler_total"]:
            return 10.0  # take one right now or finish the draft short
        if rounds_left <= holes["filler_total"] + 1:
            return 6.0
        if rounds_left <= holes["filler_total"] + FILLER_ROUNDS_FROM_END:
            return 2.0
        return 0.01

    # A required starting spot here is still empty. That is the priority, and
    # it gets sharper as you run out of picks to fix it with.
    if position in holes["skill"]:
        if rounds_left <= holes["skill_total"] + holes["filler_total"]:
            return 3.0
        if rounds_left <= holes["skill_total"] + holes["filler_total"] + 2:
            return 1.9
        return 1.35

    # This position's starting spots are full, but others are not. Do not
    # stack depth on a position you have already covered while a starting
    # spot sits empty.
    if holes["skill_total"]:
        return 0.45

    # One quarterback and one tight end is almost always enough. Backups at
    # these spots sit on your bench doing nothing.
    if position == "QB":
        return 0.20
    if position == "TE":
        return 0.28

    # Everything mandatory is covered -- now the flex is worth competing for.
    if holes["flex_open"]:
        return 1.05

    # Beyond that it is bench depth, worth a bit less with each one you add.
    surplus = have - required
    return max(0.45, 0.8 ** surplus)


def tier_scarcity(player, available, picks_until_next):
    """
    Two numbers that decide urgency:

      - how many players are left in this player's tier
      - how much worse the next tier down is

    If the tier is nearly empty and you do not pick again for a while, the
    drop is about to become your problem.
    """
    same_tier = [
        other
        for other in available
        if other["position"] == player["position"]
        and other["tier_number"] == player["tier_number"]
    ]

    next_tier_best = max(
        (
            other["vor"]
            for other in available
            if other["position"] == player["position"]
            and other["tier_number"] > player["tier_number"]
        ),
        default=None,
    )
    drop = player["vor"] - next_tier_best if next_tier_best is not None else 0.0

    # Risk that the whole tier is gone before you pick again. With N players
    # left and P picks in between, N >= P means it almost certainly survives.
    if not picks_until_next:
        risk = 0.0
    else:
        risk = (picks_until_next - len(same_tier) + 1) / float(picks_until_next)
    risk = max(0.0, min(1.0, risk))

    return {"left_in_tier": len(same_tier), "drop_to_next_tier": max(0.0, drop), "risk": risk}


def expert_adjustment(player):
    """
    A gentle nudge up or down based on how the outside experts see a player
    compared with ESPN's projections.

    Returns a multiplier near 1. It is capped deliberately: where ESPN and a
    hundred analysts disagree, the analysts are usually the ones who have
    heard about the holdout or the camp report -- but they are ranking a
    generic league, so they never get to overrule your league's own maths
    outright.

    Returns exactly 1.0 when there is no expert data, which is what makes the
    whole thing safe to fail.
    """
    gap = player.get("expert_gap")
    if gap is None:
        return 1.0

    tilt = max(-1.0, min(1.0, gap / float(EXPERT_TILT_SPAN)))
    return 1.0 + EXPERT_TILT * tilt


def bye_clash(player, roster):
    """How many players you already have share this player's bye week."""
    if not player.get("bye_week"):
        return 0
    return sum(
        1
        for other in roster
        if other.get("bye_week") == player["bye_week"]
        and other["position"] == player["position"]
    )


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------

def explain(player, need, scarcity, open_slots, clash, turn):
    """Plain-language reasons, most important first."""
    reasons = []
    position = player["position"]

    if position in FILLER_POSITIONS:
        if need >= 6:
            reasons.append(f"Almost out of picks -- fill {position} now.")
        elif need >= 1:
            reasons.append(f"Last rounds -- time to fill {position}.")
        else:
            reasons.append("Too early for a kicker or defense.")
        return reasons  # scarcity talk is meaningless for these two

    if position in open_slots:
        if need >= 3:
            reasons.append(f"Your {position} spot is still empty and picks are running out.")
        else:
            reasons.append(f"Fills your open {position} spot.")
    elif "FLEX" in open_slots and position in FLEX_POSITIONS:
        reasons.append("Fills your open flex spot.")

    gap = turn.get("picks_until_turn_after")
    if player["vor"] <= 0:
        # Below replacement level -- there is no scarcity story worth telling.
        reasons.append("Bench depth -- no better than a waiver pickup.")
        return reasons

    if scarcity["risk"] >= 0.6 and scarcity["drop_to_next_tier"] >= 8:
        if scarcity["left_in_tier"] == 1:
            reasons.append(
                f"Last {position} in this tier -- the next one is "
                f"{scarcity['drop_to_next_tier']:.0f} pts worse"
                + (f" and you pick again in {gap}." if gap else ".")
            )
        else:
            reasons.append(
                f"Only {scarcity['left_in_tier']} left in this tier, and you "
                f"pick again in {gap}." if gap else
                f"Only {scarcity['left_in_tier']} left in this tier."
            )
    elif scarcity["left_in_tier"] >= 5 and gap:
        reasons.append(
            f"{scarcity['left_in_tier']} others in this tier -- safe to wait."
        )

    if need < 0.6 and position not in FILLER_POSITIONS:
        reasons.append(f"You are already deep at {position}.")

    # What the outside experts add that ESPN cannot: a second opinion, and an
    # honest admission of how uncertain that opinion is.
    gap = player.get("expert_gap")
    if gap is not None and abs(gap) >= EXPERT_NOTE_GAP:
        if gap > 0:
            reasons.append(
                f"Experts rank him {int(gap)} spots higher than ESPN's projections do."
            )
        else:
            reasons.append(
                f"Experts rank him {int(-gap)} spots lower than ESPN's projections do."
            )

    spread = player.get("ecr_spread")
    best, worst = player.get("ecr_best"), player.get("ecr_worst")
    if spread and spread >= EXPERT_SPREAD_NOTE and best and worst:
        reasons.append(
            f"Experts cannot agree on him -- ranked anywhere from "
            f"{int(best)} to {int(worst)}."
        )

    if player["injury_status"] not in ("ACTIVE", "NORMAL"):
        reasons.append(f"Carrying a {player['injury_status'].lower()} tag.")

    if clash >= 2:
        reasons.append(f"Third {position} on bye week {player['bye_week']}.")

    return reasons


def recommend(board, drafted_ids, my_roster, plan, draft_slot, picks_made, limit=40):
    """
    The main call. Hands back the best available players for YOU, in order,
    each with the reasoning behind it.
    """
    turn = turn_info(draft_slot, plan, picks_made)
    open_slots = open_starting_slots(my_roster, plan)

    available = [p for p in board if p["player_id"] not in drafted_ids]

    # When judging "will he last?", what matters is the gap after your next
    # turn if you are on the clock, or the wait until your turn if you are not.
    gap = turn.get("picks_until_turn_after") if turn["on_the_clock"] else turn.get("picks_until_turn")

    scored = []
    for player in available:
        need = need_multiplier(player["position"], my_roster, plan, turn["rounds_left"])
        scarcity = tier_scarcity(player, available, gap)
        clash = bye_clash(player, my_roster)

        # VOR goes negative for late-round players -- they are, by definition,
        # worse than the free replacement. Floor it at zero, because a
        # negative number multiplied by a need factor scrambles the ordering
        # and can make an unwanted kicker look better than a useful bench guy.
        value = max(player["vor"], 0.0)

        # Scarcity only matters for players actually worth starting. Deep in a
        # position the gaps between tiers get enormous -- the 29th quarterback
        # can sit atop a 60-point cliff -- but missing out on a player who is
        # worse than a free agent costs you nothing. So urgency is switched off
        # below replacement level and can never exceed the player's own value.
        urgency = 0.0
        if value > 0:
            urgency = (
                min(scarcity["drop_to_next_tier"], value)
                * scarcity["risk"]
                * URGENCY_WEIGHT
            )

        score = value * need
        score += urgency * need
        # Once VOR bottoms out at zero, raw projected points is what still
        # separates one bench option from another.
        score += DEPTH_TIEBREAK * player["projection"] * need
        # Then let the outside experts nudge the whole thing up or down.
        score *= expert_adjustment(player)
        if clash >= 2:
            score -= 4

        scored.append(
            dict(
                player,
                score=round(score, 1),
                need=round(need, 2),
                left_in_tier=scarcity["left_in_tier"],
                drop_to_next_tier=round(scarcity["drop_to_next_tier"], 1),
                reasons=explain(player, need, scarcity, open_slots, clash, turn),
            )
        )

    scored.sort(key=lambda item: item["score"], reverse=True)

    return {
        "turn": turn,
        "open_slots": open_slots,
        "recommendations": scored[:limit],
        "available_count": len(available),
    }
