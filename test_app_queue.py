"""
Checks the order leagues get worked out in.

Run with:  .venv/bin/python test_app_queue.py
"""

import threading


class FakeState:
    """Just the queue behaviour from app.AppState, with no ESPN behind it."""

    def __init__(self, queue):
        self.lock = threading.Lock()
        self.work = threading.Condition(self.lock)
        self.queue = list(queue)
        self.data = {}

    prioritise = None  # filled in below from the real implementation


import app
FakeState.prioritise = app.AppState.prioritise


def test_the_league_on_screen_jumps_the_queue():
    state = FakeState([101, 102, 103])
    state.prioritise(103)
    # 101 is mid-build and must not be interrupted; 103 goes next.
    assert state.queue == [101, 103, 102], state.queue


def test_the_league_being_built_is_never_moved():
    state = FakeState([101, 102, 103])
    state.prioritise(101)
    assert state.queue == [101, 102, 103], state.queue


def test_one_already_next_is_left_alone():
    state = FakeState([101, 102, 103])
    state.prioritise(102)
    assert state.queue == [101, 102, 103], state.queue


def test_a_league_not_queued_changes_nothing():
    state = FakeState([101, 102])
    state.prioritise(999)
    assert state.queue == [101, 102], state.queue


def test_a_single_entry_queue_is_safe():
    state = FakeState([101])
    state.prioritise(101)
    assert state.queue == [101]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} queue tests passed.")
