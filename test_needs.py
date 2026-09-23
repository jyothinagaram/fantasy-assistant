"""
Checks the needs model on made-up rosters where the answer is obvious.

Run with:  .venv/bin/python test_needs.py
"""

import needs
import trades

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE"]
WEEKS = [2, 3, 4]
LIMIT = 8


def make(name, position, avg):
    return {"name": name, "position": position, "season_projected_avg": avg,
            "games_played": 0, "season_actual_avg": None, "bye_week": None,
            "injury_status": "ACTIVE", "current_slot": "BE", "score": None}


def teams():
    # I am deep at WR and leaking points at RB; they are the mirror image.
    mine = [make("My QB", "QB", 18), make("My RB1", "RB", 12), make("My RB2", "RB", 5),
            make("My WR1", "WR", 15), make("My WR2", "WR", 14), make("My WR3", "WR", 13),
            make("My TE", "TE", 8), make("My Bench", "RB", 3)]
    theirs = [make("Their QB", "QB", 18), make("Their RB1", "RB", 14), make("Their RB2", "RB", 13),
              make("Their RB3", "RB", 12), make("Their WR1", "WR", 12), make("Their WR2", "WR", 5),
              make("Their TE", "TE", 8), make("Their Bench", "WR", 3)]
    return mine, theirs


def boards():
    mine, theirs = teams()
    rosters = {1: {"players": mine}, 2: {"players": theirs}}
    bar = needs.starter_bar(rosters, SLOTS)
    return (needs.profile(mine, SLOTS, WEEKS, 2, bar),
            needs.profile(theirs, SLOTS, WEEKS, 2, bar))


def test_a_flex_slot_is_split_between_the_positions_it_accepts():
    starts = needs.starts_per_team(["QB", "RB", "RB", "WR", "RB/WR/TE"])
    assert starts["QB"] == 1
    assert abs(starts["RB"] - (2 + 1 / 3)) < 1e-9
    assert abs(starts["TE"] - 1 / 3) < 1e-9


def test_the_bar_is_an_average_starter_not_an_average_rostered_player():
    mine, theirs = teams()
    rosters = {1: {"players": mine}, 2: {"players": theirs}}
    bar = needs.starter_bar(rosters, SLOTS)
    # Four RBs start across the two teams; the bench 3-pointer must not drag
    # the bar down to the average of everyone rostered.
    rbs = sorted([12, 5, 3, 14, 13, 12], reverse=True)
    assert bar["RB"] >= rbs[3], bar["RB"]


def test_a_hole_the_waiver_wire_can_fill_is_not_worth_trading_for():
    """The quarterback trap: a real hole, but a free fix."""
    mine, theirs = teams()
    rosters = {1: {"players": mine}, 2: {"players": theirs}}
    bar = needs.starter_bar(rosters, SLOTS)
    # Replace my QB with a weak one so the hole is unmistakable.
    weak = [p for p in mine if p["position"] != "QB"] + [make("My Weak QB", "QB", 8)]

    alone = needs.profile(weak, SLOTS, WEEKS, 2, bar)
    assert alone["QB"]["need_per_week"] > 5, alone["QB"]

    # Now put a 17-point quarterback on the waiver wire, and nothing at WR.
    pool = [make("Free QB", "QB", 17), make("Free WR", "WR", 3)]
    priced = needs.profile(weak, SLOTS, WEEKS, 2, bar,
                           replacement=needs.replacement_level(pool, SLOTS))
    # The bar is 18 and the free man 17, so only that 1-point gap is left
    # for a trade to buy -- down from a 10-point hole.
    assert priced["QB"]["need_per_week"] <= 1.0, priced["QB"]
    assert priced["QB"]["raw_need_per_week"] == alone["QB"]["need_per_week"]
    assert priced["QB"]["free_fix_per_week"] > 5, priced["QB"]
    # The receiver hole has no free fix, so it survives untouched and now
    # outranks the quarterback.
    assert priced["WR"]["need_per_week"] == alone["WR"]["need_per_week"]
    assert needs.holes(priced)[0]["position"] != "QB", needs.holes(priced)


def test_replacement_is_the_best_free_agent_not_the_average():
    pool = [make("Scrub", "WR", 2), make("Best free WR", "WR", 11), make("Mid", "WR", 6)]
    best = needs.replacement_level(pool, SLOTS)
    assert best["WR"]["name"] == "Best free WR"
    # An empty pool at a position means a hole there is worth its full value.
    assert best["RB"] is None


def test_the_position_i_am_leaking_points_at_is_the_biggest_need():
    my_profile, their_profile = boards()
    assert needs.holes(my_profile)[0]["position"] == "RB", needs.holes(my_profile)
    assert needs.holes(their_profile)[0]["position"] == "WR", needs.holes(their_profile)


def test_depth_that_never_starts_costs_nothing_to_lose():
    my_profile, _ = boards()
    # My WR3 (13) is better than my starting RB2 (5) but never reaches the
    # lineup, so losing him costs me nothing -- that is what makes him the
    # piece to trade.
    spare = my_profile["WR"]["spares"][0]
    assert spare["player"]["name"] == "My WR3", spare
    assert spare["cost_per_week"] == 0.0, spare


def test_the_costlier_of_two_interchangeable_players_is_not_offered():
    my_profile, _ = boards()
    spares = [s["player"]["name"] for s in needs.spare_players(my_profile)]
    # All three of my receivers are cheap to lose, because the next one
    # slides up. But WR1 costs me 2 pts/week and WR3 costs me nothing for
    # the same return, so WR1 must not be offered.
    assert "My WR3" in spares and "My WR2" in spares, spares
    assert "My WR1" not in spares, spares


