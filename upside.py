"""
Running backs, receivers and tight ends worth grabbing BEFORE it is obvious.

The main waiver list asks "who helps my lineup most on the numbers ESPN
already shows?" That finds the obvious pickups -- the ones you can see in
the app yourself. This file hunts for the other kind: a player whose
situation just changed, so his numbers have not caught up yet.

It looks for four kinds of evidence, and every one is a FACT, not an
opinion:

  1. AN OPENING. A teammate at his position is out, on injured reserve,
     doubtful or suspended. Somebody has to take those carries and targets.
     The bigger the injured player's usual output, the bigger the opening.
  2. A ROLE. How much the offence already uses him: carries plus targets per
     game, and his share of his team's targets. Volume comes before points,
     and it is much less random than touchdowns.
  3. THE CROWD. How fast other ESPN managers are adding him this week.
     Thousands of people reacting to news is a fast, cheap news detector.
  4. THE MATCHUP. How many points the betting market expects his team to
     score this week. Sportsbooks price in injuries and defences with real
     money on the line, so a high team total is the best single matchup
     number there is.

What he did last game counts only a little: one big afternoon is a hint,
not a trend.

FACTS VOTE, PROSE DOES NOT. The latest RotoWire note on each player is
printed word for word -- that is where "he will take over as the lead back"
lives -- but it is never scored. You read it and judge it.

Each signal adds a few points to an "upside score", and every point comes
with the sentence that explains it, so a suggestion can always be checked.
"""

import json

import commentary
import outside_rankings
import status as game_status
import usage as nfl_usage


SKILL_POSITIONS = {"RB", "WR", "TE"}

# ESPN's lineup-slot numbers for the positions we fetch.
SLOT_IDS = {"RB": 2, "WR": 4, "TE": 6}

# Enough players to cover every NFL team's running backs, receivers and
# tight ends, so injured starters (who are almost all rostered) are found.
POOL_SIZE = 900

# Injury designations that open up snaps for a teammate. Questionable is
# left out on purpose -- most questionable players play.
OPENS_A_ROLE = {"OUT", "INJURY_RESERVE", "DOUBTFUL", "SUSPENSION"}

# Receivers and tight ends compete for the same targets, so an injured
# receiver opens a little up for the tight end and vice versa -- but less
# than for someone at his own position.
SHARES_TARGETS_WITH = {"WR": {"WR": 1.0, "TE": 0.5}, "TE": {"TE": 1.0, "WR": 0.5}, "RB": {"RB": 1.0}}

# "Obvious" means most of ESPN already has him. Above this he is not a
# hidden gem even if the signals are strong, and the main list covers him.
OBVIOUS_OWNERSHIP = 60.0

# What an average NFL team is expected to score. A matchup is only called
# good or bad when it is clearly away from this.
AVERAGE_TEAM_TOTAL = 22.5
GOOD_TEAM_TOTAL = 25.5
BAD_TEAM_TOTAL = 19.0

# An injury that already kept a player out of the games played so far is not
# news: his teammates' carries and targets already reflect it, and so do
# their numbers. Only a fresh injury -- someone who has played this season
# and now will not -- earns full credit. Before any games, all count.
OLD_INJURY_CREDIT = 0.3

# An opening only helps someone the team actually uses. A player with less
# than this share of his team's targets (or under 5 touches a game for a
# running back, or under 3 targets a game) gets a fraction of the credit -- he is not next in line.
NEXT_IN_LINE_SHARE = 0.12
NEXT_IN_LINE_TARGETS = 3.0   # per game -- a share of a tiny total means little
NOT_NEXT_IN_LINE_CREDIT = 0.4

# At most this many players from one team, so one injury cannot fill the list
# with the same receiver room.
MAX_PER_TEAM = 2

# Snap share (from nflverse, when available). Being on the field is the
# precondition for everything else: a receiver on 75% of snaps is a starter
# whatever the depth chart says, and a big jump in snaps is the earliest
# sign of a new role -- it usually comes a week before the targets do.
STARTER_SNAPS = 0.70
NEXT_IN_LINE_SNAPS = 0.40

