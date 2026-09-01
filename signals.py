"""
Where the three sources disagree about a player.

The board blends three opinions: ESPN's projections (turned into VOR), the
FantasyPros expert consensus, and how much of the ESPN world already rosters
him. Most of the time those three broadly agree, and the blended rank is the
whole story.

The interesting players are the ones where they do NOT agree, because a
disagreement is the only place a bargain or a trap can hide. If every source
already loves someone he is priced correctly, and there is no edge in taking
him -- you are paying exactly what he is worth.

Two things this deliberately does not do:

  * It does not predict. "value" does not mean he will be good. It means the
    experts rate him higher than the projections and the room do. That is a
    fact about the sources, not a forecast, and the wording on screen says so.
  * It does not read prose. Nothing here comes from an article. Same rule as
    everywhere else on this board: facts vote, prose does not.

Three traps had to be designed around. All three were found in your real
board, not imagined:

  1. Comparing across positions is meaningless. Our VOR and the FantasyPros
     overall list set their positional baselines differently, so a plain
     comparison called almost every quarterback overrated and almost every
     tight end too. That was an artefact of the two methods, not a fact about
     the players. Everything here compares a player only with others at his
     own position.

  2. Roster percentage saturates at the top. Thirty-four of the top 150 sit
     at 99% or above, so the gaps between them are rounding rather than
     opinion. Above that line the room is ignored instead of trusted.

  3. Expert disagreement has to be judged against a player's neighbours.
     Measured naively, the single most agreed-upon player on the board --
     ranked 1st, 2nd and 3rd by everybody -- came out as the most volatile
     player in the league, because half a rank of disagreement looks enormous
     next to a rank of 1. Disagreement is now measured against how much the
     experts typically disagree that far down the board.
"""

import statistics
from collections import defaultdict


# Kickers and defences are ranked on their own separate lists, and nearly
# every kicker is rostered everywhere, so comparing their sources produces
# nonsense -- one kicker looked like the 17th most valuable player alive.
SKIP_POSITIONS = {"K", "D/ST"}

# Above this roster percentage everyone is tied in practice, so the room
# stops being a usable opinion.
SATURATED_OWNERSHIP = 99.0

# How many players either side of him count as "his neighbours" when working
# out whether the experts are unusually split.
NEIGHBOURS = 12

# How much more split than his neighbours he has to be before it is worth
# telling you about.
SPLIT_MULTIPLE = 2.0

# The very top of a position is always tightly ranked; calling it split is
# noise.
SPLIT_MIN_RANK = 3


def _rank_within_position(players, key, high_is_better):
    """
    Ranks players against others at their own position. 1 = best.

    Doing this per position is the whole trick -- see trap 1 in the notes at
    the top of this file.
    """
    ranks = {}
    by_position = defaultdict(list)
    for player in players:
        by_position[player["position"]].append(player)

    for group in by_position.values():
        group = sorted(group, key=lambda pl: pl[key], reverse=high_is_better)
        for place, player in enumerate(group, start=1):
            ranks[id(player)] = place
    return ranks


def _typical_split(players, expert_ranks):
    """
    How much the experts normally disagree about a player this far down this
    position's list. Used as the yardstick -- see trap 3.
    """
    yardstick = {}
    by_position = defaultdict(list)
    for player in players:
        by_position[player["position"]].append(player)

    for group in by_position.values():
        group = sorted(group, key=lambda pl: expert_ranks[id(pl)])
        for index, player in enumerate(group):
            window = group[max(0, index - NEIGHBOURS): index + NEIGHBOURS + 1]
            spreads = [p["ecr_spread"] for p in window if p.get("ecr_spread")]
            yardstick[id(player)] = statistics.median(spreads) if spreads else None
    return yardstick


def _threshold(expert_rank):
    """
    How big a disagreement has to be before it means anything.

    It scales, because being three spots apart on the RB4 is a real argument
    and being three spots apart on the RB40 is a coin flip.
    """
    return max(6.0, 0.12 * expert_rank + 4.0)


def _pos_label(position, rank):
    return "%s%d" % (position, rank)


def attach(players):
    """
    Adds player["signals"] -- a list of {tag, label, why} -- to every player.

    Most players get an empty list, and that is the point. A flag on every
    row would be no more useful than a flag on none.
    """
    for player in players:
        player["signals"] = []

    pool = [
        p for p in players
        if p["position"] not in SKIP_POSITIONS
        and p.get("expert_rank")
        and p.get("ecr")
    ]
    if not pool:
        return {"used": False, "value": 0, "overpriced": 0, "split": 0}

    by_projection = _rank_within_position(pool, "vor", True)
    by_expert = _rank_within_position(pool, "ecr", False)
    by_room = _rank_within_position(pool, "percent_owned", True)
    yardstick = _typical_split(pool, by_expert)

    counts = {"value": 0, "overpriced": 0, "split": 0}

    for player in pool:
        position = player["position"]
        expert = by_expert[id(player)]
        projection = by_projection[id(player)]
        # Trap 2: only trust the room when it is actually saying something.
        room = by_room[id(player)] if player["percent_owned"] < SATURATED_OWNERSHIP else None

        expert_text = _pos_label(position, expert)
        projection_text = _pos_label(position, projection)
        room_text = _pos_label(position, room) if room else None

        gaps = [projection - expert] + ([room - expert] if room else [])
        needed = _threshold(expert)

        # Everyone the experts outrank -- they are the odd one out, in his
        # favour.
        if min(gaps) >= needed:
            others = "the projections have him %s" % projection_text
            if room_text:
                others += " and the room has him %s" % room_text
            player["signals"].append({
                "tag": "value",
                "label": "value",
                "why": "Experts rank him %s, but %s. They are the outlier in "
                       "his favour." % (expert_text, others),
            })
            counts["value"] += 1

        # The mirror image: everybody else is higher on him than the experts.
        if max(gaps) <= -needed:
            others = "the projections have him %s" % projection_text
            if room_text:
                others += " and the room has him %s" % room_text
            player["signals"].append({
                "tag": "overpriced",
                "label": "overpriced",
                "why": "Experts rank him only %s, while %s. You would be "
                       "paying ahead of what the experts see." % (expert_text, others),
            })
            counts["overpriced"] += 1

        # The experts cannot agree with each other about him.
        typical = yardstick.get(id(player))
        if (player.get("ecr_spread") and typical and typical > 0
                and player["ecr_spread"] >= SPLIT_MULTIPLE * typical
                and expert > SPLIT_MIN_RANK):
            player["signals"].append({
                "tag": "split",
                "label": "experts split",
                "why": "The experts do not agree on him at all -- ranked as "
                       "high as %d and as low as %d, far wider than anyone "
                       "near him." % (player["ecr_best"], player["ecr_worst"]),
            })
            counts["split"] += 1

    return {
        "used": True,
        "considered": len(pool),
        "flagged": sum(1 for p in pool if p["signals"]),
        **counts,
    }
