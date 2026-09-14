"""
Trades: which ones to offer, and whether one on the table is any good.

A trade is judged exactly the way a waiver claim is: play out every remaining
regular-season week, solve each team's best legal lineup, and add up the
points -- once as the rosters are now, once after the trade. The difference
is what the trade is worth to that team. (See `waivers.team_value`.)

Doing it by lineup rather than by "who is the better player" is the whole
point. Trading two decent receivers for one great one looks like a loss on
paper -- two players for one -- but if only one of them was starting for you,
you just upgraded a lineup slot and freed a bench spot. And the same trade
can be good for BOTH teams, because each team needs different things. That
is the kind of trade that actually gets accepted.

So the finder only suggests trades that improve BOTH lineups. A lopsided
offer wastes a message, and in two of these leagues four veto votes can
block it anyway.

Uneven trades change roster sizes, so they are settled the way a real
manager would settle them:

  * The team receiving more players must cut someone -- whoever it costs
    them least to lose.
  * The team receiving fewer players gets an open spot. We do NOT assume they
    fill it with a good free agent; the open spot is counted as empty. That
    makes these trades look slightly worse than they are, never better.

FACTS VOTE, PROSE DOES NOT, as everywhere else here.
"""

import itertools

import lineup
import waivers


# Only players who matter are worth building trades around -- nobody gives
# something up for a player who would never start for them. Players below
# this in a normal week are left out of trade ideas (they can still be cut).
TRADEABLE_POINTS = 6.0

# A trade has to help each side by at least this many points a week to be
# suggested. Below that it is within the error of the projections.
WORTH_A_TRADE = 0.5

# Trades suggested per opponent and overall, so the list stays readable.
IDEAS_PER_OPPONENT = 2
IDEAS_TOTAL = 10

# Two-for-one trades multiply fast, so only this many of each team's most
# valuable players are tried in them.
TWO_FOR_ONE_DEPTH = 8


# ---------------------------------------------------------------------------
# Valuing a trade
# ---------------------------------------------------------------------------

def settle_roster(players, roster_limit, slots, weeks, first_week):
    """
    If a team has more players than its roster allows, cut the ones it costs
    least to lose, one at a time. Returns (roster, the players cut).
    """
    roster = list(players)
    cut = []
    while len([p for p in roster if waivers.droppable(p)]) > roster_limit:
        candidates = [p for p in roster if waivers.droppable(p)]
        best = max(
            candidates,
            key=lambda p: (
                waivers.team_value([q for q in roster if q is not p], slots, weeks, first_week),
                -waivers.per_game_value(p),
            ),
        )
        roster.remove(best)
        cut.append(best)
    return roster, cut


def value_for(team_players, giving, getting, roster_limit, slots, weeks, first_week, baseline=None):
    """What a trade is worth to one team, in total points. Plus who they would cut."""
    if baseline is None:
        baseline = waivers.team_value(team_players, slots, weeks, first_week)
    after = [p for p in team_players if not any(p is g for g in giving)] + list(getting)
    after, cut = settle_roster(after, roster_limit, slots, weeks, first_week)
    return waivers.team_value(after, slots, weeks, first_week) - baseline, cut


def evaluate(mine, theirs, my_side, their_side, roster_limit, slots, weeks, first_week,
             my_baseline=None, their_baseline=None):
    """
    A trade from both sides. `my_side` is what I give, `their_side` what I get.
    """
    week_count = max(1, len(weeks))
    my_gain, my_cut = value_for(
        mine, my_side, their_side, roster_limit, slots, weeks, first_week, my_baseline
    )
    their_gain, their_cut = value_for(
        theirs, their_side, my_side, roster_limit, slots, weeks, first_week, their_baseline
    )
    return {
        "give": list(my_side),
        "get": list(their_side),
        "my_gain": round(my_gain, 2),
        "their_gain": round(their_gain, 2),
        "my_gain_per_week": round(my_gain / week_count, 2),
        "their_gain_per_week": round(their_gain / week_count, 2),
        "i_cut": my_cut,
        "they_cut": their_cut,
    }


