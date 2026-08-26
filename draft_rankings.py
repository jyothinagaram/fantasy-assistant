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


def print_board(players, league, league_info, starters, levels):
    print(f"\nDRAFT BOARD -- {league_info['name']}")
    print(f"{leagues.describe_rules(league)} | pool of {len(players)} projected players")

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
    )
    print(header)
    print("-" * len(header))

    for player in shown[:TOP_N_DISPLAY]:
        flag = " *" if player["injury_status"] not in ("ACTIVE", "NORMAL") else ""
        print(
            f"{player['overall_rank']:>3}  {player['name']:<24.24} "
            f"{player['position_rank']:<5} {player['pro_team']:<4} "
            f"{player['projection']:>6.1f} {player['vor']:>7.1f}  "
            f"{player['tier']:<8} {player['percent_owned']:>5.1f}%{flag}"
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
    ]
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(players)

    print(f"\nFull board ({len(players)} players) saved to: {path}")
    print("Open it in Excel or Numbers to sort and filter during your draft.")


def main():
    creds = leagues.load_credentials()

    print("Finding your leagues...")
    league_info = leagues.choose_league(creds, "Which league do you want a board for?")

    print(f"\nConnecting to {league_info['name']}...")
    league = leagues.connect(league_info["league_id"], creds)

    print("Pulling projections and ranking players...")
    try:
        board = rankings.build_board(league)
    except RuntimeError as error:
        sys.exit(str(error))

    print_board(board["players"], league, league_info, board["starters"], board["replacement"])
    write_csv(board["players"], league_info)


if __name__ == "__main__":
    main()
