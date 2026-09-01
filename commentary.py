"""
What the writers are saying about each player.

The rankings tell you what a player is projected to do. They cannot tell you
that a backfield is about to be split two ways, that a receiver landed in an
offence that suits him, or that the guy coming off a hamstring was doing
side-field work on Monday. Beat reporters know that, and they write it down.

The approach here is deliberately unambitious: DO NOT make the tool work
things out that a writer has already stated plainly. Somebody has already
published "how do you expect the backfield touches to be split between Chuba
Hubbard and Jonathon Brooks?" -- that sentence is worth more than anything
this tool could infer from a depth chart, and it comes with a byline.

So the job is collection, not analysis:

  1. Ask ESPN which articles each player is tagged in.
  2. Fetch each article once -- one article covers hundreds of players, so
     this is far cheaper than looking players up one at a time.
  3. Pull out the sentences that name the player, and show them to you
     with the headline they came from.

Alongside that we keep a small number of FACTS -- rookie or not, what round
he went in, whether he changed teams. Those come back as structured data, so
they are either true or they are not, and they are allowed a small say in
the recommendation.

The written sentences are never scored. "He is not the sleeper everyone
thinks" and "he is a sleeper" are nearly the same sentence, and no amount of
cleverness makes a program tell them apart reliably. You read it in a second.
That split -- facts vote, prose does not -- is the whole design.

Everything is best-effort. If ESPN's feeds are unreachable the board still
gets built, just quieter.
"""

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests


OVERVIEW_URL = (
    "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl"
    "/athletes/%s/overview"
)
SEASON_URL = (
    "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    "/seasons/%s/athletes/%s"
)
ARTICLE_URL = "https://content.core.api.espn.com/v1/sports/news/%s"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

CACHE_DIR = "cache"

# Written notes go stale fast during camp. The facts underneath -- draft
# round, team changes -- do not move all season. Articles sit in between.
NOTES_CACHE_HOURS = 8
ARTICLE_CACHE_HOURS = 24
FACTS_CACHE_HOURS = 24 * 7

WORKERS = 6

# Most articles we will read in one go. Well above what a normal run needs;
# it exists so a strange day cannot turn into a thousand requests.
MAX_ARTICLES = 90

# Which articles are worth reading at all. This decides WHICH pieces we open,
# never what they mean.
ARTICLE_WORDS = (
    "fantasy", "sleeper", "breakout", "bust", "draft", "undervalued",
    "overvalued", "depth chart", "position battle", "camp", "target",
    "backfield", "committee", "starting job", "waiver", "value",
)

# Pieces that are about someone's private life, or are pure betting content.
ARTICLE_NOISE = (
    "proposal", "engaged", "wedding", "arrested", "charged", "lawsuit",
    "betting", "odds", "parlay", "prop bet",
)

# A quote has to be long enough to say something.
MIN_QUOTE_CHARS = 45
MAX_QUOTE_CHARS = 320
QUOTES_PER_PLAYER = 4

NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def cache_path(name):
    return os.path.join(CACHE_DIR, name)


def read_cache(name, max_age_hours):
    path = cache_path(name)
    try:
        if (time.time() - os.path.getmtime(path)) / 3600 > max_age_hours:
            return None
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_cache(name, payload):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path(name), "w") as handle:
            json.dump(payload, handle)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Talking to ESPN
# ---------------------------------------------------------------------------

_team_names = {}
_team_lock = threading.Lock()


def get_json(url, timeout=20):
    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


def team_abbreviation(ref_url):
    """Turns ESPN's internal team link into something like 'PHI'."""
    if not ref_url:
        return None
    with _team_lock:
        if ref_url in _team_names:
            return _team_names[ref_url]
    data = get_json(ref_url)
    abbreviation = (data or {}).get("abbreviation")
    with _team_lock:
        _team_names[ref_url] = abbreviation
    return abbreviation


