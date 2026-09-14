"""
Your team check-up: how you are doing, where you are weak, what to do first.

    .venv/bin/python team_report.py                 # all your leagues
    .venv/bin/python team_report.py --league "D.C.F."

Start here each week. It tells you which KIND of move matters most -- a
lineup change, a waiver claim or a trade -- and for your weakest positions
shows the options of every kind side by side. Then use start_sit.py,
waiver_wire.py or trade_finder.py for the full detail on whichever you pick.

It takes a minute or two per league: it runs all three of those tools.
"""

import argparse
import sys
import warnings

warnings.filterwarnings("ignore")

import coach
import leagues


def parse_arguments():
    parser = argparse.ArgumentParser(description="Team check-up and where to focus.")
    parser.add_argument("--league", help="Only this league (matches part of the name)")
    parser.add_argument("--fresh", action="store_true", help="Re-download expert rankings")
    parser.add_argument("--espn-only", action="store_true", help="Skip FantasyPros")
    return parser.parse_args()


def ordinal(n):
    if n is None:
        return "?"
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def print_results(season):
    print("\n  HOW YOU'RE DOING")
    weeks = season["weeks"]
    if not weeks:
        print("    No games played yet.")
        return

    latest = weeks[-1]
    outcome = (
        "in progress" if not latest["final"]
        else "WON" if latest["score"] > latest["opponent_score"]
        else "LOST" if latest["score"] < latest["opponent_score"] else "TIED"
    )
    print(
        f"    Week {latest['week']} ({outcome}): {latest['score']:.1f} vs "
        f"{latest['opponent']} {latest['opponent_score']:.1f}"
        f"   (you were projected {latest['projected']:.1f})"
    )
    print(
        f"    Your score ranked {ordinal(latest['league_rank'])} of "
        f"{latest['team_count']} teams that week."
    )
    if not latest["final"]:
        print("    Bench review: available once the week is final (some players have not played yet).")
    elif latest["left_on_bench"] >= 0.5:
        print(
            f"    Left on your bench: {latest['left_on_bench']:.1f} pts "
            f"(best possible lineup: {latest['best_possible']:.1f})"
        )
        if latest["should_have_started"]:
            print(
                f"      should have started {', '.join(latest['should_have_started'])} "
                f"over {', '.join(latest['should_have_benched'])}"
            )
    else:
        print("    You started the best possible lineup.")
    if not latest["final"]:
        print("    (Games still to play -- these numbers will change.)")

    record = f"{season['wins']}-{season['losses']}" + (f"-{season['ties']}" if season["ties"] else "")
    print(
        f"\n    Season: {record} in finished weeks, {season['points_for']:.1f} pts scored, "
        f"{season['left_on_bench']:.1f} left on the bench"
    )
    chance = season["playoff_chance"]
    chance_text = f", ESPN gives you a {chance:.0f}% playoff chance" if chance is not None else ""
    print(
        f"    Standing: {ordinal(season['standing'])} of {season['team_count']} "
        f"({season['playoff_spots']} make the playoffs){chance_text}"
    )


def print_gaps(gaps):
    print("\n  YOUR LINEUP vs THE LEAGUE  (starters' points in a normal week)")
    print(f"    {'':6} {'you':>6} {'league':>7} {'':>7}  rank")
    for row in sorted(gaps, key=lambda r: r["difference"]):
        marker = "  << gap" if row["difference"] <= -coach.GAP_POINTS else (
            "  strength" if row["difference"] >= coach.GAP_POINTS else "")
        print(
            f"    {row['group']:<6} {row['mine']:>6.1f} {row['median']:>7.1f} "
            f"{row['difference']:>+7.1f}  {ordinal(row['rank'])}/{row['team_count']}{marker}"
        )


def print_moves(moves):
    print("\n  WHERE TO FOCUS  (best move of each kind, biggest first)")
    if not moves:
        print("    Nothing clearly worth doing this week -- your team is in good shape.")
        return
    for number, move in enumerate(moves, start=1):
        gain = f"+{move['gain']:.1f} pts/wk" if move["gain"] is not None else "upside"
        print(f"    {number}. {move['kind']:<7} {gain:>13}  ({move['when']})")
        print(f"       {move['summary']}")


def print_fixes(fixes):
    if not fixes:
        return
    print("\n  OPTIONS FOR YOUR GAPS")
    for fix in fixes:
        gap = fix["gap"]
        print(
            f"\n    {gap['group']} -- {gap['difference']:+.1f} vs league, "
            f"{ordinal(gap['rank'])} of {gap['team_count']}  (now: {', '.join(gap['starters']) or 'nobody'})"
        )
        any_option = False
        for swap in fix["waivers"]:
            any_option = True
            drop = f", drop {swap['drop']['name']}" if swap["drop"] else ""
            print(f"      WAIVER  add {swap['add']['name']}{drop}, bid ${swap['bid']}  "
                  f"(+{swap['gain_per_week']:.1f}/wk)")
        for gem in fix["gems"]:
            any_option = True
            print(f"      STASH   {gem['name']} ({gem['team']}) -- upside {gem['upside']:.1f}")
        for trade in fix["trades"]:
            any_option = True
            print(
                f"      TRADE   give {' + '.join(p['name'] for p in trade['give'])}, get "
                f"{' + '.join(p['name'] for p in trade['get'])} with {trade['partner'].team_name}"
                f"  (+{trade['my_gain_per_week']:.1f}/wk you, +{trade['their_gain_per_week']:.1f} them)"
            )
        if not any_option:
            print("      No waiver or trade option found yet -- worth watching week to week.")


def main():
    arguments = parse_arguments()
    credentials = leagues.load_credentials()
    all_leagues = leagues.available_leagues(credentials)
    if not all_leagues:
        sys.exit("Could not find any ESPN leagues -- check ESPN_S2 and ESPN_SWID in .env.")
    if arguments.league:
        wanted = arguments.league.lower()
        all_leagues = [L for L in all_leagues if wanted in L["name"].lower()]
        if not all_leagues:
            sys.exit(f"No league matching {arguments.league!r}.")

    # One league at a time, start to finish -- see the scoring-rules quirk in CLAUDE.md.
    for entry in all_leagues:
        if not entry.get("team_id"):
            continue
        print(f"\nChecking {entry['name']}", end="", flush=True)
        try:
            league = leagues.connect(entry["league_id"], credentials)
            report = coach.build(
                league, entry["team_id"], credentials["season"],
                use_experts=not arguments.espn_only, force_refresh=arguments.fresh,
                progress=lambda _: print(".", end="", flush=True),
            )
        except Exception as error:
            print(f"\nCould not build a check-up for {entry['name']}: {error}")
            continue

        print()
        print("=" * 78)
        print(f"  {report['league_name']}  --  TEAM CHECK-UP  (planning for week {report['first_week']})")
        print("=" * 78)
        print_results(report["season"])
        print_gaps(report["gaps"])
        print_moves(report["moves"])
        print_fixes(report["fixes"])
        print()


if __name__ == "__main__":
    main()
