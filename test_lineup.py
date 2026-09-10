"""
Checks the lineup solver actually finds the best lineup.

This is the one piece of the start/sit tool that can be quietly wrong. A
projection being slightly off is obvious and arguable; a lineup that leaves
half a point on the table looks completely normal and you would never catch
it by reading the output.

So rather than trusting the clever ordering in `best_lineup`, these tests
work out the answer the slow, stupid, obviously-correct way -- try every
legal arrangement and keep the best -- and check the fast one agrees.

Run it with:  .venv/bin/python test_lineup.py
"""

import random

import lineup


def make(name, position, score, status="ACTIVE", bye=False):
    return {
        "name": name,
        "position": position,
        "score": score,
        "can_play": status not in lineup.CANNOT_PLAY and not bye,
        "injury_status": status,
        "on_bye": bye,
    }


def brute_force_best(players, slots):
    """
    Every legal lineup, checked one at a time. Far too slow for real use and
    completely beyond argument, which is exactly what a test wants.

    Walks the slots one at a time, trying every player still available for
    each -- and also trying leaving it empty, so a roster too thin to fill
    every slot is still measured properly rather than coming back as zero.
    """
    playable = [p for p in players if p["can_play"]]

    def walk(slot_index, used):
        if slot_index == len(slots):
            return 0.0
        eligible = lineup.SLOT_ELIGIBILITY[slots[slot_index]]
        best = walk(slot_index + 1, used)  # leave this slot empty
        for position, player in enumerate(playable):
            if position in used or player["position"] not in eligible:
                continue
            filled = player["score"] + walk(slot_index + 1, used | {position})
            best = max(best, filled)
        return best

    return round(walk(0, frozenset()), 2)


def check(label, players, slots):
    _, starters, _ = lineup.best_lineup(players, slots)
    got = lineup.lineup_total(starters)
    want = brute_force_best(players, slots)
    assert got == want, f"{label}: solver got {got}, best possible is {want}"
    assert len(starters) == len(set(id(p) for p in starters)), (
        f"{label}: the same player was started twice"
    )
    print(f"  ok  {label}  ({got} pts)")


def test_flex_should_take_the_deeper_position():
    """
    The case a greedy solver gets wrong.

    Two good running backs fill the RB slots. The third-best running back is
    better than the second receiver -- so the flex should take him, even
    though picking "best remaining player" position-blind would work here
    too. The trap is filling flex FIRST with the best player available and
    stranding a dedicated slot.
    """
    players = [
        make("RB1", "RB", 20.0),
        make("RB2", "RB", 18.0),
        make("RB3", "RB", 14.0),
        make("WR1", "WR", 15.0),
        make("WR2", "WR", 9.0),
        make("TE1", "TE", 8.0),
    ]
    check("flex takes the deeper position", players, ["RB", "RB", "WR", "TE", "RB/WR/TE"])


def test_two_flex_spots():
    """The Boyz are Back runs two flex spots, which multiplies the options."""
    players = [
        make("QB1", "QB", 22.0),
        make("RB1", "RB", 17.0),
        make("RB2", "RB", 13.0),
        make("RB3", "RB", 11.5),
        make("WR1", "WR", 16.0),
        make("WR2", "WR", 12.0),
        make("WR3", "WR", 11.0),
        make("TE1", "TE", 10.0),
        make("TE2", "TE", 6.0),
    ]
    check("two flex spots", players, ["QB", "RB", "RB", "WR", "WR", "TE", "RB/WR/TE", "RB/WR/TE"])


def test_injured_players_are_never_started():
    """A hurt star must not be started, however good his projection is."""
    players = [
        make("Star (out)", "RB", 30.0, status="OUT"),
        make("Star (IR)", "RB", 28.0, status="INJURY_RESERVE"),
        make("Star (bye)", "RB", 26.0, bye=True),
        make("Healthy RB", "RB", 9.0),
        make("Healthy WR", "WR", 8.0),
    ]
    _, starters, _ = lineup.best_lineup(players, ["RB", "WR"])
    names = {p["name"] for p in starters}
    assert names == {"Healthy RB", "Healthy WR"}, names
    check("injured players are never started", players, ["RB", "WR"])


def test_not_enough_players():
    """A thin roster should fill what it can, not crash or invent someone."""
    players = [make("RB1", "RB", 10.0), make("WR1", "WR", 9.0)]
    _, starters, _ = lineup.best_lineup(players, ["QB", "RB", "WR", "TE", "K"])
    assert len(starters) == 2, starters
    print(f"  ok  thin roster fills what it can  ({len(starters)} of 5 slots)")


def test_random_rosters():
    """
    Two hundred random rosters, each checked against brute force.

    Handmade tests only cover the situations I thought of. This covers the
    ones I did not.
    """
    random.seed(20260909)
    slots = ["QB", "RB", "RB", "WR", "WR", "TE", "RB/WR/TE", "RB/WR/TE"]
    for trial in range(200):
        players = []
        for position, count in (("QB", 2), ("RB", 4), ("WR", 5), ("TE", 2)):
            for index in range(count):
                status = random.choice(
                    ["ACTIVE"] * 8 + ["QUESTIONABLE", "OUT", "DOUBTFUL"]
                )
                players.append(
                    make(
                        f"{position}{index}",
                        position,
                        round(random.uniform(0.0, 25.0), 1),
                        status=status,
                        bye=random.random() < 0.08,
                    )
                )
        _, starters, _ = lineup.best_lineup(players, slots)
        got = lineup.lineup_total(starters)
        want = brute_force_best(players, slots)
        assert got == want, f"random roster {trial}: solver {got}, best {want}"
    print("  ok  200 random rosters all matched brute force")


def test_scoring_respects_bye_and_injury():
    """The value step should zero out a bye and an OUT designation."""
    players = [
        {"name": "Bye guy", "position": "RB", "espn_projection": 0.0,
         "weekly_projection": 12.0, "injury_status": "ACTIVE", "bye_week": 5},
        {"name": "Out guy", "position": "WR", "espn_projection": 14.0,
         "weekly_projection": 14.0, "injury_status": "OUT", "bye_week": 9},
        {"name": "Fine guy", "position": "WR", "espn_projection": 10.0,
         "weekly_projection": 14.0, "injury_status": "ACTIVE", "bye_week": 9},
    ]
    lineup.score(players, week=5)
    assert players[0]["score"] == 0.0, players[0]
    assert players[0]["can_play"] is False
    assert players[1]["score"] == 0.0, players[1]
    assert players[1]["can_play"] is False
    # Averaged, not favoured: halfway between 10 and 14.
    assert players[2]["score"] == 12.0, players[2]
    assert players[2]["source_gap"] == 4.0, players[2]
    print("  ok  bye weeks and injuries zero out, projections average")


if __name__ == "__main__":
    print("\nChecking the lineup solver:\n")
    test_flex_should_take_the_deeper_position()
    test_two_flex_spots()
    test_injured_players_are_never_started()
    test_not_enough_players()
    test_scoring_respects_bye_and_injury()
    test_random_rosters()
    print("\nAll checks passed.\n")