def clean(text):
    text = re.sub(r"<(script|style).*?</\1>", " ", str(text or ""), flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


# ---------------------------------------------------------------------------
# The facts -- checkable, and allowed a small say
# ---------------------------------------------------------------------------

def player_facts(espn_id, season):
    """When he came into the league, what round, and whether he moved."""
    now = get_json(SEASON_URL % (season, espn_id))
    if not now:
        return {}

    draft = now.get("draft") or {}
    facts = {
        "draft_year": draft.get("year"),
        "draft_round": draft.get("round"),
        "experience": (now.get("experience") or {}).get("years"),
        "age": now.get("age"),
        "team_now": team_abbreviation((now.get("team") or {}).get("$ref")),
        "team_before": None,
        "changed_teams": False,
    }

    previous = get_json(SEASON_URL % (season - 1, espn_id))
    if previous:
        facts["team_before"] = team_abbreviation((previous.get("team") or {}).get("$ref"))
    if facts["team_now"] and facts["team_before"]:
        facts["changed_teams"] = facts["team_now"] != facts["team_before"]

    return facts


# ---------------------------------------------------------------------------
# Step 1 -- the note on the player, and which articles mention him
# ---------------------------------------------------------------------------

def worth_reading(headline, summary, section):
    text = ("%s %s" % (headline, summary)).lower()
    if any(word in text for word in ARTICLE_NOISE):
        return False
    if (section or "").lower() == "fantasy":
        return True
    return any(word in text for word in ARTICLE_WORDS)


def player_notes(espn_id):
    """The latest note on a player, plus the articles he is tagged in."""
    data = get_json(OVERVIEW_URL % espn_id)
    if not data:
        return {}

    rotowire = data.get("rotowire") or {}
    articles = []
    for item in (data.get("news") or []):
        headline = clean(item.get("headline"))
        summary = clean(item.get("description"))
        if not item.get("id") or not headline:
            continue
        if not worth_reading(headline, summary, item.get("section")):
            continue
        articles.append({
            "id": item["id"],
            "headline": headline,
            "url": ((item.get("links") or {}).get("web") or {}).get("href", ""),
        })
        if len(articles) >= 4:
            break

    return {
        "note": clean(rotowire.get("headline")),
        "note_detail": clean(rotowire.get("story"))[:700],
        "note_date": clean(rotowire.get("published")),
        "articles": articles,
    }


# ---------------------------------------------------------------------------
# Step 2 -- read each article once, keep the body
# ---------------------------------------------------------------------------

def longest_story(node, found=None):
    """ESPN nests an article's body in different places by article type."""
    if found is None:
        found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("story", "body") and isinstance(value, str) and len(value) > 400:
                found.append(value)
            longest_story(value, found)
    elif isinstance(node, list):
        for item in node:
            longest_story(item, found)
    return found


def fetch_article(article_id):
    data = get_json(ARTICLE_URL % article_id)
    if not data:
        return None
    bodies = longest_story(data)
    if not bodies:
        return None

    headline = ""
    byline = ""
    for candidate in (data.get("headlines") or []):
        headline = clean(candidate.get("headline")) or headline
        byline = clean(candidate.get("byline")) or byline
        if headline:
            break

    return {
        "headline": headline,
        "byline": byline,
        "body": clean(max(bodies, key=len))[:40000],
    }


# ---------------------------------------------------------------------------
# Step 3 -- pull out the sentences that name each player
# ---------------------------------------------------------------------------

def surname(full_name):
    parts = [p for p in full_name.split() if p]
    if not parts:
        return ""
    if len(parts) > 1 and parts[-1].lower() in NAME_SUFFIXES:
        return parts[-2]
    return parts[-1]


def spellings(name):
    """
    One name, written the way writers actually write it.

    Suffixes are the problem: the board says "Marvin Harrison Jr." but an
    article may drop the full stop, so we accept both.
    """
    return re.escape(name.rstrip(".")) + (r"\.?" if name.endswith(".") else "")


def build_name_patterns(players):
    """
    How to spot each player in prose.

    Full name always works. A bare surname is only safe when it points at
    exactly one player and nothing else. Two ways it can betray us:

      1. Someone else on the board shares it -- there are three Browns here,
         and quoting a sentence about the wrong one is worse than quoting
         nothing.
      2. It is somebody else's *first* name. "Chase" is Ja'Marr Chase's
         surname, but it is also how every sentence about Chase Brown
         starts -- so a bare "Chase" pulled Chase Brown's write-up onto
         Ja'Marr Chase's card. Same trap for Harrison, Hunter, Jackson,
         James, Mason and Tyson.

    When a surname fails either test we simply require the full name. The
    cost is a few missed sentences; the alternative is confidently showing
    you the wrong player's outlook while you are on the clock.
    """
    surnames = {}
    given_names = set()
    for player in players:
        last = surname(player["name"])
        surnames.setdefault(last.lower(), []).append(player)
        for part in player["name"].split():
            if part != last:
                given_names.add(part.lower())

    patterns = {}
    for player in players:
        names = [spellings(player["name"])]
        last = surname(player["name"])
        unique = len(surnames.get(last.lower(), [])) == 1
        if last and unique and len(last) > 3 and last.lower() not in given_names:
            names.append(spellings(last))
        # Lookarounds rather than \b: a name ending in a full stop ("Marvin
        # Harrison Jr.") can never satisfy a trailing \b, because the next
        # character is a space rather than a letter. That silently hid every
        # sentence about him.
        patterns[player["player_id"]] = re.compile(
            r"(?<!\w)(?:%s)(?!\w)" % "|".join(names), re.IGNORECASE
        )
    return patterns


# Full stops that do not end a sentence. Without these, "the No. 1 pick"
# becomes a quote that stops dead at "the No." -- which reads as if the tool
# is broken, and loses the half of the sentence that mattered.
ABBREVIATIONS = re.compile(
    r"\b(No|Nos|Jr|Sr|St|Dr|Mr|Mrs|Ms|vs|Rd|Ave|Ft|Mt|Sq|approx|Est|Gen|Rep|Sen)\.\s",
    re.IGNORECASE,
)
DOT = "․"  # a lookalike we swap in, then swap back out


def split_sentences(text):
    """Splits prose into sentences without tripping over abbreviations."""
    safe = ABBREVIATIONS.sub(lambda m: m.group(0).replace(".", DOT), text)
    safe = re.sub(r"(\d)\.(\d)", r"\1%s\2" % DOT, safe)          # 4.7 yards
    safe = re.sub(r"\b([A-Z])\.\s*([A-Z])\.", r"\1%s \2%s" % (DOT, DOT), safe)  # A.J.

    parts = re.split(r"(?<=[.!?])\s+(?=[\"'“(]?[A-Z])", safe)
    return [p.replace(DOT, ".").strip() for p in parts if p.strip()]


def quotes_from_articles(players, articles_by_id, notes_by_player):
    """
    For each player, the sentences that actually mention him, tagged with
    where they came from.
    """
    patterns = build_name_patterns(players)
    found = {}

    for player in players:
        pattern = patterns[player["player_id"]]
        picked = []
        seen = set()

        for reference in (notes_by_player.get(str(player["player_id"])) or {}).get("articles", []):
            article = articles_by_id.get(str(reference["id"]))
            if not article:
                continue
            for sentence in split_sentences(article["body"]):
                if len(sentence) < MIN_QUOTE_CHARS or len(sentence) > MAX_QUOTE_CHARS:
                    continue
                if not pattern.search(sentence):
                    continue
                key = sentence[:60].lower()
                if key in seen:
                    continue
                seen.add(key)
                picked.append({
                    "quote": sentence,
                    "headline": article["headline"] or reference["headline"],
                    "byline": article["byline"],
                    "url": reference.get("url", ""),
                })
                if len(picked) >= QUOTES_PER_PLAYER:
                    break
            if len(picked) >= QUOTES_PER_PLAYER:
                break

        found[player["player_id"]] = picked
    return found


# ---------------------------------------------------------------------------
# Facts turned into the situations worth a second look
# ---------------------------------------------------------------------------

def archetypes(player, facts, season):
    """
    Situations the projections cannot see, each derived from a fact rather
    than from anybody's prose. The tag drives a small nudge; the sentence is
    what you read on screen.
    """
    found = []
    draft_year = facts.get("draft_year")
    experience = facts.get("experience")

    if draft_year == season or experience == 0:
        round_text = (
            " (round %s pick)" % facts["draft_round"] if facts.get("draft_round") else ""
        )
        found.append({
            "tag": "rookie",
            "why": "Rookie%s -- no NFL track record for the projections to work from."
                   % round_text,
        })
    elif experience == 1 or (draft_year and draft_year == season - 1):
        found.append({
            "tag": "second_year",
            "why": "Second season -- the year players most often take a jump.",
        })

    if facts.get("changed_teams"):
        found.append({
            "tag": "new_team",
            "why": "New team this season, moved from %s to %s -- a different offence "
                   "and a different role." % (facts["team_before"], facts["team_now"]),
        })

    status = (player.get("injury_status") or "").upper()
    if status not in ("", "ACTIVE", "NORMAL"):
        found.append({
            "tag": "injury_watch",
            "why": "Carrying a %s tag -- read the note before you spend a pick."
                   % status.lower(),
        })

    return found


# ---------------------------------------------------------------------------
# Putting it on the board
# ---------------------------------------------------------------------------

def attach(players, season, limit=None, progress=None):
    """
    Adds commentary to every player, in place. Never raises: no commentary is
    a far smaller problem than no board.
    """
    ranked = sorted(players, key=lambda p: p.get("overall_rank") or 9999)
    wanted = ranked[:limit] if limit else ranked

    notes_cache = read_cache("espn_notes.json", NOTES_CACHE_HOURS) or {}
    facts_cache = read_cache("espn_facts_%s.json" % season, FACTS_CACHE_HOURS) or {}
    article_cache = read_cache("espn_articles.json", ARTICLE_CACHE_HOURS) or {}

    missing_notes = [p for p in wanted if str(p["player_id"]) not in notes_cache]
    missing_facts = [p for p in wanted if str(p["player_id"]) not in facts_cache]

    if progress and (missing_notes or missing_facts):
        progress("Reading player notes (%d players)..."
                 % max(len(missing_notes), len(missing_facts)))

    def load_notes(player):
        notes_cache[str(player["player_id"])] = player_notes(player["player_id"])

    def load_facts(player):
        facts_cache[str(player["player_id"])] = player_facts(player["player_id"], season)

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            list(pool.map(load_notes, missing_notes))
            list(pool.map(load_facts, missing_facts))
    except Exception:
        pass

    if missing_notes:
        write_cache("espn_notes.json", notes_cache)
    if missing_facts:
        write_cache("espn_facts_%s.json" % season, facts_cache)

    # One article covers hundreds of players, so gather every article anyone
    # is tagged in, throw away the duplicates, and read each one once.
    referenced = {}
    for player in wanted:
        for reference in (notes_cache.get(str(player["player_id"])) or {}).get("articles", []):
            referenced.setdefault(str(reference["id"]), reference["headline"])

    to_read = [aid for aid in referenced if aid not in article_cache][:MAX_ARTICLES]
    if to_read:
        if progress:
            progress("Reading %d articles the writers published..." % len(to_read))

        def load_article(article_id):
            article = fetch_article(article_id)
            if article:
                article_cache[article_id] = article

        try:
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                list(pool.map(load_article, to_read))
        except Exception:
            pass
        write_cache("espn_articles.json", article_cache)

    quotes = quotes_from_articles(players, article_cache, notes_cache)

    with_note = with_quote = with_shape = 0
    for player in players:
        key = str(player["player_id"])
        notes = notes_cache.get(key) or {}
        facts = facts_cache.get(key) or {}

        player["note"] = notes.get("note") or ""
        player["note_detail"] = notes.get("note_detail") or ""
        player["note_date"] = notes.get("note_date") or ""
        player["articles"] = notes.get("articles") or []
        player["quotes"] = quotes.get(player["player_id"]) or []
        player["facts"] = facts
        player["archetypes"] = archetypes(player, facts, season) if facts else []

        with_note += bool(player["note"])
        with_quote += bool(player["quotes"])
        with_shape += bool(player["archetypes"])

    return {
        "used": bool(notes_cache or facts_cache),
        "looked_up": len(wanted),
        "articles_read": len(article_cache),
        "with_note": with_note,
        "with_quote": with_quote,
        "with_archetype": with_shape,
    }
