"""
Checks playoff weeks and playoff schedules -- no network.

Run with:  .venv/bin/python test_playoffs.py
"""

import types

import playoffs


def league(regular=14, teams=8, length=1):
    return types.SimpleNamespace(settings=types.SimpleNamespace(
        reg_season_count=regular, playoff_team_count=teams, playoff_matchup_period_length=length))


def test_playoff_weeks_follow_league_settings():
    assert playoffs.playoff_weeks(league(14, 8)) == [15, 16, 17]
    assert playoffs.playoff_weeks(league(14, 6)) == [15, 16, 17]   # 6 teams: byes, still 3 rounds
    assert playoffs.playoff_weeks(league(14, 4)) == [15, 16]
    assert playoffs.playoff_weeks(league(13, 4, length=2)) == [14, 15, 16, 17]


SCHEDULE = {"KC": {15: "@DEN", 16: "BYE", 17: "LV"}, "BUF": {15: "MIA", 16: "@NYJ", 17: "NE"}}


def table(games):
    ranks = {"DEN": 2, "LV": 5, "MIA": 1, "NYJ": 4, "NE": 6}
    return {team: {"WR": {"rank": rank, "games": games}} for team, rank in ranks.items()}


def test_bye_in_the_playoffs_is_flagged():
    result = playoffs.outlook("KC", "WR", [15, 16, 17], SCHEDULE, table(6))
    assert result["byes"] == [16]
    assert playoffs.describe(result) == "playoffs (wks 15-17): @DEN, BYE, LV -- BYE in week 16"


def test_rating_waits_for_enough_games():
    early = playoffs.outlook("BUF", "WR", [15, 16, 17], SCHEDULE, table(2))
    late = playoffs.outlook("BUF", "WR", [15, 16, 17], SCHEDULE, table(6))
    assert early["rating"] is None
    assert late["rating"] == "soft"
    assert playoffs.describe(late).endswith("-- soft schedule")


def test_unknown_team_is_harmless():
    result = playoffs.outlook("XYZ", "WR", [15, 16, 17], SCHEDULE, table(6))
    assert result["opponents"] == ["?", "?", "?"] and result["rating"] is None


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} playoff tests passed.")