# Snaps only count when the ball comes his way. A receiver on the field for
# 78% of plays who draws 4% of the targets is there to block -- found in the
# first real run (Rashod Bateman). Below these, snaps earn nothing.
SNAPS_NEED_TARGET_SHARE = 0.10   # receivers and tight ends
SNAPS_NEED_TOUCHES = 8.0         # running backs, carries + targets a game

# A quarter of his team's red-zone chances is a real touchdown role. Small
# vote: touchdowns follow red-zone volume, but only a few plays a game.
RED_ZONE_SHARE = 0.25
RED_ZONE_MIN_OPPS = 3

# A player needs at least this much evidence to be listed.
MINIMUM_UPSIDE = 2.0

# How many players get their news note looked up -- one web request each.
NOTES_FOR_TOP = 12


# ---------------------------------------------------------------------------
# Reading ESPN
# ---------------------------------------------------------------------------

def fetch_pool(league, week):
    """
    Every running back, receiver and tight end ESPN tracks, rostered or not,
    with this league's view of who is available.
    """
    from espn_api.football.player import Player

    filters = {
        "players": {
            "filterSlotIds": {"value": list(SLOT_IDS.values())},
            "limit": POOL_SIZE,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        }
    }
    data = league.espn_request.league_get(
        params={"view": "kona_player_info", "scoringPeriodId": week},
        headers={"x-fantasy-filter": json.dumps(filters)},
    )

    players = []
    for item in data.get("players") or []:
        try:
            espn = Player(item, league.year)
        except Exception:
            continue
        if espn.position not in SKILL_POSITIONS:
            continue

        raw = item.get("player") or {}
        ownership = raw.get("ownership") or {}
        season_actual = espn.stats.get(0, {})
        breakdown = season_actual.get("breakdown") or {}
        total = season_actual.get("points") or 0.0
        average = season_actual.get("avg_points") or 0.0
        games = round(total / average) if average else 0

        players.append(
            {
                "player_id": espn.playerId,
                "name": espn.name,
                "position": espn.position,
                "team": outside_rankings.normalize_team(espn.proTeam),
                "available": item.get("status") in {"FREEAGENT", "WAIVERS"},
                "injury_status": espn.injuryStatus if isinstance(espn.injuryStatus, str) else "ACTIVE",
                "percent_owned": ownership.get("percentOwned") or 0.0,
                "owned_change": ownership.get("percentChange") or 0.0,
                "projected_avg": espn.projected_avg_points or 0.0,
                "actual_avg": average if games else None,
                "games_played": games,
                "carries": breakdown.get("rushingAttempts") or 0.0,
                "targets": breakdown.get("receivingTargets") or 0.0,
            }
        )
    return players


def team_totals(season, week):
    """
    Points the betting market expects each team to score this week.

    Worked out from the game total and the spread: if a game is expected to
    total 50 and the home team is favoured by 4, the home team is expected
    to score 27 and the visitors 23.
    """
    data = commentary.get_json(game_status.SCOREBOARD_URL % (week, season))
    out = {}
    for event in (data or {}).get("events") or []:
        for competition in event.get("competitions") or []:
            odds = (competition.get("odds") or [{}])[0]
            total, spread = odds.get("overUnder"), odds.get("spread")
            if total is None or spread is None:
                continue
            # ESPN's spread is from the home team's side: -4.5 = home favoured.
            home = (total - spread) / 2
            away = total - home
            opponents = {}
            for competitor in competition.get("competitors") or []:
                code = outside_rankings.normalize_team(
                    (competitor.get("team") or {}).get("abbreviation")
                )
                side = competitor.get("homeAway")
                opponents[code] = side
            codes = list(opponents)
            for code, side in opponents.items():
                other = next((c for c in codes if c != code), None)
                out[code] = {
                    "implied_points": round(home if side == "home" else away, 1),
                    "opponent": other,
                }
    return out


# ---------------------------------------------------------------------------
# The signals
# ---------------------------------------------------------------------------

def openings(pool):
    """
    For each team and position, the injured players whose work is up for
    grabs, and how many fantasy points a week that work is usually worth.
    """
    by_team = {}
    for player in pool:
        if player["injury_status"] in OPENS_A_ROLE and player["projected_avg"] >= 5:
            by_team.setdefault(player["team"], []).append(player)
    return by_team


