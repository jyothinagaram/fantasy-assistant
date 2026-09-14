"""
Your waiver report: who to pick up, who to drop, and what to bid.

    .venv/bin/python waiver_wire.py            # all your leagues
    .venv/bin/python waiver_wire.py --league "D.C.F."
    .venv/bin/python waiver_wire.py --week 3   # value pickups from week 3 on
    .venv/bin/python waiver_wire.py --top 5    # fewer suggestions

Like everything else here, it cannot change anything on ESPN. You place the
claims yourself in the app.
"""

import argparse
import sys
import warnings

warnings.filterwarnings("ignore")

import leagues
import waivers


def parse_arguments():
    parser = argparse.ArgumentParser(description="Waiver pickups, drops and FAAB bids.")
    parser.add_argument("--week", type=int, help="First week a pickup would play")
    parser.add_argument("--league", help="Only this league (matches part of the name)")
    parser.add_argument("--top", type=int, default=8, help="How many pickups to show")
    parser.add_argument("--fresh", action="store_true", help="Re-download expert rankings")
    parser.add_argument(
        "--espn-only", action="store_true", help="Skip FantasyPros for this week's numbers"
    )
    return parser.parse_args()


def describe_schedule(settings):
    days = ", ".join(settings["process_days"]) or "unknown days"
    hour = settings["process_hour"]
    hour_text = f"hour {hour}" if hour is not None else "unknown hour"
    return f"Claims process {days} at {hour_text} (ESPN's timezone for this is unconfirmed)"


def print_report(report, top):
    settings = report["settings"]
    weeks = report["weeks"]

    print()
    print("=" * 78)
    print(f"  {report['league_name']}  --  WAIVERS  (pickups valued weeks "
          f"{weeks[0]}-{weeks[-1]})" if weeks else f"  {report['league_name']}  --  WAIVERS")
    print(f"  {describe_schedule(settings)}")
    print("=" * 78)

    if not weeks:
        print("  The regular season is over -- nothing left to value pickups against.")
        return

    minimum = settings["minimum_bid"]
    print(f"  Your FAAB left: ${report['budget_left']}   (minimum bid ${minimum})")
    richest = report["opponents"][:3]
    if richest:
        others = ", ".join(f"{o['team']} ${o['budget_left']}" for o in richest)
        print(f"  Most money left elsewhere: {others}")
    if not report["expert_summary"]:
        print("  Expert rankings unavailable -- this week's numbers are ESPN only.")

    worth = [s for s in report["swaps"] if s["gain_per_week"] >= waivers.WORTH_A_CLAIM]
    if not worth:
        print("\n  NOTHING WORTH A CLAIM -- no free agent adds even "
              f"{waivers.WORTH_A_CLAIM} pts a week to your best lineup.")
        near = report["swaps"][:3]
        if near:
            print("  Closest calls:")
            for swap in near:
                print(f"    {swap['add']['name']} ({swap['add']['position']}) "
                      f"+{swap['gain_per_week']:.1f}/wk")
        return

    print(f"\n  RECOMMENDED CLAIMS  (best first)")
    for number, swap in enumerate(worth[:top], start=1):
        add, drop = swap["add"], swap["drop"]
        print(
            f"\n  {number}. ADD  {add['name']} ({add['position']}, {add['pro_team']})"
            f"   bid ${swap['bid']}"
        )
        if drop:
            print(f"     DROP {drop['name']} ({drop['position']}, {drop['pro_team']})")
        else:
            print("     no drop needed -- you have an open roster spot")
        print(
            f"     +{swap['gain_per_week']:.1f} pts/week to your best lineup "
            f"({swap['total_gain']:.0f} over {len(weeks)} weeks)"
        )
        for reason in reasons(swap, report):
            print(f"       - {reason}")

    same_drop = {}
    for swap in worth[:top]:
        if swap["drop"]:
            same_drop.setdefault(swap["drop"]["name"], 0)
            same_drop[swap["drop"]["name"]] += 1
    repeated = [name for name, count in same_drop.items() if count > 1]
    if repeated:
        print(
            f"\n  Note: {', '.join(repeated)} appears as the drop more than once. "
            "Each claim assumes only that one move -- once one goes through, "
            "run this again before relying on the next."
        )
    print()


def reasons(swap, report):
    """Plain-language facts behind a suggestion. Numbers only, no opinions."""
    add = swap["add"]
    notes = []

    this_week = add.get("score")
    notes.append(
        f"this week {this_week:.1f} pts; normal week about "
        f"{waivers.per_game_value(add):.1f}"
    )
    if add.get("games_played"):
        notes.append(
            f"has actually averaged {add['season_actual_avg']:.1f} over "
            f"{add['games_played']} game(s) vs {add['season_projected_avg']:.1f} projected"
        )
    status = add.get("injury_status") or "ACTIVE"
    if status in {"INJURY_RESERVE", "SUSPENSION"}:
        notes.append(
            f"{status.replace('_', ' ').lower()} -- assumed to miss "
            f"{waivers.ASSUMED_WEEKS_MISSED} weeks; ESPN gives no return date"
        )
    elif status not in {"ACTIVE", "NORMAL"}:
        notes.append(f"listed {status.lower()} this week")
    if swap["bye_cover"]:
        weeks = ", ".join(str(w) for w in swap["bye_cover"])
        notes.append(f"covers your bye week(s): {weeks}")
    notes.append(f"owned in {add['percent_owned']:.0f}% of ESPN leagues")

    drop = swap["drop"]
    if drop:
        notes.append(
            f"{drop['name']} is worth about {waivers.per_game_value(drop):.1f} "
            "in a normal week to you"
        )
    return notes


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

    # One league at a time, start to finish -- the ESPN library shares scoring
    # rules between connections, so connecting to the next league early would
    # hand this one the wrong format. See CLAUDE.md.
    for entry in all_leagues:
        if not entry.get("team_id"):
            print(f"\nDo not know which team is yours in {entry['name']} -- skipping.")
            continue
        try:
            league = leagues.connect(entry["league_id"], credentials)
            report = waivers.build(
                league,
                entry["team_id"],
                credentials["season"],
                week=arguments.week,
                use_experts=not arguments.espn_only,
                force_refresh=arguments.fresh,
            )
        except Exception as error:
            print(f"\nCould not build a waiver report for {entry['name']}: {error}")
            continue
        print_report(report, arguments.top)


if __name__ == "__main__":
    main()
