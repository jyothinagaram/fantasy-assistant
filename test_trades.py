"""
Checks trade valuation with made-up rosters where the answer is obvious.

Run with:  .venv/bin/python test_trades.py
"""

import trades

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE"]
WEEKS = [2, 3, 4]
LIMIT = 8


def make(name, position, avg):
    return {"name": name, "position": position, "season_projected_avg": avg,
            "games_played": 0, "season_actual_avg": None, "bye_week": None,
            "injury_status": "ACTIVE", "current_slot": "BE", "score": None}


def teams():
    # I am deep at WR and weak at RB; they are the opposite.
    mine = [make("My QB", "QB", 18), make("My RB1", "RB", 12), make("My RB2", "RB", 5),
            make("My WR1", "WR", 15), make("My WR2", "WR", 14), make("My WR3", "WR", 13),
            make("My TE", "TE", 8), make("My Bench", "RB", 3)]
    theirs = [make("Their QB", "QB", 18), make("Their RB1", "RB", 14), make("Their RB2", "RB", 13),
              make("Their RB3", "RB", 12), make("Their WR1", "WR", 12), make("Their WR2", "WR", 5),
              make("Their TE", "TE", 8), make("Their Bench", "WR", 3)]
    return mine, theirs


def test_a_trade_that_fills_both_needs_helps_both():
    mine, theirs = teams()
    result = trades.evaluate(mine, theirs, [mine[5]], [theirs[3]], LIMIT, SLOTS, WEEKS, 2)
    # I swap an idle WR3 (13) for an RB (12) who replaces my 5-pt RB2: +7/week.
    assert abs(result["my_gain_per_week"] - 7.0) < 0.01, result["my_gain_per_week"]
    # They swap an idle RB3 for a WR who replaces their 5-pt WR2: +8/week.
    assert abs(result["their_gain_per_week"] - 8.0) < 0.01, result["their_gain_per_week"]


def test_finder_suggests_the_win_win_and_not_the_giveaway():
    mine, theirs = teams()
    ideas = trades.ideas_with(mine, theirs, LIMIT, SLOTS, WEEKS, 2)
    assert ideas, "the obvious WR-for-RB swap should be found"
    for idea in ideas:
        assert idea["my_gain_per_week"] >= trades.WORTH_A_TRADE
        assert idea["their_gain_per_week"] >= trades.WORTH_A_TRADE


def test_two_for_one_forces_a_cut_on_the_receiving_side():
    mine, theirs = teams()
    result = trades.evaluate(mine, theirs, [mine[5], mine[4]], [theirs[1]], LIMIT, SLOTS, WEEKS, 2)
    assert [p["name"] for p in result["they_cut"]] == ["Their Bench"], result["they_cut"]
    assert result["i_cut"] == []


def test_padding_is_removed():
    a, b, c = make("A", "RB", 10), make("B", "WR", 10), make("C", "QB", 15)
    small = {"give": [a], "get": [c], "my_gain": 30.0}
    padded = {"give": [a, b], "get": [c], "my_gain": 30.0}
    assert trades.without_padding([small, padded]) == [small]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} trade tests passed.")