def target_shares(pool):
    """Each player's share of his team's targets so far this season."""
    team_targets = {}
    for player in pool:
        team_targets[player["team"]] = team_targets.get(player["team"], 0.0) + player["targets"]
    return {
        id(player): (player["targets"] / team_targets[player["team"]])
        if team_targets.get(player["team"])
        else 0.0
        for player in pool
    }


def season_under_way(injured_by_team):
    """True once any injured player on the list has games on record."""
    return any(
        (p["games_played"] or 0) > 0 for group in injured_by_team.values() for p in group
    )


def score_player(player, injured_by_team, shares, totals):
    """
    Adds up the evidence for one player. Returns (score, reasons).

    Kept as plain additions with a sentence for each, so any suggestion can
    be traced back to exactly what earned it.
    """
    points, reasons = 0.0, []
    position = player["position"]
    games = player["games_played"] or 0

    # 1. An opening
    weights = SHARES_TARGETS_WITH.get(position, {})
    season_started = season_under_way(injured_by_team)
    vacated, names, fresh = 0.0, [], False
    for injured in injured_by_team.get(player["team"], []):
        if injured is player:
            continue
        weight = weights.get(injured["position"], 0.0)
        if not weight:
            continue
        is_fresh = not season_started or (injured["games_played"] or 0) > 0
        fresh = fresh or is_fresh
        vacated += weight * injured["projected_avg"] * (1.0 if is_fresh else OLD_INJURY_CREDIT)
        label = "newly " if is_fresh and season_started else ""
        names.append(
            f"{injured['name']} ({injured['position']}, {label}"
            f"{injured['injury_status'].replace('_', ' ').lower()})"
        )
    if vacated:
        touches = (player["carries"] + player["targets"]) / games if games else 0.0
        next_in_line = (
            not season_started
            or (
                shares.get(id(player), 0.0) >= NEXT_IN_LINE_SHARE
                and games
                and player["targets"] / games >= NEXT_IN_LINE_TARGETS
            )
            or (position == "RB" and touches >= 5)
            or (
                ((player.get("usage") or {}).get("snap_pct") or 0) >= NEXT_IN_LINE_SNAPS
                and ((player.get("usage") or {}).get("target_share") or 0) >= SNAPS_NEED_TARGET_SHARE
            )
        )
        earned = min(3.0, vacated / 4) * (1.0 if next_in_line else NOT_NEXT_IN_LINE_CREDIT)
        points += earned
        if fresh:
            text = f"about {vacated:.0f} pts/week of work to hand out"
        else:
            text = "already out, so his usage below mostly reflects it"
        if not next_in_line:
            text += "; but he has barely been used, so may not be next in line"
        reasons.append(f"OPENING: {', '.join(names)} -- {text}")

    # 2. A role
    use = player.get("usage") or {}
    involved = (
        (use.get("touches_per_game") or 0) >= SNAPS_NEED_TOUCHES
        if position == "RB"
        else (use.get("target_share") or 0) >= SNAPS_NEED_TARGET_SHARE
    )
    if use.get("snap_pct") is not None and not involved and use["snap_pct"] >= STARTER_SNAPS:
        reasons.append(
            f"on the field for {use['snap_pct']:.0%} of snaps but rarely gets the ball"
        )
    elif use.get("snap_pct") is not None:
        trend = use.get("snap_trend")
        if trend is not None and trend >= nfl_usage.SNAP_JUMP:
            points += 1.5
            reasons.append(
                f"ROLE GROWING: played {use['snap_pct']:.0%} of snaps last game, "
                f"up {trend * 100:.0f} pts on his earlier games"
            )
        elif use["snap_pct"] >= STARTER_SNAPS:
            points += 0.5
            reasons.append(f"ROLE: on the field for {use['snap_pct']:.0%} of snaps")

    if (use.get("red_zone_share") or 0) >= RED_ZONE_SHARE and (use.get("red_zone_opps") or 0) >= RED_ZONE_MIN_OPPS:
        points += 0.5
        reasons.append(
            f"ROLE: {use['red_zone_share']:.0%} of his team's red-zone chances "
            f"({use['red_zone_opps']} carries/targets inside the 20)"
        )

    if games:
        touches = (player["carries"] + player["targets"]) / games
        # nflverse's target share uses the team's true total; the ESPN pool
        # estimate misses targets to players outside the pool. Prefer it.
        share = use.get("target_share") if use.get("target_share") is not None else shares.get(id(player), 0.0)
        if position == "RB":
            earned = 2.0 if touches >= 16 else 1.0 if touches >= 10 else 0.0
            if earned:
                reasons.append(f"ROLE: {touches:.0f} carries + targets per game")
        else:
            targets_per_game = player["targets"] / games
            earned = 2.0 if share >= 0.22 else 1.0 if share >= 0.15 else 0.0
            if earned:
                reasons.append(
                    f"ROLE: {targets_per_game:.0f} targets per game, "
                    f"{share:.0%} of his team's targets"
                )
        points += earned

        # One good game is a hint, not a trend -- worth half a point at most.
        actual, projected = player["actual_avg"] or 0.0, player["projected_avg"]
        if actual >= 10 and projected and actual >= 1.5 * projected:
            points += 0.5
            reasons.append(
                f"has averaged {actual:.1f} pts against a {projected:.1f} projection"
            )

    # 3. The crowd
    change = player["owned_change"] or 0.0
    if change >= 15:
        points += 2.0
        reasons.append(f"TRENDING: added in {change:.0f}% more ESPN leagues this week")
    elif change >= 5:
        points += 1.0
        reasons.append(f"TRENDING: added in {change:.0f}% more ESPN leagues this week")

    # 4. The matchup
    game = totals.get(player["team"])
    if game:
        implied = game["implied_points"]
        if implied >= GOOD_TEAM_TOTAL:
            points += 1.0
            reasons.append(
                f"MATCHUP: vs {game['opponent']}, team expected to score {implied:.0f} "
                f"(average is about {AVERAGE_TEAM_TOTAL:.0f})"
            )
        elif implied <= BAD_TEAM_TOTAL:
            points -= 1.0
            reasons.append(
                f"tough matchup: vs {game['opponent']}, team expected to score "
                f"only {implied:.0f}"
            )

    # He cannot use an opening if he is the one who is hurt.
    if player["injury_status"] in OPENS_A_ROLE:
        points = 0.0

    return round(points, 2), reasons


