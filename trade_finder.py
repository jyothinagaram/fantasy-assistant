"""
Trade ideas, and a second opinion on any specific trade.

    .venv/bin/python trade_finder.py                      # ideas, all leagues
    .venv/bin/python trade_finder.py --league "D.C.F."
    .venv/bin/python trade_finder.py --league "D.C.F." --give "Makai Lemon" --get "Jaylen Waddle"
    .venv/bin/python trade_finder.py --league Boyz --give "Player A" "Player B" --get "Player C"

--give / --get check one trade from both sides: use it on an offer someone
sent you, or on one you are thinking of sending. Part of a name is enough.

Nothing is sent from here -- ESPN has no write API. You propose trades in
the app.
"""

import argparse
import sys
import warnings

warnings.filterwarnings("ignore")

import leagues
import trades
import waivers


def parse_arguments():
    parser = argparse.ArgumentParser(description="Trade ideas and trade checks.")
    parser.add_argument("--league", help="Only this league (matches part of the name)")
    parser.add_argument("--week", type=int, help="First week the trade would count")
    parser.add_argument("--give", nargs="+", help="Players you would give")
    parser.add_argument("--get", nargs="+", help="Players you would get")
    parser.add_argument("--fresh", action="store_true", help="Re-download expert rankings")
    parser.add_argument("--espn-only", action="store_true", help="Skip FantasyPros")
    return parser.parse_args()


def names(players):
    def one(p):
        status = p.get("injury_status") or "ACTIVE"
        flag = "" if status in {"ACTIVE", "NORMAL"} else f", {status.replace('_', ' ')}"
        return f"{p['name']} ({p['position']}, {waivers.per_game_value(p):.1f}{flag})"
    return " + ".join(one(p) for p in players)


def verdict(per_week):
    if per_week >= 2.0:
        return "clearly better"
    if per_week >= trades.WORTH_A_TRADE:
        return "better"
    if per_week > -trades.WORTH_A_TRADE:
        return "about the same"
    if per_week > -2.0:
        return "worse"
    return "clearly worse"


def print_trade(result, weeks, number=None):
    prefix = f"  {number}. " if number else "  "
    pad = " " * len(prefix)
    print(f"\n{prefix}with {result['partner'].team_name}")
    print(f"{pad}GIVE {names(result['give'])}")
    print(f"{pad}GET  {names(result['get'])}")
    print(
        f"{pad}You:  {result['my_gain_per_week']:+.1f} pts/week "
        f"({result['my_gain']:+.0f} over {len(weeks)} weeks) -- {verdict(result['my_gain_per_week'])}"
    )
    print(
        f"{pad}Them: {result['their_gain_per_week']:+.1f} pts/week -- "
        f"{verdict(result['their_gain_per_week'])} for them"
    )
    give_points, get_points = trades.on_paper(result)
    if get_points > 1.25 * give_points:
        print(f"{pad}On paper you get {get_points:.1f} pts/week of players for {give_points:.1f} -- "
              "they may see it as lopsided; explain why it helps them.")
    elif give_points > 1.25 * get_points:
        print(f"{pad}On paper you give {give_points:.1f} pts/week of players for {get_points:.1f} -- "
              "an easy yes for them; make sure the lineup gain is worth it to you.")
    if result["i_cut"]:
        print(f"{pad}You would need to drop: {', '.join(p['name'] for p in result['i_cut'])}")
    if result["they_cut"]:
        print(f"{pad}They would need to drop: {', '.join(p['name'] for p in result['they_cut'])}")
    if len(result["give"]) > len(result["get"]):
        print(f"{pad}(You also open a roster spot for a free agent -- not counted above.)")
    for player in result["give"] + result["get"]:
        if player.get("playoffs"):
            flag = "  <<" if player.get("playoff_bye") else ""
            print(f"{pad}{player['name']}: {player['playoffs']}{flag}")
    print(f"{pad}(Numbers after each name: what he scores in a normal week.)")


def main():
    arguments = parse_arguments()
    if bool(arguments.give) != bool(arguments.get):
        sys.exit("To check a trade, give both --give and --get.")
    credentials = leagues.load_credentials()

    all_leagues = leagues.available_leagues(credentials)
    if not all_leagues:
        sys.exit("Could not find any ESPN leagues -- check ESPN_S2 and ESPN_SWID in .env.")
    if arguments.league:
        wanted = arguments.league.lower()
        all_leagues = [L for L in all_leagues if wanted in L["name"].lower()]
        if not all_leagues:
            sys.exit(f"No league matching {arguments.league!r}.")
    if arguments.give and len(all_leagues) > 1:
        sys.exit("To check a trade, say which league with --league.")

    # One league at a time, start to finish -- see the scoring-rules quirk in CLAUDE.md.
    for entry in all_leagues:
        if not entry.get("team_id"):
            continue
        try:
            league = leagues.connect(entry["league_id"], credentials)
            board = trades.build(
                league, entry["team_id"], credentials["season"], week=arguments.week,
                use_experts=not arguments.espn_only, force_refresh=arguments.fresh,
            )
        except Exception as error:
            print(f"\nCould not read {entry['name']}: {error}")
            continue

        settings = board["settings"]
        deadline = settings["deadline"] or "none"
        print()
        print("=" * 78)
        print(f"  {board['league_name']}  --  TRADES  (valued weeks {board['weeks'][0]}-{board['weeks'][-1]})")
        print(f"  Trade deadline: {deadline}   Veto votes needed: {settings['veto_votes']}")
        print("=" * 78)

        if arguments.give:
            try:
                result = trades.evaluate_named(board, arguments.give, arguments.get)
            except LookupError as error:
                sys.exit(f"  {error}")
            print_trade(result, board["weeks"])
            print()
            continue

        print("  Looking for trades that improve both lineups", end="", flush=True)
        ideas = trades.find_ideas(board, progress=lambda _: print(".", end="", flush=True))
        print()
        if not ideas:
            print("\n  No trade found that clearly helps both you and the other team.")
        for number, idea in enumerate(ideas, start=1):
            print_trade(idea, board["weeks"], number)
        print()


if __name__ == "__main__":
    main()
