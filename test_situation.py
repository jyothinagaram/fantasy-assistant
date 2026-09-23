"""
Checks the stale-games model on made-up play-by-play.

Run with:  .venv/bin/python test_situation.py
"""

import situation
import waivers

# nflverse id -> ESPN id, the mapping the real file gets from nflverse.
PLAYERS_CSV = (
    "gsis_id,pfr_id,espn_id\n"
    "00-STARTER,,101\n"
    "00-BACKUP,,102\n"
    "00-OTHERQB,,103\n"
)


def pbp(rows):
    out = ["season_type,posteam,week,passer_player_id,passer_player_name"]
    out += [f"REG,{team},{week},{gsis},{name}" for team, week, gsis, name in rows]
    return "\n".join(out) + "\n"


def player(name, position, team, espn_id=None, avg=None, games=0, projected=12.0,
           injury="ACTIVE"):
    return {"name": name, "position": position, "pro_team": team, "player_id": espn_id,
            "season_projected_avg": projected, "season_actual_avg": avg,
            "games_played": games, "injury_status": injury, "bye_week": None,
            "current_slot": "BE", "score": None}


def test_short_name_is_only_ever_for_display():
    assert situation.short_name("Michael Penix Jr.") == "M.Penix"
    assert situation.short_name("Cooper Rush") == "C.Rush"


def test_the_busiest_passer_owns_the_game():
    rows = [("ATL", 1, "00-STARTER", "M.Penix")] * 3 + [("ATL", 1, "00-BACKUP", "C.Rush")] * 9
    _, __ = None, None
    by_gsis = {"00-STARTER": 101, "00-BACKUP": 102}
    passers = situation.passers_by_week(pbp(rows), by_gsis)
    assert passers[("ATL", 1)][0] == 102, passers


def test_games_thrown_by_someone_else_stop_counting():
    """The Drake London case, in miniature."""
    starter = player("Michael Penix Jr.", "QB", "ATL", 101, projected=14.4)
    catcher = player("Drake London", "WR", "ATL", 201, avg=7.2, games=2, projected=15.4)
    rows = [("ATL", 1, "00-BACKUP", "C.Rush"), ("ATL", 2, "00-BACKUP", "C.Rush")]

    before = waivers.per_game_value(catcher)
    situation.attach([starter, catcher], 2026, waivers.per_game_value,
                     pbp_text=pbp(rows), players_text=PLAYERS_CSV)
    assert catcher["stale_games"] == 2, catcher
    assert "C.Rush" in catcher["situation_note"] and "Penix" in catcher["situation_note"]
    # Every game he has played describes a different offence, so he falls
    # back to his projection -- and rises, because the stale games were bad.
    after = waivers.per_game_value(catcher)
    assert after > before, (before, after)
    assert abs(after - 15.4) < 0.01, after


def test_it_cuts_both_ways():
    """A stale average that FLATTERS a player is discounted just the same."""
    starter = player("Sam Darnold", "QB", "SEA", 101, projected=16.0)
    catcher = player("Hot Start", "WR", "SEA", 202, avg=34.0, games=2, projected=20.0)
    rows = [("SEA", 1, "00-BACKUP", "D.Lock"), ("SEA", 2, "00-BACKUP", "D.Lock")]
    before = waivers.per_game_value(catcher)
    situation.attach([starter, catcher], 2026, waivers.per_game_value,
                     pbp_text=pbp(rows), players_text=PLAYERS_CSV)
    assert waivers.per_game_value(catcher) < before


def test_nothing_changes_when_the_starter_is_the_one_throwing():
    starter = player("Michael Penix Jr.", "QB", "ATL", 101, projected=14.4)
    catcher = player("Drake London", "WR", "ATL", 201, avg=7.2, games=2, projected=15.4)
    rows = [("ATL", 1, "00-STARTER", "M.Penix"), ("ATL", 2, "00-STARTER", "M.Penix")]
    before = waivers.per_game_value(catcher)
    situation.attach([starter, catcher], 2026, waivers.per_game_value,
                     pbp_text=pbp(rows), players_text=PLAYERS_CSV)
    assert catcher["stale_games"] == 0
    assert waivers.per_game_value(catcher) == before


def test_an_injured_quarterback_is_never_the_benchmark():
    """He cannot be who they start, so his absence is not a change."""
    hurt = player("Michael Penix Jr.", "QB", "ATL", 101, projected=14.4, injury="OUT")
    catcher = player("Drake London", "WR", "ATL", 201, avg=7.2, games=2, projected=15.4)
    rows = [("ATL", 1, "00-BACKUP", "C.Rush"), ("ATL", 2, "00-BACKUP", "C.Rush")]
    situation.attach([hurt, catcher], 2026, waivers.per_game_value,
                     pbp_text=pbp(rows), players_text=PLAYERS_CSV)
    assert catcher["stale_games"] == 0, catcher


def test_a_third_stringer_is_not_treated_as_the_plan():
    """Guard against a team whose real starter nobody rosters."""
    scrub = player("Practice Squad Guy", "QB", "ATL", 103, projected=3.0)
    catcher = player("Drake London", "WR", "ATL", 201, avg=7.2, games=2, projected=15.4)
    rows = [("ATL", 1, "00-BACKUP", "C.Rush"), ("ATL", 2, "00-BACKUP", "C.Rush")]
    situation.attach([scrub, catcher], 2026, waivers.per_game_value,
                     pbp_text=pbp(rows), players_text=PLAYERS_CSV)
    assert catcher["stale_games"] == 0, catcher


def test_the_waiver_pool_counts_toward_who_should_be_starting():
    """The bug that made the first version do nothing: an unrostered starter."""
    free_starter = player("Michael Penix Jr.", "QB", "ATL", 101, projected=14.4)
    catcher = player("Drake London", "WR", "ATL", 201, avg=7.2, games=2, projected=15.4)
    rows = [("ATL", 1, "00-BACKUP", "C.Rush"), ("ATL", 2, "00-BACKUP", "C.Rush")]

    situation.attach([catcher], 2026, waivers.per_game_value,
                     pbp_text=pbp(rows), players_text=PLAYERS_CSV)
    assert catcher["stale_games"] == 0, "with no quarterback in sight, nothing to compare"

    situation.attach([catcher], 2026, waivers.per_game_value, pbp_text=pbp(rows),
                     players_text=PLAYERS_CSV, also=[free_starter])
    assert catcher["stale_games"] == 2, catcher


def test_running_backs_are_left_alone():
    """His carries arrive whoever is under centre."""
    starter = player("Michael Penix Jr.", "QB", "ATL", 101, projected=14.4)
    back = player("Bijan Robinson", "RB", "ATL", 203, avg=21.0, games=2, projected=20.0)
    rows = [("ATL", 1, "00-BACKUP", "C.Rush"), ("ATL", 2, "00-BACKUP", "C.Rush")]
    before = waivers.per_game_value(back)
    situation.attach([starter, back], 2026, waivers.per_game_value,
                     pbp_text=pbp(rows), players_text=PLAYERS_CSV)
    assert back["stale_games"] == 0, back
    assert waivers.per_game_value(back) == before


def test_a_missing_play_by_play_changes_nothing():
    starter = player("Michael Penix Jr.", "QB", "ATL", 101, projected=14.4)
    catcher = player("Drake London", "WR", "ATL", 201, avg=7.2, games=2, projected=15.4)
    before = waivers.per_game_value(catcher)
    assert situation.attach([starter, catcher], 2026, waivers.per_game_value,
                            pbp_text="", players_text=PLAYERS_CSV) is None
    assert waivers.per_game_value(catcher) == before


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} situation tests passed.")
