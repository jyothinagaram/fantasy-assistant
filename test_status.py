"""
Checks the practice-report reader.

This is the riskiest code in the project. Everywhere else the tool reads
numbers; here it reads English, and English is full of ways to say the
opposite of what a keyword suggests. "Was a full participant" and "will not
be a full participant" share every word that matters.

The stakes are real but bounded: a misread here can move a questionable
player's score by up to 45%, which is enough to start the wrong man. So
these tests are mostly about the sentences that should NOT match.

Run it with:  .venv/bin/python test_status.py
"""

import status


def check(text, expected_level, expected_day=None, label=None):
    level, day = status.read_practice(text)
    assert level == expected_level, (
        f"{label or text!r}\n    got {level!r}, expected {expected_level!r}"
    )
    if expected_day is not None:
        assert day == expected_day, (
            f"{label or text!r}\n    got day {day!r}, expected {expected_day!r}"
        )
    shown = (text or "(nothing at all)")[:66]
    print(f"  ok  {expected_level or 'no report':<10} <- {shown}")


def test_the_plain_cases():
    check("Nabers (knee) was a full participant in Wednesday's practice.",
          "FULL", "Wednesday")
    check("Smith (hamstring) did not practice Thursday.", "DNP", "Thursday")
    check("Jones (ankle) was limited in Friday's practice.", "LIMITED", "Friday")
    check("Brown was a non-participant at Wednesday's session.", "DNP", "Wednesday")
    check("Davis practiced in full Friday.", "FULL", "Friday")
    check("Wilson didn't participate in Thursday's practice.", "DNP", "Thursday")


def test_the_last_day_mentioned_wins():
    """
    Notes are written chronologically, and Friday supersedes Wednesday.
    Friday is also the report the designation is actually based on.
    """
    check(
        "Hall (knee) did not practice Wednesday but was a full participant Friday.",
        "FULL", "Friday",
        label="upgraded over the week",
    )
    check(
        "Moore (groin) practiced in full Wednesday but did not practice Friday.",
        "DNP", "Friday",
        label="downgraded over the week",
    )


def test_negations_must_not_match():
    """
    The sentences that would break it. Each contains the exact keyword for a
    level it must NOT be read as.
    """
    check("Taylor is not expected to be a full participant this week.", None,
          label="'not expected to be a full participant'")
    check("Carter will not practice Wednesday, per the coach.", "DNP",
          label="'will not practice' is genuinely a DNP")
    check("Evans is unlikely to be a full participant before Sunday.", None,
          label="'unlikely to be a full participant'")
    check("The team has not said whether Reed will be limited in practice.", None,
          label="'has not said whether'")
    check("Young isn't a full participant yet.", None,
          label="contracted negation")


def test_no_report_at_all():
    check("Nabers is having a great camp and looks explosive.", None)
    check("", None)
    check(None, None)
    check("The Giants signed a veteran receiver on Tuesday.", None)


def test_body_parts():
    cases = [
        ("Nabers (knee) was a full participant.", "knee"),
        ("Smith (hamstring) is questionable.", "hamstring"),
        ("Jones (ankle/foot) did not practice.", "ankle/foot"),
        ("Brown (per the coach) is fine.", None),
        ("No brackets here at all.", None),
    ]
    for text, expected in cases:
        got = status.read_body_part(text)
        assert got == expected, f"{text!r}: got {got!r}, expected {expected!r}"
        print(f"  ok  body part {str(expected):<12} <- {text[:50]}")


def test_multipliers_are_sane():
    """
    The numbers must never make a hurt player worth more than a healthy one,
    and must actually differentiate the three practice levels.
    """
    full = status.PRACTICE_MULTIPLIERS["FULL"]
    limited = status.PRACTICE_MULTIPLIERS["LIMITED"]
    dnp = status.PRACTICE_MULTIPLIERS["DNP"]

    assert dnp < limited < full, (dnp, limited, full)
    assert full <= 1.25, f"full participation boost {full} is too aggressive"
    assert status.PRACTICE_MULTIPLIERS[None] == 1.0, "no report must be a no-op"
    print(f"  ok  multipliers ordered and bounded  (dnp {dnp}, limited {limited}, full {full})")


def test_countdown_reads_properly():
    import datetime as dt

    now = dt.datetime(2026, 9, 13, 10, 0, tzinfo=dt.timezone.utc)
    cases = [
        (now + dt.timedelta(minutes=45), "in 45m"),
        (now + dt.timedelta(hours=3, minutes=30), "in 3h 30m"),
        (now + dt.timedelta(days=3), "in 3 days"),
        (now - dt.timedelta(minutes=1), "LOCKED"),
        (None, "kickoff unknown"),
    ]
    for kickoff, expected in cases:
        got = status.describe_countdown(kickoff, now)
        assert got == expected, f"got {got!r}, expected {expected!r}"
        print(f"  ok  countdown {expected}")


if __name__ == "__main__":
    print("\nChecking the practice-report reader:\n")
    test_the_plain_cases()
    print()
    test_the_last_day_mentioned_wins()
    print()
    test_negations_must_not_match()
    print()
    test_no_report_at_all()
    print()
    test_body_parts()
    print()
    test_multipliers_are_sane()
    test_countdown_reads_properly()
    print("\nAll checks passed.\n")