def find(league, season, week):
    """
    The under-the-radar skill players available in this league, best first.

    Matchup on its own never qualifies someone: every player on a
    high-scoring team would otherwise make the list. He needs an opening, a
    role or a crowd moving toward him as well.
    """
    pool = fetch_pool(league, week)
    try:
        nfl_usage.attach(pool, nfl_usage.load(season))
    except Exception:
        pass  # usage is a bonus; ESPN's numbers still work without it
    injured = openings(pool)
    shares = target_shares(pool)
    totals = team_totals(season, week)

    found = []
    for player in pool:
        if not player["available"] or player["percent_owned"] >= OBVIOUS_OWNERSHIP:
            continue
        score, reasons = score_player(player, injured, shares, totals)
        has_substance = any(
            r.startswith(("OPENING", "ROLE", "TRENDING")) for r in reasons
        )
        if score >= MINIMUM_UPSIDE and has_substance:
            player["upside"] = score
            player["upside_reasons"] = reasons
            player["opponent"] = (totals.get(player["team"]) or {}).get("opponent")
            found.append(player)

    found.sort(key=lambda p: p["upside"], reverse=True)
    import defense
    defense.attach_for_league(league, season, week, found)  # shown, never scored
    per_team, trimmed = {}, []
    for player in found:
        per_team[player["team"]] = per_team.get(player["team"], 0) + 1
        if per_team[player["team"]] <= MAX_PER_TEAM:
            trimmed.append(player)
    found = trimmed

    # The news note, word for word. Shown, never scored.
    for player in found[:NOTES_FOR_TOP]:
        try:
            notes = commentary.player_notes(player["player_id"])
        except Exception:
            notes = {}
        player["note"] = notes.get("note") or None
        player["note_detail"] = notes.get("note_detail") or None
        player["note_date"] = notes.get("note_date") or None

    return found
