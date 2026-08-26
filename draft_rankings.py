"""
Builds your draft board.

The problem this solves: ESPN's raw projections are not a draft order. They
say Josh Allen (369 projected points) is worth more than Puka Nacua (295).
But you only start ONE quarterback, and the 12th-best quarterback also scores
a pile of points. Meanwhile the 12th-best receiver does not.

So what actually matters at the draft is not "how many points will this player
score" but "how many MORE points will he score than the guy I could get for
free at the same position later." That number is called value over replacement,
or VOR. A high-VOR player wins you the position; a high-points player might
just be a quarterback.

This script blends two signals into one ranked list:

  1. VOR, calculated from ESPN's projections and YOUR league's exact roster
     rules (12 teams, half-PPR, one flex, etc.)
  2. Market consensus, from how widely each player is rostered across all
     ESPN leagues -- a sanity check against the crowd

Run it with:  .venv/bin/python draft_rankings.py
"""

import csv
import os
import sys
import warnings
from collections import defaultdict

warnings.filterwarnings("ignore")  # hides a harmless OpenSSL notice on macOS

from dotenv import load_dotenv
from espn_api.football import League


# ---------------------------------------------------------------------------
# Settings you might want to change
# ---------------------------------------------------------------------------

# How many players to pull from ESPN. 500 covers every player who will
# realistically be drafted in a 12-team league (which uses ~168 picks).
POOL_SIZE = 500

# How much to trust each signal, from 0 to 1. These must add up to 1.
# VOR is weighted higher because it is tailored to your league's rules;
# market consensus is a broad average across every league format.
VOR_WEIGHT = 0.75
MARKET_WEIGHT = 0.25

# How many players to print to the screen. The CSV always gets everyone.
TOP_N_DISPLAY = 60

# Kickers and defenses are worth almost nothing until the last two rounds,
# and including them clutters the board. They still land in the CSV.
SKIP_POSITIONS_IN_DISPLAY = {"K", "D/ST"}

OUTPUT_DIR = "output"
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "draft_board.csv")


# ---------------------------------------------------------------------------
# Connecting to your league
# ---------------------------------------------------------------------------

