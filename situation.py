"""
When a player's past games no longer describe his present.

A season average is only evidence if the games in it were played in the
situation the player is in now. The case that prompted this: through week 2
Drake London had caught passes from Cooper Rush in both his games, because
Michael Penix Jr. was hurt. His 7.2-point average was a real number about a
team that no longer exists. Blending it into his value -- which is what
`waivers.per_game_value` does with every game -- charged him for a
quarterback he will not be playing with again.

So this finds, from the free nflverse play-by-play already on disk, the
games a pass-catcher played with a DIFFERENT quarterback than the one his
team is expected to start now, and marks them stale. Those games stop
counting toward his average, so his value leans on the projections instead
-- which is the right place to lean when the only real evidence describes a
different offence.

QUARTERBACKS ARE MATCHED BY ID, NEVER BY NAME. The play-by-play writes
passers as "C.Rush", and a first-initial-and-surname match would quietly
fail on "A.St. Brown" or two brothers on one roster. A mismatch would look
exactly like the thing this file is trying to detect -- a starter who has
thrown none of the passes -- so it would mark whole rosters stale and move
every number on the board. nflverse publishes an ESPN id for every player,
so the passer's id is mapped to ESPN's and compared with the id we already
hold. Names are used only in the sentence shown to the reader.

HOW THE EXPECTED QUARTERBACK IS DECIDED. Not from news, and not from a
depth chart nobody publishes for free: the expected starter is the best
quarterback on the team who is fit to play, out of the quarterbacks the
league can actually see (every roster plus the waiver pool -- between them
they cover all 32 teams). A quarterback who is hurt, suspended or on IR
cannot be the expected starter, so his weeks are not the benchmark. When
the best fit quarterback is also the one who has been throwing the passes,
nothing is stale and nothing changes, which is the ordinary case.

TWO GUARDS, both there because a wrong call here quietly moves every number
on the board:

  * The expected starter must look like a real starter (a projection worth
    starting). Otherwise a rostered third-stringer on a team whose actual
    starter nobody rosters would mark every week stale.
  * Nothing is ever marked stale for the quarterback himself, or for
    kickers and defences. A quarterback's own games describe his own play.

FACTS VOTE, PROSE DOES NOT. Every discount here comes with the sentence
that produced it -- "both his games were thrown by C.Rush, not Michael
Penix Jr." -- so it can be checked against the box score rather than
believed.
"""

import collections
import csv
import gzip
import io

import redzone
import usage


# Positions whose production really is the quarterback's production.
# Running backs are deliberately left out: most of a back's work is carries,
# which arrive whoever is under centre, and marking his whole average stale
# would throw away the part of his game that did not change. A back's
# receiving work does move with the quarterback, but not enough to justify
# discounting everything else he does.
CATCHES_PASSES = {"WR", "TE"}

# A quarterback below this in a normal week is not somebody's plan for the
# season, so he is not used as the benchmark for what "changed".
REAL_STARTER_POINTS = 10.0

# Designations that mean a quarterback cannot be the expected starter.
CANNOT_START = {"OUT", "INJURY_RESERVE", "SUSPENSION", "DOUBTFUL"}


def short_name(name):
    """
    'Michael Penix Jr.' -> 'M.Penix', which is how the play-by-play writes
    passers. Suffixes are dropped; they never appear in the short form.
    """
    parts = [p for p in (name or "").replace(".", " ").split() if p]
    parts = [p for p in parts if p.lower().strip(".") not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    if len(parts) < 2:
        return (parts[0] if parts else "").title()
    return f"{parts[0][0].upper()}.{parts[-1].title()}"


def passers_by_week(pbp_text, by_gsis):
    """
    {(team, week): (ESPN id of the man who threw most of that team's passes,
    the name to show)}.

    Most attempts, not the first passer seen: a starter who leaves injured
    in the second quarter should not make the whole game look like his.
    """
    if not pbp_text:
        return {}
    counts = collections.defaultdict(collections.Counter)
    names = {}
    for row in csv.DictReader(io.StringIO(pbp_text)):
        if row.get("season_type") not in (None, "", "REG"):
            continue
        team, week = row.get("posteam"), row.get("week")
        gsis = row.get("passer_player_id")
        if not (team and week and gsis):
            continue
        espn = by_gsis.get(gsis)
        if espn is None:
            continue
        try:
            counts[(team, int(week))][espn] += 1
        except ValueError:
            continue
        names[espn] = row.get("passer_player_name") or ""
    return {
        key: (tally.most_common(1)[0][0], names.get(tally.most_common(1)[0][0], ""))
        for key, tally in counts.items() if tally
    }


def expected_starters(players, value_of):
    """
    {team: the quarterback it should start now}.

    The best fit quarterback the league can see. `value_of` is how a player
    is priced -- passed in rather than imported so this file never has an
    opinion about valuation.
    """
    best = {}
    for player in players:
        if player.get("position") != "QB":
            continue
        team = player.get("pro_team")
        if not team:
            continue
        if (player.get("injury_status") or "ACTIVE") in CANNOT_START:
            continue
        if value_of(player) < REAL_STARTER_POINTS:
            continue
        if team not in best or value_of(player) > value_of(best[team]):
            best[team] = player
    return best


def attach(players, season, value_of, pbp_text=None, players_text=None, also=None):
    """
    Marks every pass-catcher whose games were thrown by somebody else.

    `also` is extra players -- normally the waiver pool -- considered only
    when working out who each team should be starting at quarterback, never
    marked themselves. Leave it out and any team whose starter is
    unrostered will look unchanged.

    Adds `stale_games` (how many of his games no longer describe his
    situation) and `situation_note` (the sentence that says why) to each
    player it applies to. Returns a short summary, or None when the
    play-by-play is unavailable -- in which case nothing is marked and every
    number stays exactly as it was.
    """
    if pbp_text is None:
        pbp_text = redzone.download(season)
    if players_text is None:
        players_text = usage.download("players", season)
    if not players_text:
        return None
    by_gsis, _ = usage.id_maps(players_text)
    passers = passers_by_week(pbp_text, by_gsis)
    if not passers:
        return None

    starters = expected_starters(list(players) + list(also or []), value_of)
    weeks_by_team = collections.defaultdict(list)
    for (team, week) in passers:
        weeks_by_team[team].append(week)

    changed = 0
    for player in players:
        player.setdefault("stale_games", 0)
        player.setdefault("situation_note", None)
        if player.get("position") not in CATCHES_PASSES:
            continue
        team = player.get("pro_team")
        starter = starters.get(team)
        if not starter:
            continue
        wanted = starter.get("player_id")
        if wanted is None:
            continue
        weeks = sorted(weeks_by_team.get(team, []))
        if not weeks:
            continue

        # Only the games he actually played can be stale, and we know how
        # many those were, not which. Counting from the most recent week
        # backwards matches how a season average is usually wrong: the old
        # games are the ones under the old quarterback.
        played = player.get("games_played") or 0
        if not played:
            continue
        his_weeks = weeks[-played:]
        stale = [w for w in his_weeks if (passers.get((team, w)) or (None, ""))[0] != wanted]
        if not stale:
            continue

        throwers = sorted(
            {(passers.get((team, w)) or (None, ""))[1] for w in stale}
            - {""}
        )
        player["stale_games"] = len(stale)
        player["situation_note"] = (
            f"{len(stale)} of {played} game{'s' if played != 1 else ''} thrown by "
            f"{', '.join(throwers)}, not {starter['name']}"
        )
        changed += 1

    return {"players_marked": changed, "teams": len(starters)}
