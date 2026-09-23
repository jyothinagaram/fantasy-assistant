"""
Checks the waiver logic gives answers a person would agree with.

No ESPN connection needed -- every roster here is made up, small enough that
the right answer is obvious by eye, so a wrong one stands out.

Run it with:  .venv/bin/python test_waivers.py
"""

import waivers


SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "RB/WR/TE"]
WEEKS = list(range(2, 6))


def make(name, position, avg, bye=None, status="ACTIVE", slot="BE", games=0, actual=None):
    return {
        "name": name,
        "position": position,
        "season_projected_avg": avg,
        "season_actual_avg": actual,
        "games_played": games,
        "bye_week": bye,
        "injury_status": status,
        "current_slot": slot,
        "score": None,
        "percent_owned": 0.0,
    }


def base_roster():
    return [
        make("QB One", "QB", 20, bye=3),
        make("RB One", "RB", 15),
        make("RB Two", "RB", 12),
        make("WR One", "WR", 14),
        make("WR Two", "WR", 11),
        make("TE One", "TE", 8),
        make("Flex Guy", "WR", 9),
        make("Dead Weight", "RB", 2),
    ]


def test_a_real_upgrade_drops_the_worst_player():
    roster = base_roster()
    pickup = make("New WR", "WR", 13)
    swaps = waivers.best_swaps(roster, [pickup], SLOTS, WEEKS, 2)
    assert swaps, "a clear upgrade should be suggested"
    assert swaps[0]["drop"]["name"] == "Dead Weight", swaps[0]["drop"]["name"]
    # Replaces the 9-point flex: +4 a week.
    assert abs(swaps[0]["gain_per_week"] - 4.0) < 0.01, swaps[0]["gain_per_week"]


def test_a_player_who_would_never_start_is_not_suggested():
    roster = base_roster()
    pickup = make("Worse RB", "RB", 1)
    assert waivers.best_swaps(roster, [pickup], SLOTS, WEEKS, 2) == []


def test_bye_week_cover_has_value():
    """A backup QB is worth exactly the week the starter is off."""
    roster = base_roster()
    backup = make("Backup QB", "QB", 16, bye=5)
    swaps = waivers.best_swaps(roster, [backup], SLOTS, WEEKS, 2)
    assert swaps, "covering the week-3 bye should be worth something"
    assert abs(swaps[0]["total_gain"] - 16.0) < 0.01, swaps[0]["total_gain"]
    assert waivers.bye_weeks_covered(backup, roster, WEEKS) == [3]


def test_ir_slot_players_are_never_dropped():
    roster = base_roster()
    roster[-1] = make("Hurt Star", "RB", 0, status="INJURY_RESERVE", slot="IR")
    pickup = make("New WR", "WR", 13)
    swaps = waivers.best_swaps(roster, [pickup], SLOTS, WEEKS, 2)
    assert swaps[0]["drop"]["name"] != "Hurt Star"


def test_open_roster_spot_needs_no_drop():
    roster = base_roster()
    pickup = make("New WR", "WR", 13)
    swaps = waivers.best_swaps(roster, [pickup], SLOTS, WEEKS, 2, roster_full=False)
    assert swaps[0]["drop"] is None


def test_one_big_game_does_not_take_over():
    breakout = make("Hot RB", "RB", 5, games=1, actual=30)
    value = waivers.per_game_value(breakout)
    assert 5 < value < 15, value
    fluky_defense = make("Lucky D", "D/ST", 6, games=1, actual=20)
    assert waivers.per_game_value(fluky_defense) < 8, waivers.per_game_value(fluky_defense)


def test_expert_rest_of_season_blends_with_espn():
    player = make("Blend", "WR", 10)
    player["ros_expert_avg"] = 14.0
    assert abs(waivers.per_game_value(player) - 12.0) < 1e-9
    player["ros_expert_avg"] = None
    assert waivers.per_game_value(player) == 10


def test_games_left_counts_the_bye_only_if_still_to_come():
    import ros_rankings
    assert ros_rankings.games_left(2, 9) == 16
    assert ros_rankings.games_left(10, 9) == 9
    assert ros_rankings.games_left(19, None) == 0


def test_expert_scale_is_removed_but_opinion_kept():
    import ros_rankings
    players = []
    for n in range(6):
        p = make(f"WR{n}", "WR", 10)
        p["ros_expert_avg"] = 11.0            # experts 10% high across the board
        players.append(p)
    players[0]["ros_expert_avg"] = 16.5       # ...but genuinely higher on this one
    scales = ros_rankings.calibrate(players)
    assert abs(scales["WR"] - 1.1) < 1e-9, scales
    assert abs(players[1]["ros_expert_avg"] - 10.0) < 0.01   # scale gone
    assert abs(players[0]["ros_expert_avg"] - 15.0) < 0.01   # opinion kept


def test_bids_are_sane():
    assert waivers.suggest_bid(0.2, 100, 1) == 1, "not worth a claim: minimum bid"
    assert waivers.suggest_bid(6.0, 100, 1) == 25
    assert waivers.suggest_bid(6.0, 100, 1, percent_owned=80) == 38
    assert waivers.suggest_bid(6.0, 10, 1, percent_owned=80) <= 10, "never over budget"
    assert waivers.suggest_bid(6.0, 0, 1) == 0, "no money, no bid"
    assert waivers.suggest_bid(0.6, 100, 0) == 2
    # Bigger gain never means a smaller bid.
    bids = [waivers.suggest_bid(g / 2, 75, 1) for g in range(0, 20)]
    assert bids == sorted(bids), bids


def claim(name, position, gain, drop_name="Spare Man"):
    return {"add": {"name": name, "position": position},
            "drop": {"name": drop_name}, "gain_per_week": gain}


def test_same_slot_alternatives_are_folded_away():
    swaps = [claim(f"QB{n}", "QB", 5 - n) for n in range(6)]
    swaps += [claim("A Back", "RB", 1.0), claim("Another Back", "RB", 0.9),
              claim("Third Back", "RB", 0.8)]
    kept, folded = waivers.rank_claims(swaps)
    assert [c["add"]["name"] for c in kept] == ["QB0", "A Back", "Another Back"], kept
    # One quarterback slot, so five runners-up; two backs shown, one folded.
    assert folded == {"QB": 5, "RB": 1}, folded


def test_a_kicker_never_crowds_the_list():
    swaps = [claim(f"K{n}", "K", 2 - n / 10) for n in range(4)]
    kept, folded = waivers.rank_claims(swaps)
    assert len(kept) == 1 and folded == {"K": 3}, (kept, folded)


def test_folding_counts_what_the_limit_cut_too():
    swaps = [claim("A Back", "RB", 3), claim("A Receiver", "WR", 2), claim("A TE", "TE", 1)]
    kept, folded = waivers.rank_claims(swaps, limit=1)
    assert [c["add"]["name"] for c in kept] == ["A Back"]
    assert folded == {"WR": 1, "TE": 1}, folded


def test_a_drop_spent_twice_is_reported():
    swaps = [claim("A Back", "RB", 3, "Mack Hollins"),
             claim("A Receiver", "WR", 2, "Mack Hollins"),
             claim("A TE", "TE", 1, "Somebody Else")]
    assert waivers.shared_drops(swaps) == {"Mack Hollins": 2}
    assert waivers.shared_drops(swaps[:1]) == {}


if __name__ == "__main__":
    tests = [value for name, value in dict(globals()).items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} waiver tests passed.")
