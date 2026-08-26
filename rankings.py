"""
Works out what every player is worth in one specific league.

The idea behind this, in one paragraph: ESPN's raw projections are not a
draft order. They say Josh Allen (370 projected points) is worth more than
Puka Nacua (295). But you only start ONE quarterback, and the 12th-best
quarterback also scores a pile of points. Meanwhile the 12th-best receiver
does not. So what matters at a draft is not "how many points will he score"
but "how many MORE than the guy I could get for free at the same position
later." That gap is called value over replacement, or VOR, and it is what
this file computes.

Everything here depends on the league you pass in. A full-PPR league with
two flex spots produces a genuinely different board than a half-PPR league
with one, which is why this takes a league rather than assuming one.

This file only calculates what players are WORTH. Deciding who YOU should
take, given who is already on your roster, lives in advice.py.
"""

from collections import defaultdict


# How many players to pull from ESPN. 500 covers everyone who will
# realistically be drafted in a 12-team league (which uses ~168 picks).
POOL_SIZE = 500

# How much to trust each signal, from 0 to 1. These must add up to 1.
# VOR is weighted higher because it is tailored to your league's rules;
# market consensus is a broad average across every league format.
VOR_WEIGHT = 0.75
MARKET_WEIGHT = 0.25


# ---------------------------------------------------------------------------
# Getting the players
# ---------------------------------------------------------------------------

def fetch_players(league, pool_size=POOL_SIZE):
    """
    Pulls the player pool with this league's season projections.

    Before the draft every player is a 'free agent', so this is everybody.
    Note the projections come back already adjusted for the league's
    scoring -- receivers are worth more in the full-PPR league, and ESPN
    handles that for us.
    """
    players = []
    for player in league.free_agents(size=pool_size):
        projection = getattr(player, "projected_total_points", None) or 0.0
        if projection <= 0:
            continue  # no projection means ESPN expects nothing from him

        players.append(
            {
                "player_id": getattr(player, "playerId", None),
                "name": player.name,
                "position": player.position,
                "pro_team": player.proTeam,
                "projection": round(projection, 1),
                "percent_owned": round(getattr(player, "percent_owned", 0.0) or 0.0, 2),
                "injury_status": clean_injury_status(player),
                "bye_week": find_bye_week(player),
                "eligible_slots": list(getattr(player, "eligibleSlots", []) or []),
            }
        )
    return players


def clean_injury_status(player):
    """
    ESPN reports injury status as text for real players but as an empty
    list for team defenses. Without this, every defense looks injured.
    """
    status = getattr(player, "injuryStatus", None)
    return status if isinstance(status, str) and status else "ACTIVE"


def find_bye_week(player):
    """
    Works out a player's bye week by finding the one week ESPN projects
    him for zero points. Returns None if we cannot tell.
    """
    stats = getattr(player, "stats", None) or {}
    for week, detail in stats.items():
        try:
            if not detail.get("projected_points") and 1 <= int(week) <= 18:
                return int(week)
        except (AttributeError, TypeError, ValueError):
            continue
    return None


# ---------------------------------------------------------------------------
# Working out who counts as a "starter" in this league
# ---------------------------------------------------------------------------

def group_by_position(players):
    grouped = defaultdict(list)
    for player in players:
        grouped[player["position"]].append(player)
    return grouped


def count_starters(league, players):
    """
    How many players at each position will be starting somewhere in this
    league on any given week. That number defines 'replacement level' --
    the first guy at the position who is NOT starting anywhere.

    Two parts: the fixed slots, then the flex.
    """
    slots = league.settings.position_slot_counts
    teams = league.settings.team_count

    # Fixed slots: every team starts 1 QB, 2 RB, 2 WR, 1 TE, and so on.
    starters = {
        "QB": slots.get("QB", 0) * teams,
        "RB": slots.get("RB", 0) * teams,
        "WR": slots.get("WR", 0) * teams,
        "TE": slots.get("TE", 0) * teams,
        "K": slots.get("K", 0) * teams,
        "D/ST": slots.get("D/ST", 0) * teams,
    }

    # The flex is trickier. A flex spot can hold a RB, WR, or TE, so we do not
    # know in advance which position fills it. We work it out by looking at who
    # is actually left over: take everyone who did NOT make a fixed slot, and
    # let the highest projected of them claim the flex spots. However many
    # running backs win flex spots, that is how much deeper the RB pool runs.
    flex_slots = slots.get("RB/WR/TE", 0) * teams
    if flex_slots:
        by_position = group_by_position(players)
        leftovers = []
        for position in ("RB", "WR", "TE"):
            ranked = sorted(
                by_position.get(position, []),
                key=lambda pl: pl["projection"],
                reverse=True,
            )
            leftovers.extend(ranked[starters[position]:])

        leftovers.sort(key=lambda pl: pl["projection"], reverse=True)
        for player in leftovers[:flex_slots]:
            starters[player["position"]] += 1

    return starters


