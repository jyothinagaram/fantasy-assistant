"""
When a player's past games no longer describe his present.

A season average is only evidence if the games in it were played in the
situation the player is in now. The case that prompted this: through week 2
Drake London had caught passes from Cooper Rush in both his games, because
Michael Penix Jr. was hurt. His 7.2-point average was a real number about a
team that no longer exists. Blending it into his value -- which is what
`waivers.per_game_value` does with every game -- charged him for a
quarterback he will not be playing with again.

So this finds two kinds of game that are not evidence, and marks them
stale:

  1. A DIFFERENT QUARTERBACK. Games a pass-catcher played with someone
     other than the quarterback his team is expected to start now.
  2. A GAME HE DID NOT PLAY. A game cut short -- the injury in the first
     quarter, the concussion check he never came back from. Kyler Murray
     played eleven snaps, 17% of the game, and scored -0.38; that number
     says nothing about how he plays and everything about when he left,
     and it was dragging his value from an 18.5 projection down to 13.9. Those games stop
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
  * A quarterback's own games are never stale for reason (1) -- his own
    play is his own play -- and kickers and defences have no snap counts,
    so neither rule reaches them.
  * Reason (2) is judged against the player HIMSELF wherever possible: a
    committee back who takes 30% of the snaps every week is doing his job,
    not limping off, so only a game far below his own normal counts. A
    player with no other game to compare against gets an absolute floor,
    and only at quarterback, where the starter plays every snap and a
    figure like 17% cannot mean anything else. There is deliberately no
    absolute floor for the other positions, because their roles vary too
    much for one to be honest.

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

# A game below this share of the player's own normal snap count is a game
# he did not really play.
PART_OF_HIS_NORMAL = 0.5

# He needs this many other games before his own normal means anything.
ENOUGH_TO_COMPARE = 2

# With nothing to compare against, only a quarterback is judged, and only
# against this: a starting quarterback plays nearly every snap, so a share
# this low is someone who left or someone who came on when it was over.
QB_PLAYED_THE_GAME = 0.5


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


def snaps_by_week(snaps_text, by_pfr):
    """{ESPN id: {week: share of his team's offensive snaps}}."""
    if not snaps_text:
        return {}
    found = collections.defaultdict(dict)
    for row in usage.rows(snaps_text):
        if row.get("game_type") != "REG":
            continue
        espn = by_pfr.get(row.get("pfr_player_id"))
        week = usage.number(row.get("week"))
        share = usage.number(row.get("offense_pct"))
        if espn is None or week is None or share is None:
            continue
        found[espn][int(week)] = share
    return found


def median(values):
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def games_cut_short(weeks_played, position):
    """
    The weeks he was on the field far less than he normally is.

    `weeks_played` is {week: snap share}. Judged against his own median so
    that a part-time role is not mistaken for an injury; with too little to
    compare against, only a quarterback is judged, and only against the
    fact that starting quarterbacks play the whole game.
    """
    if not weeks_played:
        return []
    short = []
    for week, share in weeks_played.items():
        others = [s for w, s in weeks_played.items() if w != week]
        if len(others) >= ENOUGH_TO_COMPARE:
            normal = median(others)
            if normal and share < PART_OF_HIS_NORMAL * normal:
                short.append(week)
        elif position == "QB" and share < QB_PLAYED_THE_GAME:
            short.append(week)
    return sorted(short)


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


def attach(players, season, value_of, pbp_text=None, players_text=None, also=None,
           snaps_text=None):
    """
    Marks the games that are not evidence about a player any more.

    `also` is extra players -- normally the waiver pool -- considered only
    when working out who each team should be starting at quarterback, never
    marked themselves. Leave it out and any team whose starter is
    unrostered will look unchanged.

    Adds `stale_games` (how many of his games no longer describe him) and
    `situation_note` (the sentence that says why) to each player it applies
    to. Returns a short summary, or None when nothing could be read -- in
    which case nothing is marked and every number stays as it was.
    """
    if pbp_text is None:
        pbp_text = redzone.download(season)
    if players_text is None:
        players_text = usage.download("players", season)
    if snaps_text is None:
        snaps_text = usage.download("snaps", season)
    if not players_text:
        return None

    by_gsis, by_pfr = usage.id_maps(players_text)
    passers = passers_by_week(pbp_text, by_gsis)
    snaps = snaps_by_week(snaps_text, by_pfr)
    if not passers and not snaps:
        return None

    starters = expected_starters(list(players) + list(also or []), value_of)
    weeks_by_team = collections.defaultdict(list)
    for (team, week) in passers:
        weeks_by_team[team].append(week)

    changed = 0
    for player in players:
        player.setdefault("stale_games", 0)
        player.setdefault("situation_note", None)
        played = player.get("games_played") or 0
        if not played:
            continue

        his_snaps = snaps.get(player.get("player_id")) or {}
        # Which weeks he actually played, from the snap counts when they are
        # there. Falling back to "the last N weeks" is only a guess, but it
        # is the same guess the season average itself makes.
        if his_snaps:
            his_weeks = sorted(w for w, share in his_snaps.items() if share)
        else:
            team_weeks = sorted(weeks_by_team.get(player.get("pro_team"), []))
            his_weeks = team_weeks[-played:] if team_weeks else []
        if not his_weeks:
            continue

        stale, reasons = set(), []

        # 1. Somebody else was throwing.
        if player.get("position") in CATCHES_PASSES:
            starter = starters.get(player.get("pro_team"))
            wanted = starter.get("player_id") if starter else None
            if wanted is not None:
                elsewhere = [
                    w for w in his_weeks
                    if (passers.get((player["pro_team"], w)) or (None, ""))[0] != wanted
                    and (passers.get((player["pro_team"], w)) or (None, ""))[0] is not None
                ]
                if elsewhere:
                    stale.update(elsewhere)
                    throwers = sorted(
                        {(passers.get((player["pro_team"], w)) or (None, ""))[1]
                         for w in elsewhere} - {""}
                    )
                    reasons.append(
                        f"{len(elsewhere)} of {played} game"
                        f"{'s' if played != 1 else ''} thrown by "
                        f"{', '.join(throwers)}, not {starter['name']}"
                    )

        # 2. He was barely on the field.
        short = [w for w in games_cut_short(his_snaps, player.get("position")) if w in his_weeks]
        if short:
            stale.update(short)
            shares = ", ".join(f"week {w} {round(his_snaps[w] * 100)}% of snaps" for w in short)
            reasons.append(f"left {'a game' if len(short) == 1 else 'games'} early ({shares})")

        if not stale:
            continue
        player["stale_games"] = min(played, len(stale))
        player["situation_note"] = "; ".join(reasons)
        changed += 1

    return {"players_marked": changed, "teams": len(starters)}
