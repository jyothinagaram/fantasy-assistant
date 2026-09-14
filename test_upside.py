"""
Checks the under-the-radar finder rewards real evidence and nothing else.

Made-up players, no ESPN connection. Run with:  .venv/bin/python test_upside.py
"""

import upside


def make(name, position="WR", team="NE", games=1, targets=0, carries=0,
         status="ACTIVE", projected=5.0, actual=None, change=0.0):
    return {
        "name": name, "position": position, "team": team, "games_played": games,
        "targets": targets, "carries": carries, "injury_status": status,
        "projected_avg": projected, "actual_avg": actual, "owned_change": change,
    }


def run(player, pool, totals=None):
    injured = upside.openings(pool)
    shares = upside.target_shares(pool)
    return upside.score_player(player, injured, shares, totals or {})


def test_fresh_injury_opens_a_role_for_the_next_man():
    star = make("Star", games=1, targets=10, status="INJURY_RESERVE", projected=14)
    wr2 = make("Number Two", targets=7)
    pool = [star, wr2, make("Filler", targets=13)]
    score, reasons = run(wr2, pool)
    assert any(r.startswith("OPENING") and "newly" in r for r in reasons), reasons
    assert score >= 3.0, score


def test_an_old_injury_is_not_news():
    long_gone = make("Long Gone", games=0, targets=0, status="INJURY_RESERVE", projected=14)
    someone_else_hurt = make("Other", team="BUF", games=1, targets=5, status="OUT", projected=8)
    wr2 = make("Number Two", targets=7)
    pool = [long_gone, someone_else_hurt, wr2, make("Filler", targets=13)]
    fresh_score, _ = run(wr2, [make("Star", games=1, targets=10, status="OUT", projected=14),
                               wr2, make("Filler", targets=13)])
    old_score, reasons = run(wr2, pool)
    assert old_score < fresh_score, (old_score, fresh_score)
    assert any("already out" in r for r in reasons), reasons


def test_unused_player_gets_little_from_an_opening():
    star = make("Star", games=1, targets=10, status="OUT", projected=14)
    unused = make("Practice Squad", targets=1)
    pool = [star, unused, make("WR2", targets=8), make("TE", position="TE", targets=6)]
    score, reasons = run(unused, pool)
    assert score < upside.MINIMUM_UPSIDE, score
    assert any("barely been used" in r for r in reasons), reasons


def test_the_injured_player_himself_scores_nothing():
    hurt = make("Hurt", targets=10, status="OUT", projected=14, change=20)
    assert run(hurt, [hurt, make("Other", targets=5)])[0] == 0.0


def test_matchup_alone_never_qualifies():
    player = make("Nobody", targets=0, games=0)
    totals = {"NE": {"implied_points": 31, "opponent": "NYJ"}}
    score, reasons = run(player, [player], totals)
    substance = any(r.startswith(("OPENING", "ROLE", "TRENDING")) for r in reasons)
    assert not substance and score <= 1.0, (score, reasons)


def test_crowd_and_bad_matchup():
    player = make("Hot Add", targets=2, change=18)
    totals = {"NE": {"implied_points": 17, "opponent": "BAL"}}
    score, reasons = run(player, [player, make("Other", targets=20)], totals)
    assert score == 1.0, (score, reasons)  # +2 trending, -1 tough matchup


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} upside tests passed.")