def test_a_player_i_cannot_replace_is_not_spare():
    my_profile, _ = boards()
    spares = [s["player"]["name"] for s in needs.spare_players(my_profile)]
    assert "My RB1" not in spares and "My QB" not in spares, spares


def test_kickers_are_priced_as_a_need_but_never_offered_as_a_chip():
    slots = SLOTS + ["K"]
    mine, theirs = teams()
    mine = mine + [make("My K", "K", 9), make("My K2", "K", 8)]
    rosters = {1: {"players": mine}, 2: {"players": theirs + [make("Their K", "K", 9)]}}
    bar = needs.starter_bar(rosters, slots)
    my_profile = needs.profile(mine, slots, WEEKS, 2, bar)
    # The hole is still priced -- it is just one the waiver wire fixes.
    assert "K" in my_profile
    # But the spare kicker is never offered as a trade chip.
    assert "My K2" not in [s["player"]["name"] for s in needs.spare_players(my_profile)]


def test_scrubs_are_never_offered_as_spares():
    my_profile, _ = boards()
    # "My Bench" (3 pts) costs nothing to lose, but nobody trades for him.
    spares = [s["player"]["name"] for s in needs.spare_players(my_profile)]
    assert "My Bench" not in spares, spares


def test_i_chase_after_waivers_but_they_are_judged_on_what_they_see():
    """The two sides of a trade are priced from different chairs."""
    mine, theirs = teams()
    rosters = {1: {"players": mine}, 2: {"players": theirs}}
    bar = needs.starter_bar(rosters, SLOTS)
    # A free 14-point RB would fix most of my RB hole; nothing free at WR.
    pool = [make("Free RB", "RB", 14)]
    spot = needs.replacement_level(pool, SLOTS)
    my_profile = needs.profile(mine, SLOTS, WEEKS, 2, bar, replacement=spot)
    their_profile = needs.profile(theirs, SLOTS, WEEKS, 2, bar, replacement=spot)

    # I stop chasing running backs, because the wire fixes that.
    assert "RB" not in [h["position"] for h in needs.holes(my_profile)]
    # But they are still judged on the hole they can see, so I can still
    # offer into it and the trade still gets built.
    assert "WR" in [h["position"] for h in needs.holes(their_profile, waiver_aware=False)]
    match = needs.overlap(my_profile, their_profile)
    assert [h["position"] for h in match["i_fill"]] == ["WR"], match["i_fill"]


def test_the_two_rosters_cross_in_both_directions():
    my_profile, their_profile = boards()
    match = needs.overlap(my_profile, their_profile)
    assert match["mutual"], match
    assert [h["position"] for h in match["they_fill"]] == ["RB"], match["they_fill"]
    assert [h["position"] for h in match["i_fill"]] == ["WR"], match["i_fill"]
    assert match["fit"] > 0


def test_a_one_sided_pair_is_not_a_match():
    mine, _ = teams()
    # A clone of my own roster: same holes, same depth, nothing to trade.
    twin = [make(f"Twin {p['name']}", p["position"], p["season_projected_avg"]) for p in mine]
    rosters = {1: {"players": mine}, 2: {"players": twin}}
    bar = needs.starter_bar(rosters, SLOTS)
    mine_profile = needs.profile(mine, SLOTS, WEEKS, 2, bar)
    twin_profile = needs.profile(twin, SLOTS, WEEKS, 2, bar)
    # The positions cross -- both are short at RB and both own running backs
    # -- so the cheap targeting filter lets it through. What must hold is
    # that nothing survives valuation: two identical rosters have no trade.
    ideas = trades.ideas_with(mine, twin, LIMIT, SLOTS, WEEKS, 2)
    assert ideas == [], ideas


def test_a_trade_landing_on_their_hole_reads_as_an_easy_yes():
    mine, theirs = teams()
    _, their_profile = boards()
    result = trades.evaluate(mine, theirs, [mine[5]], [theirs[3]], LIMIT, SLOTS, WEEKS, 2)
    seen = needs.perception(result, their_profile)
    assert [f["position"] for f in seen["fills"]] == ["WR"], seen["fills"]
    assert seen["reads"] == "easy yes", seen
    assert "My WR3" in seen["pitch"]


def test_an_offer_that_fills_nothing_and_loses_on_paper_is_a_hard_sell():
    mine, theirs = teams()
    _, their_profile = boards()
    # They give an RB they start and get back my weak RB2: no hole filled
    # for them, and they lose on raw points too.
    result = trades.evaluate(mine, theirs, [mine[2]], [theirs[1]], LIMIT, SLOTS, WEEKS, 2)
    seen = needs.perception(result, their_profile)
    assert seen["fills"] == [], seen["fills"]
    assert seen["reads"] == "hard sell", seen
    assert seen["paper_for_them"] < 0


def test_narrowing_the_search_does_not_change_the_valuation():
    mine, theirs = teams()
    full = trades.ideas_with(mine, theirs, LIMIT, SLOTS, WEEKS, 2)
    narrowed = trades.ideas_with(
        mine, theirs, LIMIT, SLOTS, WEEKS, 2,
        my_pieces=[mine[5]], their_pieces=[theirs[3]],
    )
    assert narrowed, "the WR3-for-RB3 swap should survive the shortlist"
    match = [t for t in full
             if [p["name"] for p in t["give"]] == ["My WR3"]
             and [p["name"] for p in t["get"]] == ["Their RB3"]]
    assert match, "the same swap should be in the unfiltered search"
    assert narrowed[0]["my_gain"] == match[0]["my_gain"]
    assert narrowed[0]["their_gain"] == match[0]["their_gain"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} needs tests passed.")
