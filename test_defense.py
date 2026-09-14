"""
Checks the defence-vs-position table with made-up weekly stats -- no network.

Run with:  .venv/bin/python test_defense.py
"""

import defense

HEADER = "player_id,position,season_type,week,team,opponent_team,fantasy_points,fantasy_points_ppr\n"


def stats(rows):
    return HEADER + "\n".join(rows) + "\n"


def sample():
    rows = []
    # Week 1: PIT gives up a lot to receivers, BUF very little.
    rows += [f"w{n},WR,REG,1,NE,PIT,15,20" for n in range(3)]      # 60 PPR to NE WRs
    rows += [f"x{n},WR,REG,1,DET,BUF,2,4" for n in range(2)]       # 8 PPR
    rows += ["y,WR,REG,1,KC,DAL,10,14"]                            # 14 PPR
    rows += ["p,WR,PRE,1,NE,PIT,50,60"]                            # preseason: ignored
    rows += ["r,RB,REG,1,NE,PIT,10,12"]
    rows += ["s,WR,REG,2,NE,PIT,40,50"]                            # the week being previewed
    return stats(rows)


def test_points_are_credited_to_the_defence_and_ranked():
    table = defense.build(sample(), "PPR", before_week=2)
    assert table["PIT"]["WR"]["allowed_per_game"] == 60.0
    assert table["PIT"]["WR"]["rank"] == 1
    assert table["BUF"]["WR"]["rank"] == 3


def test_the_previewed_week_is_left_out():
    assert defense.build(sample(), "PPR", before_week=2)["PIT"]["WR"]["games"] == 1
    assert defense.build(sample(), "PPR")["PIT"]["WR"]["games"] == 2


def test_scoring_format_changes_the_numbers():
    half = defense.build(sample(), "HALF", before_week=2)["PIT"]["WR"]["allowed_per_game"]
    std = defense.build(sample(), "STD", before_week=2)["PIT"]["WR"]["allowed_per_game"]
    assert half == 52.5 and std == 45.0, (half, std)


def test_one_game_is_pulled_toward_average():
    entry = defense.build(sample(), "PPR", before_week=2)["PIT"]["WR"]
    assert entry["adjusted"] < entry["allowed_per_game"]


def test_describe_and_quality():
    table = defense.build(sample(), "PPR", before_week=2)
    text = defense.describe("PIT", "WR", table)
    assert text == "vs PIT: allows 60.0 pts/game to WRs, 1st most (1 game)", text
    assert defense.matchup_quality("PIT", "WR", table) is None, "one game is too few to label"
    two_games = defense.build(sample(), "PPR")
    assert defense.matchup_quality("PIT", "WR", two_games) == "soft"
    assert defense.describe("NYJ", "WR", table) is None


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} defense tests passed.")
