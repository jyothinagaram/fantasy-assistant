"""
Checks the nflverse usage reader with tiny made-up files -- no network.

Run with:  .venv/bin/python test_usage.py
"""

import usage

PLAYERS = """gsis_id,pfr_id,espn_id,display_name
00-1,AbcA00,111,Receiver A
00-2,DefD00,222,Receiver D
00-3,GhiG00,,No Espn Id
"""

SNAPS = """game_type,week,player,pfr_player_id,position,team,offense_snaps,offense_pct
REG,1,Receiver A,AbcA00,WR,NE,20,0.30
REG,2,Receiver A,AbcA00,WR,NE,50,0.75
REG,1,Receiver D,DefD00,WR,NE,60,0.90
REG,1,Guard,XyzX00,G,NE,60,1.0
PRE,1,Receiver A,AbcA00,WR,NE,60,1.0
REG,1,No Espn Id,GhiG00,WR,NE,60,0.9
"""

STATS = """player_id,position,season_type,week,team,targets,carries,target_share,air_yards_share,wopr
00-1,WR,REG,1,NE,2,0,0.08,0.05,0.2
00-1,WR,REG,2,NE,9,0,0.30,0.35,0.7
00-2,WR,REG,1,NE,7,0,0.25,0.30,0.6
"""


def data():
    return usage.build(SNAPS, STATS, PLAYERS)


def test_matched_by_espn_id_not_name():
    result = data()
    assert set(result) == {111, 222}, result.keys()


def test_snap_jump_is_a_trend():
    a = data()[111]
    assert a["snap_pct"] == 0.75
    assert abs(a["snap_trend"] - 0.45) < 1e-9, a["snap_trend"]
    assert a["snap_trend"] >= usage.SNAP_JUMP


def test_one_week_has_no_trend():
    assert data()[222]["snap_trend"] is None


def test_preseason_and_linemen_ignored():
    # The preseason row at 100% must not overwrite week 1's 30%.
    a = data()[111]
    assert a["snap_pct_avg"] == (0.30 + 0.75) / 2


def test_shares_average_the_last_two_weeks():
    a = data()[111]
    assert abs(a["target_share"] - 0.19) < 1e-9, a["target_share"]


def test_describe_reads_plainly():
    text = usage.describe(data()[111])
    assert text == "snaps 75% (up 45 pts) · 19% of targets · 20% of air yards", text
    assert usage.describe(None) is None


def test_missing_files_give_nothing_not_an_error():
    assert usage.build(None, None, PLAYERS) == {}


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} usage tests passed.")
