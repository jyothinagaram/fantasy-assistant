"""
Prints a draft board for one of your leagues, and saves the full list to a
spreadsheet you can open during the draft.

This is the static version -- a cheat sheet you read top to bottom. For the
live version that tracks who is gone and reacts to your roster as you draft,
use draft_assistant.py instead.

Run it with:  .venv/bin/python draft_rankings.py

The actual ranking maths lives in rankings.py, so this file and the live
assistant always agree with each other.
"""

import csv
import os
import sys

import leagues
import rankings


# How many players to print to the screen. The CSV always gets everyone.
TOP_N_DISPLAY = 60

# Kickers and defenses are worth almost nothing until the last two rounds,
# and including them clutters the board. They still land in the CSV.
SKIP_POSITIONS_IN_DISPLAY = {"K", "D/ST"}

OUTPUT_DIR = "output"


def safe_filename(name):
    """Turns a league name into something safe to use as a file name."""
    keep = [c if c.isalnum() or c in " -_" else "" for c in name]
    return "".join(keep).strip().replace(" ", "_").lower() or "league"


def print_board(players, league, league_info, starters, levels, experts):
    print(f"\nDRAFT BOARD -- {league_info['name']}")
    print(f"{leagues.describe_rules(league)} | pool of {len(players)} projected players")

    if experts["used"]:
        print(
            f"Blended with FantasyPros expert consensus "
            f"({experts['scoring']} list, {experts['matched']} of {len(players)} players matched)"
        )
    else:
        print("ESPN projections only -- could not reach FantasyPros for expert rankings")

    print("\nReplacement level (the free player you are measuring against):")
    for position in ("QB", "RB", "WR", "TE"):
        if position in levels:
            print(
                f"  {position:4} starters league-wide: {starters.get(position, 0):3}  "
                f"-> replacement projects {levels[position]:6.1f} pts"
            )

    shown = [p for p in players if p["position"] not in SKIP_POSITIONS_IN_DISPLAY]

    print(f"\nTop {min(TOP_N_DISPLAY, len(shown))} (kickers and defenses omitted):\n")
    header = (
        f"{'#':>3}  {'PLAYER':<24} {'POS':<5} {'TM':<4} "
        f"{'PROJ':>6} {'VOR':>7}  {'TIER':<8} {'OWN%':>6}"
        f"{'  ECR':>6} {'RANGE':>10}"
    )
    print(header)
    print("-" * len(header))

    for player in shown[:TOP_N_DISPLAY]:
        flag = " *" if player["injury_status"] not in ("ACTIVE", "NORMAL") else ""

        # ECR is where the experts have him; the range beside it is the best
        # and worst rank any single analyst gave him. A wide range is a
        # warning that nobody really knows.
        if player.get("expert_ranked"):
            ecr = f"{player['ecr']:.0f}"
            spread = (
                f"{player['ecr_best']:.0f}-{player['ecr_worst']:.0f}"
                if player.get("ecr_best") and player.get("ecr_worst")
                else "-"
            )
        else:
            ecr, spread = "-", "-"

        print(
            f"{player['overall_rank']:>3}  {player['name']:<24.24} "
            f"{player['position_rank']:<5} {player['pro_team']:<4} "
            f"{player['projection']:>6.1f} {player['vor']:>7.1f}  "
            f"{player['tier']:<8} {player['percent_owned']:>5.1f}%"
            f"{ecr:>6} {spread:>10}{flag}"
        )

    if any(p["injury_status"] not in ("ACTIVE", "NORMAL") for p in shown[:TOP_N_DISPLAY]):
        print("\n  * = carrying an injury designation, check before drafting")


def write_csv(players, league_info):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"draft_board_{safe_filename(league_info['name'])}.csv")

    columns = [
        "overall_rank", "name", "position", "position_rank", "tier", "pro_team",
        "projection", "replacement", "vor", "percent_owned", "bye_week",
        "vor_rank", "market_rank", "blended_score", "injury_status",
        # From FantasyPros: where the experts have him, how far apart they
        # are, and how that compares with ESPN's own numbers.
        "ecr", "ecr_pos_rank", "ecr_best", "ecr_worst", "ecr_spread",
        "expert_rank", "expert_gap", "expert_ranked",
        # Where the three sources disagree -- sort on this column to pull all
        # the bargains, or all the traps, to the top.
        "signal", "signal_why",
    ]
    rows = []
    for player in players:
        row = dict(player)
        found = player.get("signals") or []
        row["signal"] = " + ".join(s["label"] for s in found)
        row["signal_why"] = " ".join(s["why"] for s in found)
        rows.append(row)

    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nFull board ({len(players)} players) saved to: {path}")
    print("Open it in Excel or Numbers to sort and filter during your draft.")


def main():
    creds = leagues.load_credentials()

    print("Finding your leagues...")
    league_info = leagues.choose_league(creds, "Which league do you want a board for?")

    print(f"\nConnecting to {league_info['name']}...")
    league = leagues.connect(league_info["league_id"], creds)

    print("Pulling projections and expert rankings, and ranking players...")
    try:
        board = rankings.build_board(league)
    except RuntimeError as error:
        sys.exit(str(error))

    print_board(
        board["players"], league, league_info,
        board["starters"], board["replacement"], board["experts"],
    )
    write_csv(board["players"], league_info)


if __name__ == "__main__":
    main()