# ---------------------------------------------------------------------------
# Finding trade ideas
# ---------------------------------------------------------------------------

def tradeable(players):
    return [
        p for p in players
        if waivers.droppable(p) and waivers.per_game_value(p) >= TRADEABLE_POINTS
    ]


def ideas_with(mine, theirs, roster_limit, slots, weeks, first_week):
    """
    Every one-for-one, two-for-one and one-for-two trade with one opponent
    that improves both lineups, best for me first.
    """
    my_base = waivers.team_value(mine, slots, weeks, first_week)
    their_base = waivers.team_value(theirs, slots, weeks, first_week)

    my_pieces = tradeable(mine)
    their_pieces = tradeable(theirs)
    top = lambda players: sorted(players, key=waivers.per_game_value, reverse=True)[:TWO_FOR_ONE_DEPTH]

    shapes = [((a,), (b,)) for a in my_pieces for b in their_pieces]
    shapes += [(pair, (b,)) for pair in itertools.combinations(top(my_pieces), 2) for b in their_pieces]
    shapes += [((a,), pair) for a in my_pieces for pair in itertools.combinations(top(their_pieces), 2)]

    found = []
    for give, get in shapes:
        # A cheap filter before the full valuation: if what I give is worth
        # far more than what I get in raw points, they will say yes and I
        # will regret it; far less, and they will say no. Either way skip it.
        give_points = sum(waivers.per_game_value(p) for p in give)
        get_points = sum(waivers.per_game_value(p) for p in get)
        if get_points > 1.6 * give_points or give_points > 1.6 * get_points:
            continue

        result = evaluate(
            mine, theirs, give, get, roster_limit, slots, weeks, first_week, my_base, their_base
        )
        if (result["my_gain_per_week"] >= WORTH_A_TRADE
                and result["their_gain_per_week"] >= WORTH_A_TRADE):
            found.append(result)

    # Best for me first; between similar trades, the one that helps them
    # more is likelier to be accepted.
    found.sort(key=lambda r: (r["my_gain"], r["their_gain"]), reverse=True)
    return without_padding(found)


def without_padding(found):
    """
    Drops trades that are just a smaller trade with a spare player thrown in.

    If giving Tuten alone for Burrow is worth +29 to me, giving Tuten AND
    Murray for Burrow at the same +29 means handing over Murray for nothing.
    A trade is kept only if it beats every smaller version of itself.
    """
    kept = []
    for trade in found:
        give, get = set(map(id, trade["give"])), set(map(id, trade["get"]))
        padded = any(
            other is not trade
            and set(map(id, other["give"])) <= give
            and set(map(id, other["get"])) >= get
            and (len(other["give"]), len(other["get"])) != (len(trade["give"]), len(trade["get"]))
            and other["my_gain"] >= trade["my_gain"] - 1.0
            for other in found
        )
        if not padded:
            kept.append(trade)
    return kept


def on_paper(result):
    """
    How the trade looks to someone comparing normal-week points, which is
    roughly how the other manager -- and the league's veto voters -- will
    judge it. Returns (points I give, points I get).
    """
    give = sum(waivers.per_game_value(p) for p in result["give"])
    get = sum(waivers.per_game_value(p) for p in result["get"])
    return round(give, 1), round(get, 1)


# ---------------------------------------------------------------------------
# Reading ESPN
# ---------------------------------------------------------------------------

def trade_settings(league):
    try:
        data = league.espn_request.league_get(params={"view": "mSettings"})
        settings = data["settings"].get("tradeSettings") or {}
    except Exception:
        settings = {}
    deadline = settings.get("deadlineDate")
    if deadline:
        import datetime as dt
        deadline = dt.datetime.fromtimestamp(deadline / 1000).strftime("%b %d")
    return {"deadline": deadline, "veto_votes": settings.get("vetoVotesRequired")}