def load_league():
    """Reads your .env credentials and connects to your ESPN league."""
    load_dotenv()

    missing = [v for v in ("ESPN_LEAGUE_ID", "ESPN_SEASON") if not os.getenv(v)]
    if missing:
        sys.exit(
            f"Missing required .env values: {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )

    return League(
        league_id=int(os.getenv("ESPN_LEAGUE_ID")),
        year=int(os.getenv("ESPN_SEASON")),
        espn_s2=os.getenv("ESPN_S2") or None,
        swid=os.getenv("ESPN_SWID") or None,
    )


def fetch_players(league):
    """
    Pulls the available player pool with ESPN's season projections.

    Before the draft every player is a 'free agent', so this is everybody.
    After the draft it is only players nobody has rostered.
    """
    players = []
    for p in league.free_agents(size=POOL_SIZE):
        projection = getattr(p, "projected_total_points", None) or 0.0
        if projection <= 0:
            continue  # no projection means ESPN expects nothing from him
        players.append(
            {
                "name": p.name,
                "position": p.position,
                "pro_team": p.proTeam,
                "projection": round(projection, 1),
                "percent_owned": round(getattr(p, "percent_owned", 0.0) or 0.0, 2),
                "injury_status": getattr(p, "injuryStatus", "ACTIVE"),
            }
        )
    return players


# ---------------------------------------------------------------------------
# Working out who counts as a "starter" in your league
# ---------------------------------------------------------------------------

def count_starters(league, players):
    """
    Works out how many players at each position will be starting somewhere
    in your league on any given week. This is the number that defines
    'replacement level' -- the first guy at that position who is NOT starting.

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
    # is actually left: take everyone who did NOT make a fixed slot, and let the
    # highest projected players claim the flex spots. However many running backs
    # win flex spots, that is how much deeper the running back pool runs.
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


def group_by_position(players):
    grouped = defaultdict(list)
    for player in players:
        grouped[player["position"]].append(player)
    return grouped


def replacement_levels(players, starters):
    """
    Replacement level = what the first NON-starter at each position projects for.

    If 30 running backs will be starting somewhere each week, then the 31st
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


def rank_positions(players, key, reverse=True):
    """
    Turns a raw number into a rank (1 = best). Ranking rather than averaging
    the raw numbers keeps one signal from drowning out the other just because
    it happens to use bigger units.
    """
    ordered = sorted(players, key=lambda pl: pl[key], reverse=reverse)
    ranks = {}
    for position, player in enumerate(ordered, start=1):
        ranks[id(player)] = position
    return ranks


def blend(players):
    """Combines the VOR rank and the market rank into one overall rank."""
    vor_ranks = rank_positions(players, "vor")
    market_ranks = rank_positions(players, "percent_owned")

    for player in players:
        player["vor_rank"] = vor_ranks[id(player)]
        player["market_rank"] = market_ranks[id(player)]
        player["blended_score"] = round(
            VOR_WEIGHT * player["vor_rank"] + MARKET_WEIGHT * player["market_rank"], 2
        )

    players.sort(key=lambda pl: pl["blended_score"])
    for position, player in enumerate(players, start=1):
        player["overall_rank"] = position
    return players


def add_position_ranks_and_tiers(players):
    """
    Position rank (RB1, RB2...) plus tiers.

    A tier is a group of players who are close enough in value that it does not
    much matter which one you get. The useful moment in a draft is a tier BREAK:
    when the next player down is a real step worse. If four running backs are
    left in your current tier, you can afford to draft a receiver first. If one
    is left, take him now.

    We start a new tier wherever there is an unusually large drop in VOR
    between consecutive players at the same position.
    """
    for position, group in group_by_position(players).items():
        ranked = sorted(group, key=lambda pl: pl["vor"], reverse=True)

        drops = [
            ranked[i]["vor"] - ranked[i + 1]["vor"] for i in range(len(ranked) - 1)
        ]
        # A "big" drop is one noticeably larger than the typical drop.
        typical_drop = (sum(drops) / len(drops)) if drops else 0
        big_drop = max(typical_drop * 2.0, 8.0)

        tier = 1
        for i, player in enumerate(ranked):
            if i > 0 and (ranked[i - 1]["vor"] - player["vor"]) >= big_drop:
                tier += 1
            player["position_rank"] = f"{position}{i + 1}"
            player["tier"] = f"{position} T{tier}"
    return players


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_board(players, league, starters, levels):
    print(f"\nDRAFT BOARD -- {league.settings.name}")
    print(
        f"{league.settings.team_count} teams | half-PPR | "
        f"pool of {len(players)} projected players"
    )

    print("\nReplacement level (the free player you are measuring against):")
    for position in ("QB", "RB", "WR", "TE"):
        if position in levels:
            print(
                f"  {position:4} starters league-wide: {starters.get(position, 0):3}  "
                f"-> replacement projects {levels[position]:6.1f} pts"
            )

    shown = [p for p in players if p["position"] not in SKIP_POSITIONS_IN_DISPLAY]

    print(f"\nTop {min(TOP_N_DISPLAY, len(shown))} (kickers and defenses omitted):\n")
    header = f"{'#':>3}  {'PLAYER':<24} {'POS':<5} {'TM':<4} {'PROJ':>6} {'VOR':>7}  {'TIER':<8} {'OWN%':>6}"
    print(header)
    print("-" * len(header))

    previous_tier = None
    for player in shown[:TOP_N_DISPLAY]:
        if previous_tier and player["tier"] != previous_tier:
            pass  # tier labels already mark the break
        flag = " *" if player["injury_status"] not in ("ACTIVE", "NORMAL") else ""
        print(
            f"{player['overall_rank']:>3}  {player['name']:<24.24} "
            f"{player['position_rank']:<5} {player['pro_team']:<4} "
            f"{player['projection']:>6.1f} {player['vor']:>7.1f}  "
            f"{player['tier']:<8} {player['percent_owned']:>5.1f}%{flag}"
        )
        previous_tier = player["tier"]

    if any(p["injury_status"] not in ("ACTIVE", "NORMAL") for p in shown[:TOP_N_DISPLAY]):
        print("\n  * = carrying an injury designation, check before drafting")


def write_csv(players):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    columns = [
        "overall_rank",
        "name",
        "position",
        "position_rank",
        "tier",
        "pro_team",
        "projection",
        "replacement",
        "vor",
        "percent_owned",
        "vor_rank",
        "market_rank",
        "blended_score",
        "injury_status",
    ]
    with open(OUTPUT_CSV, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(players)
    print(f"\nFull board ({len(players)} players) saved to: {OUTPUT_CSV}")
    print("Open it in Excel or Numbers to sort and filter during your draft.")


def main():
    print("Connecting to ESPN...")
    league = load_league()

    print(f"Pulling projections for up to {POOL_SIZE} players...")
    players = fetch_players(league)
    if not players:
        sys.exit("ESPN returned no projected players. Try again closer to the season.")

    starters = count_starters(league, players)
    levels = replacement_levels(players, starters)

    players = add_vor(players, levels)
    players = blend(players)
    players = add_position_ranks_and_tiers(players)

    print_board(players, league, starters, levels)
    write_csv(players)


if __name__ == "__main__":
    main()
