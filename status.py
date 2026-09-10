"""
How real is that "Questionable", and when does the decision expire?

Two problems this file exists to solve, both of which bite on a Sunday
morning rather than during the week.

THE FIRST: "Questionable" is a weak word doing a lot of different jobs.
Some questionable players are genuinely fifty-fifty. Some are being listed
that way because a coach would rather the other team spent the week
game-planning for two possibilities instead of one. The designation cannot
tell those apart -- but practice participation largely can, and it is
published. A player who practised in full on Friday is a different
proposition from one who did not practise all week, even though ESPN prints
the same word next to both.

So this pulls the RotoWire note ESPN carries for each player and lifts one
structured fact out of it: did he practise, and how much. That is a fact,
so it is allowed to move his score. The rest of the note -- the coach's
quote, the reporter's read on it -- is shown to you and never scored,
which is the same rule the draft board has always followed.

THE SECOND: a lineup decision has an expiry time, and it is not Sunday at
1pm. Each player locks when HIS game kicks off, so a Thursday-night player
is a decision you have to make before most of the week's information
exists. Forgetting that is one of the most expensive routine mistakes in
fantasy, and it is entirely avoidable -- ESPN publishes the schedule. This
works out when each of your players locks, so the tool can tell you what
is about to expire rather than leaving you to remember.
"""

import datetime as dt
import re

import commentary
import outside_rankings


SCOREBOARD_URL = (
    "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl"
    "/scoreboard?week=%s&seasontype=2&dates=%s"
)

# Gameday data goes stale in minutes, not hours -- a player ruled out at
# 11:40 is the whole point of the exercise. This is deliberately far shorter
# than the caches elsewhere in the project.
CACHE_MINUTES = 20

REGULAR_SEASON = 2


# ---------------------------------------------------------------------------
# When does each player lock?
# ---------------------------------------------------------------------------

def kickoffs(season, week):
    """
    When every team plays this week, and whether the game has started.

    One request covers all sixteen games, so this costs the same whether you
    are checking one player or all forty-five across three leagues.

    Returns {team code: {"kickoff": datetime in UTC, "started": bool, ...}}.
    Returns an empty dict rather than raising if ESPN cannot be reached --
    losing the countdown is much better than losing the whole board.
    """
    data = commentary.get_json(SCOREBOARD_URL % (week, season))
    if not data:
        return {}

    out = {}
    for event in data.get("events") or []:
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]

        moment = parse_time(event.get("date"))
        state = ((competition.get("status") or {}).get("type") or {})
        # "pre" means not yet started. Anything else -- in progress, final,
        # postponed -- means the lineup decision is already gone.
        started = (state.get("state") or "").lower() != "pre"

        competitors = competition.get("competitors") or []
        codes = {}
        for competitor in competitors:
            code = ((competitor.get("team") or {}).get("abbreviation") or "").upper()
            if code:
                codes[outside_rankings.normalize_team(code)] = competitor.get("homeAway")

        for code, home_away in codes.items():
            others = [c for c in codes if c != code]
            out[code] = {
                "kickoff": moment,
                "started": started,
                "status": state.get("name"),
                "opponent": others[0] if others else None,
                "at_home": home_away == "home",
            }
    return out


def parse_time(text):
    """ESPN's timestamps, as a timezone-aware datetime. None if unreadable."""
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def describe_countdown(kickoff, now=None):
    """'in 2h 15m', 'in 3 days', 'LOCKED' -- something readable at a glance."""
    if kickoff is None:
        return "kickoff unknown"

    now = now or dt.datetime.now(dt.timezone.utc)
    remaining = kickoff - now

    if remaining.total_seconds() <= 0:
        return "LOCKED"

    hours, seconds = divmod(int(remaining.total_seconds()), 3600)
    minutes = seconds // 60
    if hours >= 48:
        return f"in {hours // 24} days"
    if hours >= 1:
        return f"in {hours}h {minutes:02d}m"
    return f"in {minutes}m"


# ---------------------------------------------------------------------------
# What did the writers actually say?
# ---------------------------------------------------------------------------

# RotoWire writes practice reports to a formula -- "was a full participant in
# Wednesday's practice", "did not practice Thursday", "was limited". That
# regularity is why these can be read as facts rather than interpreted as
# opinion. Anything that does not match one of these patterns is left as
# unknown rather than guessed at.
PRACTICE_PATTERNS = [
    ("FULL", re.compile(
        r"\b(full participant|practic(?:ed|ing) (?:in )?full|fully participat)", re.I)),
    ("DNP", re.compile(
        r"\b(did not (?:practice|participate)|didn'?t (?:practice|participate)|"
        r"(?:will not|won'?t) (?:practice|participate)|"
        r"missed (?:\w+ )?practice|non-?participant|sat out (?:of )?practice)", re.I)),
    ("LIMITED", re.compile(
        r"\b(limited (?:participant|practice|in practice)|was limited|"
        r"limited to a )", re.I)),
]

