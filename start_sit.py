"""
Your weekly start/sit board.

Run it and it tells you, for every league you are in, who to start this
week, who to bench, what to change, and why.

    .venv/bin/python start_sit.py            # all your leagues
    .venv/bin/python start_sit.py --week 3   # a week other than the current one
    .venv/bin/python start_sit.py --league "D.C.F."
    .venv/bin/python start_sit.py --fresh    # ignore cached expert rankings

Nothing here changes anything on ESPN. It cannot -- ESPN has no write API.
Every change it recommends you make yourself in the app, which is also a
good thing: you get to disagree with it.
"""

import argparse
import sys
import warnings

warnings.filterwarnings("ignore")

import leagues
import lineup


# How big a scoring difference has to be before it is worth telling you to
# change anything. Both projections are estimates with real error bars, and a
# tenth of a point is noise, not information -- acting on it just churns your
# lineup and makes the tool feel unreliable.
MEANINGFUL_POINTS = 0.5


def parse_arguments():
    parser = argparse.ArgumentParser(description="Weekly start/sit recommendations.")
    parser.add_argument("--week", type=int, help="Which week (default: the current one)")
    parser.add_argument("--league", help="Only this league (matches part of the name)")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Re-download expert rankings instead of using the cache",
    )
    parser.add_argument(
        "--espn-only",
        action="store_true",
        help="Skip FantasyPros and use ESPN's projections alone",
    )
    return parser.parse_args()


def format_player(player, show_slot=None):
    """One player as a single readable line."""
    slot = f"{show_slot:<9}" if show_slot else ""
    flag = ""
    status = player.get("injury_status")
    if player.get("on_bye"):
        flag = "BYE"
    elif status in lineup.CANNOT_PLAY:
        flag = status.replace("_", " ")
    elif status == "QUESTIONABLE":
        flag = "QUESTIONABLE"

    espn = player.get("espn_projection")
    expert = player.get("weekly_projection")
    expert_text = f"{expert:5.1f}" if expert is not None else "    -"
    opponent = player.get("opponent") or ""

    return (
        f"  {slot}{player['name']:<22} {player['position']:<4} "
        f"{opponent:<8} {player['score']:>6.1f}  "
        f"(ESPN {espn:>5.1f} | experts {expert_text})  {flag}"
    )


def print_board(board, rules):
    print()
    print("=" * 78)
    print(f"  {board['league_name']}  --  Week {board['week']}")
    print(f"  {rules}")
    print("=" * 78)

    summary = board["expert_summary"]
    if summary:
        print(
            f"  Expert rankings: {board['scoring']} format, matched "
            f"{summary['matched']} of {summary['total']} players."
        )
    else:
        print("  Expert rankings unavailable -- using ESPN projections only.")

    # -- the recommended lineup ------------------------------------------
    print("\n  RECOMMENDED LINEUP")
    for slot in sorted(board["assigned"], key=lambda s: len(lineup.SLOT_ELIGIBILITY[s])):
        for player in board["assigned"][slot]:
            print(format_player(player, show_slot=slot))

    empty = len(board["slots"]) - len(board["starters"])
    if empty:
        print(f"\n  !! {empty} slot(s) could not be filled -- not enough healthy players.")

    # -- what to change ---------------------------------------------------
    gain = round(board["recommended_total"] - board["current_total"], 2)
    print(
        f"\n  Projected: {board['recommended_total']:.1f} pts "
        f"(your current lineup: {board['current_total']:.1f})"
    )

    if not board["changes"]:
        print("\n  NO CHANGES NEEDED -- your lineup is already the best one.")
    elif gain < MEANINGFUL_POINTS:
        print(
            f"\n  NO CHANGES WORTH MAKING -- the best alternative is only "
            f"{gain:.1f} pts better, which is inside the margin of error."
        )
    else:
        print(f"\n  CHANGES TO MAKE  (+{gain:.1f} pts)")
        for out_player, in_player in board["changes"]:
            print(f"    BENCH  {out_player['name']} ({out_player['score']:.1f})")
            print(f"    START  {in_player['name']} ({in_player['score']:.1f})")
            for reason in lineup.reasons(in_player):
                print(f"           - {reason}")
            for reason in lineup.reasons(out_player):
                print(f"           - {out_player['name']}: {reason}")
            print()

    # -- things to keep an eye on -----------------------------------------
    watch = []
    for player in board["starters"]:
        notes = [
            note
            for note in lineup.reasons(player)
            if "confirm before kickoff" in note
            or "experts split" in note
            or "moved him down" in note
            or "ESPN higher than experts" in note
        ]
        if notes:
            watch.append((player, notes))

    if watch:
        print("  WATCH THESE STARTERS")
        for player, notes in watch:
            print(f"    {player['name']} ({player['position']})")
            for note in notes:
                print(f"      - {note}")
        print()

    # -- bench ------------------------------------------------------------
    print("  BENCH")
    for player in sorted(board["bench"], key=lambda p: p["score"], reverse=True):
        print(format_player(player))


def main():
    arguments = parse_arguments()
    credentials = leagues.load_credentials()

    all_leagues = leagues.available_leagues(credentials)
    if not all_leagues:
        sys.exit(
            "Could not find any ESPN leagues for your account. Check that "
            "ESPN_S2 and ESPN_SWID in your .env are current -- they expire."
        )

    if arguments.league:
        wanted = arguments.league.lower()
        all_leagues = [L for L in all_leagues if wanted in L["name"].lower()]
        if not all_leagues:
            sys.exit(f"No league matching {arguments.league!r}.")

    for entry in all_leagues:
        try:
            league = leagues.connect(entry["league_id"], credentials)
        except Exception as error:
            print(f"\nCould not connect to {entry['name']}: {error}")
            continue

        # Read the rules immediately after connecting. The ESPN library keeps
        # scoring settings in one shared place, so connecting to the next
        # league would otherwise overwrite this league's answer.
        rules = leagues.describe_rules(league)

        week = arguments.week or league.current_week
        team_id = entry.get("team_id")
        if not team_id:
            print(f"\nDo not know which team is yours in {entry['name']} -- skipping.")
            continue

        try:
            board = lineup.build(
                league,
                team_id,
                week,
                credentials["season"],
                use_experts=not arguments.espn_only,
                force_refresh=arguments.fresh,
            )
        except Exception as error:
            print(f"\nCould not build a board for {entry['name']}: {error}")
            continue

        print_board(board, rules)

    print()


if __name__ == "__main__":
    main()