def replacement_levels(players, starters):
    """
    Replacement level = what the first NON-starter at each position projects for.

    If 31 running backs will be starting somewhere each week, then the 32nd
    running back is the one you could grab off waivers for nothing. His
    projection is the bar every other running back has to clear.
    """
    levels = {}
    for position, group in group_by_position(players).items():
        ranked = sorted(group, key=lambda pl: pl["projection"], reverse=True)
        cutoff = starters.get(position, 0)

        if cutoff and len(ranked) > cutoff:
            levels[position] = ranked[cutoff]["projection"]
        elif ranked:
            levels[position] = ranked[-1]["projection"]  # thin pool, use the last guy
        else:
            levels[position] = 0.0
    return levels


# ---------------------------------------------------------------------------
# Scoring and blending
# ---------------------------------------------------------------------------

def add_vor(players, levels):
    """VOR = this player's projection minus replacement level at his position."""
    for player in players:
        baseline = levels.get(player["position"], 0.0)
        player["replacement"] = baseline
        player["vor"] = round(player["projection"] - baseline, 1)
    return players


def rank_by(players, key):
    """
    Turns a raw number into a rank (1 = best). Ranking rather than averaging
    the raw numbers keeps one signal from drowning out the other just because
    it happens to use bigger units.
    """
    ordered = sorted(players, key=lambda pl: pl[key], reverse=True)
    return {id(player): place for place, player in enumerate(ordered, start=1)}


def blend(players):
    """Combines the VOR rank and the market rank into one overall rank."""
    vor_ranks = rank_by(players, "vor")
    market_ranks = rank_by(players, "percent_owned")

    for player in players:
        player["vor_rank"] = vor_ranks[id(player)]
        player["market_rank"] = market_ranks[id(player)]
        player["blended_score"] = round(
            VOR_WEIGHT * player["vor_rank"] + MARKET_WEIGHT * player["market_rank"], 2
        )

    players.sort(key=lambda pl: pl["blended_score"])
    for place, player in enumerate(players, start=1):
        player["overall_rank"] = place
    return players


def add_position_ranks_and_tiers(players):
    """
    Position rank (RB1, RB2...) plus tiers.

    A tier is a group of players close enough in value that it does not much
    matter which one you get. The useful moment in a draft is a tier BREAK:
    when the next player down is a real step worse. If four running backs are
    left in your current tier, you can afford to draft a receiver first. If
    one is left, take him now.

    We start a new tier wherever there is an unusually large drop in VOR
    between consecutive players at the same position.
    """
    for position, group in group_by_position(players).items():
        ranked = sorted(group, key=lambda pl: pl["vor"], reverse=True)

        drops = [ranked[i]["vor"] - ranked[i + 1]["vor"] for i in range(len(ranked) - 1)]
        # A "big" drop is one noticeably larger than the typical drop.
        typical_drop = (sum(drops) / len(drops)) if drops else 0
        big_drop = max(typical_drop * 2.0, 8.0)

        tier_number = 1
        for place, player in enumerate(ranked):
            if place > 0 and (ranked[place - 1]["vor"] - player["vor"]) >= big_drop:
                tier_number += 1
            player["position_rank"] = f"{position}{place + 1}"
            player["tier_number"] = tier_number
            player["tier"] = f"{position} T{tier_number}"
    return players


# ---------------------------------------------------------------------------
# The whole pipeline in one call
# ---------------------------------------------------------------------------

def build_board(league, pool_size=POOL_SIZE):
    """
    Runs everything above and hands back the finished, ranked board plus
    the supporting numbers, tailored to this league's rules.
    """
    players = fetch_players(league, pool_size)
    if not players:
        raise RuntimeError(
            "ESPN returned no projected players for this league. "
            "Try again closer to the season."
        )

    starters = count_starters(league, players)
    levels = replacement_levels(players, starters)

    players = add_vor(players, levels)
    players = blend(players)
    players = add_position_ranks_and_tiers(players)

    return {"players": players, "starters": starters, "replacement": levels}
