"""
Checks the league-price learning with made-up claim histories.

Run with:  .venv/bin/python test_bids.py
"""

import bids


def claim(player, bid, won=True, team=1, when=1):
    return {"player_id": player, "player": str(player), "team_id": team,
            "bid": bid, "won": won, "week": 1, "processed": when}


def aggressive():
    return [claim(n, b, when=n) for n, b in enumerate([12, 15, 20, 25, 30, 8, 1, 1])]


def cheap():
    return [claim(n, b, when=n) for n, b in enumerate([2, 2, 3, 2, 3, 2])]


def test_too_little_history_changes_nothing():
    market = bids.summarise([claim(1, 1), claim(2, 3)], 100, 1)
    assert not market["trusted"]
    assert bids.adjust(4, 5.0, 100, 1, market) == (4, None)


def test_minimum_bid_claims_do_not_count_as_contested():
    market = bids.summarise(aggressive(), 100, 1)
    assert market["claims"] == 8 and market["contested"] == 6


def test_important_pickup_is_raised_in_an_aggressive_league():
    market = bids.summarise(aggressive(), 100, 1)
    bid, note = bids.adjust(8, 4.0, 100, 1, market)
    assert bid == market["winning_bid_75"] and bid > 8, (bid, market)
    assert "three contested claims in four" in note


def test_raise_never_exceeds_budget_left():
    market = bids.summarise(aggressive(), 100, 1)
    assert bids.adjust(3, 6.0, 10, 1, market)[0] == 10


def test_marginal_pickup_is_capped_in_a_cheap_league():
    market = bids.summarise(cheap(), 100, 1)
    bid, note = bids.adjust(8, 1.5, 100, 1, market)
    assert bid == 2, (bid, market)  # typical $2, x1.25 rounds to 2
    assert "usually go for" in note


def test_rivals_on_the_same_player_are_counted():
    history = [claim(9, 20, when=5), claim(9, 11, won=False, team=2, when=5), claim(9, 4, won=False, team=3, when=5)]
    market = bids.summarise(history, 100, 1)
    assert market["recent"][0]["rivals"] == 2


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} bid tests passed.")