PRACTICE_DAYS = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)

# The reason this file is the riskiest in the project: "was a full
# participant" and "will not be a full participant" share every word that
# matters. So before believing a positive report, we look at the words just
# before it for a negation.
#
# This only guards FULL and LIMITED. The DNP patterns carry their own
# negation ("did not practice"), and guarding them would cancel every one.
NEGATION = re.compile(
    r"(\bnot\b|n'?t\b|\bunlikely\b|\bdoubtful\b|\bwhether\b|\bif\b|"
    r"\bhop(?:es|ing|ed)\b|\bexpects? to be\b|\bshould be\b|\baiming\b)", re.I)

# How far back to look for that negation. Long enough to catch "is not
# expected to be a full participant", short enough not to trip over a
# negation about something else entirely a sentence earlier.
NEGATION_WINDOW = 35

# How much of a game a player is expected to be worth, relative to the
# TYPICAL questionable player -- not relative to a healthy one.
#
# That distinction is the whole reason these numbers are mild. ESPN's and
# FantasyPros' projections have already discounted a questionable player for
# the average case: some chance he sits, some chance he plays hurt. Applying
# a full injury haircut on top would charge him twice for the same ankle.
# What is NOT already priced in is how he differs from that average, and
# practice participation is the best public evidence of it.
#
# So a full participant is nudged up slightly -- and only slightly, because
# he must not end up worth more than he would be healthy. A player who did
# not practise at all is cut hard, because that is a genuinely different
# situation from the one the projections assumed.
#
# These are directional, not precise. They are deliberately blunt so that
# nobody is tempted to read a decimal place into them.
PRACTICE_MULTIPLIERS = {
    "FULL": 1.10,
    "LIMITED": 1.00,  # this IS the typical questionable player
    "DNP": 0.55,
    None: 1.00,       # no report found -- assume the typical case
}

PRACTICE_LABELS = {
    "FULL": "practised in full",
    "LIMITED": "limited in practice",
    "DNP": "did not practise",
}


def read_practice(text):
    """
    Pulls the practice report out of a note, if there is one.

    Returns (level, day) -- e.g. ("FULL", "Wednesday") -- or (None, None).

    Two rules, both learned from sentences that broke earlier versions:

    THE LAST REPORT WINS. Notes are written chronologically, so a note
    saying "did not practice Wednesday but was a full participant Friday"
    is a story about a man getting healthy, and Friday is the answer.
    Friday is also the practice the designation is actually based on.

    A POSITIVE REPORT MUST NOT BE NEGATED. "Was a full participant" and
    "is not expected to be a full participant" contain the same keyword and
    mean opposite things, so the words just before a positive match are
    checked for a negation first.

    When in doubt this returns nothing rather than guessing. That is the
    safe direction: no report means no adjustment at all, so an unreadable
    sentence costs us the extra insight and never costs a lineup.
    """
    if not text:
        return None, None

    # Where the "did not practice" phrases are. Their own negations must not
    # be counted against a LATER positive report -- in "did not practice
    # Wednesday but was a full participant Friday", that "not" belongs to
    # Wednesday and says nothing about Friday.
    dnp_spans = [
        match.span()
        for level, pattern in PRACTICE_PATTERNS
        if level == "DNP"
        for match in pattern.finditer(text)
    ]

    best_level, best_position = None, -1
    for level, pattern in PRACTICE_PATTERNS:
        for match in pattern.finditer(text):
            if level in ("FULL", "LIMITED") and is_negated(text, match.start(), dnp_spans):
                continue  # something like "will not be a full participant"
            if match.start() > best_position:
                best_level, best_position = level, match.start()

    if best_level is None:
        return None, None

    return best_level, day_for(text, best_position)


def is_negated(text, position, dnp_spans):
    """
    Whether a positive practice report is cancelled by the words before it.

    Any negation that is part of a "did not practice" phrase is ignored --
    that negation is about an earlier day, not about this report.
    """
    window_start = max(0, position - NEGATION_WINDOW)
    for match in NEGATION.finditer(text, window_start, position):
        inside_a_dnp = any(
            start <= match.start() < end for start, end in dnp_spans
        )
        if not inside_a_dnp:
            return True
    return False


