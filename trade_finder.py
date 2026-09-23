"""
Trade ideas, and a second opinion on any specific trade.

    .venv/bin/python trade_finder.py                      # ideas, all leagues
    .venv/bin/python trade_finder.py --needs              # who needs what, then matched ideas
    .venv/bin/python trade_finder.py --league "D.C.F."
    .venv/bin/python trade_finder.py --league "D.C.F." --give "Makai Lemon" --get "Jaylen Waddle"
    .venv/bin/python trade_finder.py --league Boyz --give "Player A" "Player B" --get "Player C"

--needs works the question the other way round: it prices what every team in
the league is short of and who they can spare, then builds offers only out of
the pieces both sides can actually part with -- and says how each one will
READ to the other manager, plus the line to send him.

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
import needs
import trades
import waivers


def parse_arguments():
    parser = argparse.ArgumentParser(description="Trade ideas and trade checks.")
    parser.add_argument("--league", help="Only this league (matches part of the name)")
    parser.add_argument("--week", type=int, help="First week the trade would count")
    parser.add_argument("--needs", action="store_true",
                        help="Show what every team needs, then needs-matched ideas")
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
    seen = result.get("perception")
    if seen:
        fills = ", ".join(
            f"{f['player']['name']} at {f['position']} (their hole: {f['need_per_week']:+.1f}/wk)"
            for f in seen["fills"]
        )
        print(f"{pad}Reads to them: {seen['reads'].upper()}"
              + (f" -- fills {fills}" if fills else " -- fills no hole of theirs"))
        print(f"{pad}Say: {seen['pitch']}")
    if result["i_cut"]:
        print(f"{pad}You would need to drop: {', '.join(p['name'] for p in result['i_cut'])}")
    if result["they_cut"]:
        print(f"{pad}They would need to drop: {', '.join(p['name'] for p in result['they_cut'])}")
    if len(result["give"]) > len(result["get"]):
        print(f"{pad}(You also open a roster spot for a free agent -- not counted above.)")
    for player in result["give"] + result["get"]:
        if player.get("situation_note"):
            print(f"{pad}{player['name']}: {player['situation_note']} "
                  "-- those games no longer count toward his average")
    for player in result["give"] + result["get"]:
        if player.get("playoffs"):
            flag = "  <<" if player.get("playoff_bye") else ""
            print(f"{pad}{player['name']}: {player['playoffs']}{flag}")
    print(f"{pad}(Numbers after each name: what he scores in a normal week.)")


def print_needs(board, league_needs):
    """The league's holes and spare parts, mine first, then the best partners."""
    mine = league_needs["profiles"][board["team_id"]]

    print("\n  WHAT I NEED  (points a week my lineup leaks at each spot)")
    my_holes = needs.holes(mine)
    if not my_holes:
        print("    Nothing worth trading for -- every spot is close to a league-average starter.")
    for hole in my_holes:
        free_man = hole.get("replacement")
        fixable = (
            f"   waivers already fix {hole['free_fix_per_week']:.1f} of {hole['raw_need_per_week']:.1f}"
            f" ({free_man['name']} is free)" if free_man and hole["free_fix_per_week"] >= 0.1 else ""
        )
        print(f"    {hole['position']:<5} {hole['need_per_week']:+.1f}/wk"
              f"   (an average {hole['position']} here scores {hole['bar']:.1f}){fixable}")

    print("\n  WHAT I CAN SPARE  (what losing him would actually cost me)")
    my_spares = needs.spare_players(mine)
    if not my_spares:
        print("    Nobody -- every player worth trading is holding a lineup spot.")
    for spare in my_spares:
        print(f"    {spare['player']['name']} ({spare['position']}, "
              f"{waivers.per_game_value(spare['player']):.1f})"
              f"   costs me {spare['cost_per_week']:.1f}/wk to lose")

    print("\n  WHO FITS  (their holes I can fill, and theirs I am short of)")
    for match in needs.partners(board, league_needs):
        if not match["mutual"]:
            continue
        they_fill = ", ".join(
            f"{h['position']} {h['need_per_week']:+.1f}" for h in match["they_fill"]
        )
        i_fill = ", ".join(f"{h['position']} {h['need_per_week']:+.1f}" for h in match["i_fill"])
        print(f"\n    {match['team'].team_name}  (fit {match['fit']:.1f})")
        print(f"      they can fill for me: {they_fill}")
        print(f"      I can fill for them:  {i_fill}")
        for spare in needs.spare_players(league_needs["profiles"][match["team_id"]])[:4]:
            print(f"        they can spare {spare['player']['name']} "
                  f"({spare['position']}, {waivers.per_game_value(spare['player']):.1f}) "
                  f"-- costs them {spare['cost_per_week']:.1f}/wk")


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

        if arguments.needs:
            print("  Pricing what every team is short of", end="", flush=True)
            # The waiver pool, so a hole waivers can fix for free is not
            # priced as one worth trading for. See `needs.py`.
            try:
                pool = waivers.free_agent_pool(
                    league, board["first_week"], waivers.bye_weeks(league), board["slots"]
                )
                waivers.attach_ros(
                    league, credentials["season"], pool, board["first_week"],
                    not arguments.espn_only, arguments.fresh,
                )
            except Exception:
                pool = None
            league_needs = needs.build(
                board, pool, progress=lambda _: print(".", end="", flush=True)
            )
            print()
            print_needs(board, league_needs)
            print("\n  Building offers out of what both sides can spare", end="", flush=True)
            ideas = needs.find_ideas(
                board, league_needs, progress=lambda _: print(".", end="", flush=True)
            )
            print()
        else:
            print("  Looking for trades that improve both lineups", end="", flush=True)
            ideas = trades.find_ideas(board, progress=lambda _: print(".", end="", flush=True))
            print()
        if not ideas and arguments.needs:
            print("\n  No offer that both rosters can spare. Nobody's depth lines up "
                  "with anybody's hole right now.")
        elif not ideas:
            print("\n  No trade found that clearly helps both you and the other team.")
        for number, idea in enumerate(ideas, start=1):
            print_trade(idea, board["weeks"], number)
        print()


if __name__ == "__main__":
    main()
