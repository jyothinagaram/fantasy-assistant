"""
Checks consistency profiles and the head-to-head logic with made-up players.

Run with:  .venv/bin/python test_matchup.py
"""

import consistency
import matchup


def player(name, position, score, floor=None, ceiling=None, swing=0.5):
    profile = None if floor is None else {"floor": floor, "ceiling": ceiling, "swing": swing,
                                          "games": 17, "average": score, "label": "normal"}
    return {"name": name, "position": position, "score": score, "can_play": True,
            "consistency": profile}


def test_profile_needs_enough_games():
    assert consistency.profile_from([10, 12, 11]) is None


def test_steady_and_boom_labels():
    steady = consistency.profile_from([10, 11, 12, 10, 11, 12, 11])
    boom = consistency.profile_from([2, 25, 3, 28, 1, 30, 4])
    assert steady["label"] == "steady", steady
    assert boom["label"] == "boom-or-bust", boom
    assert boom["ceiling"] > steady["ceiling"] and boom["floor"] < steady["floor"]


def test_win_probability_is_sensible():
    even = [player("a", "WR", 100, 50, 150)]
    assert abs(matchup.win_probability(even, [player("b", "WR", 100, 50, 150)]) - 0.5) < 1e-9
    # Real lineups: nine starters a side, so individual swings partly cancel.
    team = lambda each: [player(f"p{n}", "WR", each) for n in range(9)]
    assert matchup.win_probability(team(14.5), team(11.1)) > 0.65    # ~130 vs ~100
    assert matchup.win_probability(team(7.8), team(11.1)) < 0.35     # ~70 vs ~100


def test_label_matches_the_rounded_number():
    assert matchup.situation(0.36) == "underdog"     # shown as 35%
    assert matchup.situation(0.38) == "toss-up"      # shown as 40%


def lineup_with_close_call():
    starter = player("Steady Starter", "WR", 12.0, floor=9, ceiling=15)
    boomer = player("Boom Bench", "WR", 11.0, floor=3, ceiling=24)
    safe = player("Safe Bench", "WR", 11.2, floor=12, ceiling=14)
    return {"WR": [starter]}, [boomer, safe]


def test_underdog_leans_to_the_ceiling():
    assigned, bench = lineup_with_close_call()
    tips = matchup.tiebreaks(assigned, bench, 0.2)
    assert [t["start"]["name"] for t in tips] == ["Boom Bench"], tips


def test_favourite_leans_to_the_floor():
    assigned, bench = lineup_with_close_call()
    tips = matchup.tiebreaks(assigned, bench, 0.85)
    assert [t["start"]["name"] for t in tips] == ["Safe Bench"], tips


def test_toss_up_and_big_gaps_change_nothing():
    assigned, bench = lineup_with_close_call()
    assert matchup.tiebreaks(assigned, bench, 0.5) == []
    far = [player("Far Behind", "WR", 5.0, floor=1, ceiling=30)]
    assert matchup.tiebreaks(assigned, far, 0.1) == []


def test_wrong_position_is_never_suggested():
    assigned, _ = lineup_with_close_call()
    rb = [player("Boom RB", "RB", 11.5, floor=2, ceiling=30)]
    assert matchup.tiebreaks(assigned, rb, 0.1) == []


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} matchup tests passed.")