def day_for(text, position):
    """
    Which day the report at `position` is talking about.

    Prefers the first day named AFTER the phrase, because that is how these
    notes are written -- "did not practice Friday", "a full participant in
    Wednesday's practice". Only if there is no day afterwards does it fall
    back to the nearest one before, which stops a note that mentions two
    days from confidently reporting the wrong one.
    """
    after = [m for m in PRACTICE_DAYS.finditer(text) if m.start() >= position]
    if after:
        return after[0].group(1).capitalize()

    before = [m for m in PRACTICE_DAYS.finditer(text) if m.start() < position]
    if before:
        return before[-1].group(1).capitalize()

    return None


BODY_PART = re.compile(r"\(([a-z][a-z /'-]{2,20})\)")

# Words that show up in brackets but are not injuries.
NOT_INJURIES = {"per", "via", "who", "and", "or", "the", "his", "no", "not"}


def read_body_part(text):
    """The bit in brackets -- 'Nabers (knee)' -- if it looks like an injury."""
    if not text:
        return None
    for match in BODY_PART.finditer(text):
        candidate = match.group(1).strip().lower()
        if candidate and candidate.split()[0] not in NOT_INJURIES:
            return candidate
    return None


def player_report(espn_id):
    """
    The latest RotoWire note for one player, with the facts pulled out.

    The note itself is kept whole so it can be shown to you verbatim. Only
    the practice level and the body part are treated as facts.
    """
    overview = commentary.get_json(commentary.OVERVIEW_URL % espn_id)
    if not overview:
        return {}

    note = overview.get("rotowire") or {}
    headline = commentary.clean(note.get("headline"))
    story = commentary.clean(note.get("story"))
    combined = f"{headline} {story}".strip()

    level, day = read_practice(combined)

    return {
        "note_headline": headline or None,
        "note_story": story or None,
        "note_published": note.get("published"),
        "practice": level,
        "practice_day": day,
        "body_part": read_body_part(combined),
    }


# ---------------------------------------------------------------------------
# Putting it on the board
# ---------------------------------------------------------------------------

def attach(players, season, week, only_uncertain=True, progress=None):
    """
    Adds kickoff timing to every player and a practice report to the ones
    whose status is actually in doubt.

    By default the notes are only fetched for players who are questionable,
    doubtful or hurt. Reading a note for a healthy player costs a request and
    tells you nothing -- and on a Sunday morning, when this matters most,
    speed is the feature.

    Never raises. Losing this layer should cost you the extra context, not
    the lineup.
    """
    schedule = kickoffs(season, week)
    now = dt.datetime.now(dt.timezone.utc)

    for player in players:
        game = schedule.get(outside_rankings.normalize_team(player.get("pro_team")))
        kickoff = game["kickoff"] if game else None
        player["kickoff"] = kickoff
        player["locked"] = bool(game and (game["started"] or (
            kickoff is not None and kickoff <= now)))
        player["locks_in"] = describe_countdown(kickoff, now)
        player["game_status"] = game["status"] if game else None

    uncertain = [p for p in players if needs_a_note(p)] if only_uncertain else list(players)

    if progress and uncertain:
        progress(f"Checking {len(uncertain)} uncertain player(s)...")

    for player in uncertain:
        if not player.get("player_id"):
            continue
        try:
            player.update(player_report(player["player_id"]))
        except Exception:
            continue

    for player in players:
        level = player.get("practice")
        player["practice_multiplier"] = (
            PRACTICE_MULTIPLIERS.get(level, 1.0)
            if player.get("injury_status") == "QUESTIONABLE"
            else 1.0
        )

    return players


# Designations where a note is worth reading. OUT and INJURY_RESERVE are
# included because the note often says how long he is gone for, which is a
# waiver question even though it is no longer a lineup one.
WORTH_A_NOTE = {"QUESTIONABLE", "DOUBTFUL", "OUT", "INJURY_RESERVE", "SUSPENSION"}


def needs_a_note(player):
    return (player.get("injury_status") or "ACTIVE") in WORTH_A_NOTE


def describe_practice(player):
    """'did not practise (Friday, knee)' -- or None if there is no report."""
    level = player.get("practice")
    if not level:
        return None

    text = PRACTICE_LABELS.get(level, level.lower())
    details = [d for d in (player.get("practice_day"), player.get("body_part")) if d]
    return f"{text} ({', '.join(details)})" if details else text