def roster_limit(league):
    counts = league.settings.position_slot_counts
    return sum(int(c or 0) for c in counts.values()) - int(counts.get("IR", 0) or 0)


def build(league, team_id, season, week=None, use_experts=True, force_refresh=False):
    """Every team's roster, valued the same way, ready for trade maths."""
    import weekly_rankings

    first_week = week or waivers.first_playable_week(league, season)
    weeks = list(range(first_week, league.settings.reg_season_count + 1))
    byes = waivers.bye_weeks(league)
    week_rosters = lineup.rosters_for_week(league, first_week)

    rosters = {
        team.team_id: {
            "team": team,
            "players": [
                waivers.as_player(p, first_week, byes)
                for p in week_rosters.get(team.team_id, team.roster)
            ],
        }
        for team in league.teams
    }

    everyone = [p for entry in rosters.values() for p in entry["players"]]
    try:
        import usage
        usage.attach(everyone, usage.load(season))
    except Exception:
        pass
    expert_summary = None
    if use_experts:
        _, by_position = weekly_rankings.load_for_league(
            league, season, first_week, force_refresh=force_refresh
        )
        if by_position:
            expert_summary = weekly_rankings.attach(everyone, by_position)
    if expert_summary is None:
        for player in everyone:
            player.setdefault("weekly_projection", None)
    lineup.score(everyone, first_week)

    return {
        "league_name": league.settings.name,
        "team_id": team_id,
        "first_week": first_week,
        "weeks": weeks,
        "slots": lineup.open_slots(league),
        "roster_limit": roster_limit(league),
        "rosters": rosters,
        "settings": trade_settings(league),
        "expert_summary": expert_summary,
    }


def find_ideas(board, progress=None):
    mine = board["rosters"][board["team_id"]]["players"]
    ideas = []
    for team_id, entry in board["rosters"].items():
        if team_id == board["team_id"]:
            continue
        if progress:
            progress(entry["team"].team_name)
        found = ideas_with(
            mine, entry["players"], board["roster_limit"], board["slots"],
            board["weeks"], board["first_week"],
        )
        for idea in found[:IDEAS_PER_OPPONENT]:
            idea["partner"] = entry["team"]
            ideas.append(idea)
    ideas.sort(key=lambda r: (r["my_gain"], r["their_gain"]), reverse=True)
    return ideas[:IDEAS_TOTAL]


def find_player(board, name):
    """Finds a rostered player by (part of) his name. Returns (team_id, player)."""
    wanted = name.lower().strip()
    matches = [
        (team_id, p)
        for team_id, entry in board["rosters"].items()
        for p in entry["players"]
        if wanted in p["name"].lower()
    ]
    exact = [m for m in matches if m[1]["name"].lower() == wanted]
    matches = exact or matches
    if not matches:
        raise LookupError(f"nobody rostered in {board['league_name']} matches {name!r}")
    if len(matches) > 1:
        names = ", ".join(p["name"] for _, p in matches[:5])
        raise LookupError(f"{name!r} matches more than one player: {names}")
    return matches[0]


def evaluate_named(board, give_names, get_names):
    """Checks a specific trade, given players by name."""
    mine = board["rosters"][board["team_id"]]["players"]
    give = []
    for name in give_names:
        team_id, player = find_player(board, name)
        if team_id != board["team_id"]:
            raise LookupError(f"{player['name']} is not on your team")
        give.append(player)

    get, partner = [], None
    for name in get_names:
        team_id, player = find_player(board, name)
        if team_id == board["team_id"]:
            raise LookupError(f"{player['name']} is already on your team")
        if partner is not None and team_id != partner:
            raise LookupError("everyone you get must come from the same team")
        partner = team_id
        get.append(player)

    if partner is None:
        raise LookupError("name at least one player you would get")
    result = evaluate(
        mine, board["rosters"][partner]["players"], give, get,
        board["roster_limit"], board["slots"], board["weeks"], board["first_week"],
    )
    result["partner"] = board["rosters"][partner]["team"]
    return result
