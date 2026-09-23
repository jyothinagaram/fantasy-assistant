"""
Finds your ESPN leagues and connects to them.

You play in more than one league, and they do not use the same rules --
one is full PPR, another has two flex spots. Every number this tool
produces depends on those rules, so everything starts by picking which
league you mean.

The convenient part: ESPN already knows which leagues you are in. This
asks it directly, so you never have to hunt down league ID numbers and
paste them into a config file. If that lookup ever fails, it falls back
to the single league in your .env.
"""

import os
import sys
import warnings

warnings.filterwarnings("ignore")  # hides a harmless OpenSSL notice on macOS

import requests
from dotenv import load_dotenv
from espn_api.football import League


FAN_API = "https://fan.api.espn.com/apis/v2/fans/{swid}"

# ESPN uses numeric game IDs. 1 is football.
FOOTBALL_GAME_ID = 1


def load_credentials():
    """
    Reads your settings and makes sure the required ones are there.

    From a `.env` file on your own computer, or from real environment
    variables when this runs on a host -- `load_dotenv` fills in the first
    and leaves the second alone, so the same code works in both places.
    """
    load_dotenv()

    creds = {
        "season": os.getenv("ESPN_SEASON"),
        "espn_s2": os.getenv("ESPN_S2") or None,
        "swid": os.getenv("ESPN_SWID") or None,
    }

    if not creds["season"]:
        # Say both, because the answer depends on where this is running and
        # the message is read by someone who has just watched a deploy fail.
        # Pointing a server at a .env file it will never have wastes the one
        # piece of information they actually needed.
        sys.exit(
            "Missing ESPN_SEASON.\n"
            "  On this computer: copy .env.example to .env and fill it in.\n"
            "  On a host (Render and the like): add ESPN_SEASON as an "
            "environment variable -- e.g. ESPN_SEASON=2026 -- then deploy "
            "again. ESPN_S2 and ESPN_SWID are set the same way.\n"
            "  See DEPLOY.md."
        )
    try:
        creds["season"] = int(creds["season"])
    except ValueError:
        sys.exit(
            f"ESPN_SEASON should be a year like 2026, not {creds['season']!r}."
        )
    return creds


def discover_leagues(creds):
    """
    Asks ESPN which football leagues you are in this season.

    Returns a list like:
        [{"league_id": 123456, "name": "Your League Name", "team_id": 1}, ...]

    Returns an empty list if ESPN will not answer -- callers should fall
    back to whatever single league is configured in .env.
    """
    if not (creds["swid"] and creds["espn_s2"]):
        return []

    try:
        response = requests.get(
            FAN_API.format(swid=creds["swid"]),
            params={
                "featureFlags": "fanNotificationsEnabled",
                "displayEvents": "true",
                "displayNow": "true",
                "recentDays": "30",
            },
            cookies={"espn_s2": creds["espn_s2"], "SWID": creds["swid"]},
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    found = {}
    for preference in payload.get("preferences", []):
        entry = (preference.get("metaData") or {}).get("entry") or {}

        if entry.get("seasonId") != creds["season"]:
            continue
        if entry.get("gameId") != FOOTBALL_GAME_ID:
            continue

        for group in entry.get("groups") or []:
            league_id = group.get("groupId")
            if not league_id:
                continue
            # Same league can appear more than once in ESPN's response.
            found[league_id] = {
                "league_id": int(league_id),
                "name": group.get("groupName") or f"League {league_id}",
                "team_id": entry.get("entryId"),
            }

    return sorted(found.values(), key=lambda item: item["name"].lower())


def leagues_from_env():
    """Fallback: the single league configured in .env, if any."""
    league_id = os.getenv("ESPN_LEAGUE_ID")
    if not league_id:
        return []
    team_id = os.getenv("ESPN_TEAM_ID")
    return [
        {
            "league_id": int(league_id),
            "name": f"League {league_id}",
            "team_id": int(team_id) if team_id else None,
        }
    ]


def available_leagues(creds):
    """All your leagues, from ESPN if possible and .env if not."""
    return discover_leagues(creds) or leagues_from_env()


def connect(league_id, creds):
    """Opens a connection to one specific league."""
    return League(
        league_id=int(league_id),
        year=creds["season"],
        espn_s2=creds["espn_s2"],
        swid=creds["swid"],
    )


def describe_rules(league):
    """
    A one-line, plain-language summary of how a league scores and starts
    players -- the two things that change who is worth drafting.
    """
    settings = league.settings
    slots = settings.position_slot_counts

    reception_points = next(
        (rule["points"] for rule in settings.scoring_format if rule.get("abbr") == "REC"),
        0.0,
    )
    if reception_points >= 1.0:
        scoring = "full PPR"
    elif reception_points > 0:
        scoring = f"{reception_points:g} PPR"
    else:
        scoring = "standard (no PPR)"

    flex = slots.get("RB/WR/TE", 0)
    flex_text = f"{flex} flex" if flex != 1 else "1 flex"

    return f"{settings.team_count} teams | {scoring} | {flex_text}"


def choose_league(creds, prompt="Which league?"):
    """
    Asks which league to use, in the terminal. If there is only one,
    picks it without asking.
    """
    leagues = available_leagues(creds)

    if not leagues:
        sys.exit(
            "Could not find any ESPN leagues for your account. Check that "
            "ESPN_S2 and ESPN_SWID in your .env are current -- they expire."
        )

    if len(leagues) == 1:
        return leagues[0]

    print(f"\n{prompt}\n")
    for number, league in enumerate(leagues, start=1):
        print(f"  {number}. {league['name']}")

    while True:
        answer = input(f"\nPick 1-{len(leagues)}: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(leagues):
            return leagues[int(answer) - 1]
        print("Please enter one of the numbers listed above.")
