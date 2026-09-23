"""
What every team in the league actually needs, and who can fill it.

The trade engine in `trades.py` answers "is this trade good?". This answers
the question you ask before that one: "where should I even be looking?"

It prices two things for every team, in the same currency as everything else
here -- points per week of best lineup, over the remaining season:

  * A NEED at a position is what that team would gain by adding one
    league-average starter there. A team starting a 4-point tight end gains
    a lot from an average one; a team with a stud gains almost nothing.
    So a need is not "they only have two running backs", it is "their
    lineup is leaking points at running back", which is the thing that
    actually makes a manager answer a message.

  * A SPARE at a position is a real player -- someone good enough to start
    somewhere -- whom that team could lose for almost nothing, because
    somebody just as good would step into the slot. Depth only has value
    while it is in the lineup. A fourth receiver on a team that starts
    three is worth roughly zero to them and possibly a lot to me.

A NEED IS ONLY WORTH TRADING FOR IF THE WAIVER WIRE CANNOT FIX IT. This is
the difference between a hole and a hole worth paying for. A team starting a
weak quarterback is leaking real points -- but in a one-quarterback league
there is usually a 17-point quarterback sitting in free agency, so that hole
costs nothing but a waiver claim to fix, and trading a receiver for it is
burning an asset on a problem that solves itself. A thin receiver room is
the opposite: the best free-agent receiver is barely startable, so the only
way out is a trade. So every need is priced twice -- once against an average
starter, once against the best player actually available for free -- and
what is left over, the part waivers CANNOT fix, is what a trade at that
position is worth. That is the honest version of "receivers and running
backs win leagues": it is not a preference for those positions, it is that
their pools run dry and the quarterback pool does not.

A trade worth chasing is where those two lists cross: they have a spare at
a position I am leaking points at, and I have a spare at a position they
are leaking points at. That is the matching layer; the actual valuation is
still done by `trades.evaluate`, which remains the only thing allowed to
say a trade is good.

PERCEPTION IS MODELLED SEPARATELY FROM VALUE. The other manager does not
run this program. He compares points-per-game and looks at his own roster
holes, and in two of these leagues four veto votes can kill a trade that
looks lopsided to people who are not even in it. So every idea also carries
how it READS to him -- whether he gets more raw points than he gives, and
whether what he gets lands on a hole he can see. That never changes whether
a trade is good for me; it only changes whether it is worth sending, and
what to say when I send it.

FACTS VOTE, PROSE DOES NOT, as everywhere else here.
"""

import lineup
import trades
import waivers


# A need this small is noise in the projections, not a hole worth trading for.
NEED_BAR = 1.0

# A player a team can lose for less than this per week is spare depth: the
# next man in the slot is nearly as good.
SPARE_BAR = 1.0

# The most expensive "spare" worth building an offer around. Above this we
# are asking for a player the team would genuinely miss, which is a
# different conversation (and usually a no).
MAX_SPARE_COST = 2.5

# On-paper points gap, per week, at which a trade starts to LOOK unfair to
# the other manager and to the veto voters, whatever the lineup maths says.
PAPER_GAP = 1.5

# Positions nobody trades. A kicker or a defence is streamed off waivers
# every week, so offering one is not a trade chip -- it is noise crowding out
# the real ones. They are still PRICED as needs, because a hole at kicker is
# a genuine hole; it is just one the waiver wire fixes, not a trade.
STREAMED_POSITIONS = {"K", "D/ST"}

# Needs-matched ideas kept per opponent and overall.
IDEAS_PER_OPPONENT = 2
IDEAS_TOTAL = 10


# ---------------------------------------------------------------------------
# The bar for "a league-average starter"
# ---------------------------------------------------------------------------

def starts_per_team(slots):
    """
    How many of each position a team starts in a normal week.

    Dedicated slots count for the position they name. A flex slot is split
    evenly between the positions it accepts -- it is not knowable in advance
    which one fills it, and splitting it evenly is the assumption that
    favours no position.
    """
    counts = {}
    for slot in slots:
        eligible = lineup.SLOT_ELIGIBILITY[slot]
        for position in eligible:
            counts[position] = counts.get(position, 0.0) + 1.0 / len(eligible)
    return counts


def positions_started(slots):
    return sorted(starts_per_team(slots))


def starter_bar(rosters, slots):
    """
    What an average STARTER at each position scores in a normal week.

    Not an average of everyone rostered -- that is dragged down by the
    handcuffs and streamers sitting on benches, and would make every hole
    look filled. The pool is the top N at the position across the whole
    league, where N is how many of them the league starts each week, and the
    bar is the middle of that pool.

    `rosters` is the {team_id: {"players": [...]}} map that `trades.build`
    produces.
    """
    everyone = [p for entry in rosters.values() for p in entry["players"]]
    team_count = max(1, len(rosters))
    starts = starts_per_team(slots)

    bar = {}
    for position, per_team in starts.items():
        at_position = sorted(
            (waivers.per_game_value(p) for p in everyone if p.get("position") == position),
            reverse=True,
        )
        if not at_position:
            bar[position] = 0.0
            continue
        pool = at_position[: max(1, round(team_count * per_team))]
        middle = len(pool) // 2
        bar[position] = round(
            pool[middle] if len(pool) % 2 else (pool[middle - 1] + pool[middle]) / 2, 2
        )
    return bar


def average_starter(position, points):
    """
    A stand-in player used only to price a hole: what would this team gain
    if an average starter at this position fell out of the sky? He never
    appears in a trade, never has a bye and is never hurt -- he is a ruler,
    not a person.
    """
    return {
        "name": f"an average {position}",
        "position": position,
        "season_projected_avg": points,
        "season_actual_avg": None,
        "games_played": 0,
        "bye_week": None,
        "injury_status": "ACTIVE",
        "current_slot": "BE",
        "score": None,
        "is_average_starter": True,
    }


def replacement_level(free_agents, slots):
    """
    The best player at each position who can be had for nothing.

    The BEST one, not an average of the pool: on waivers you claim the top
    man left, you do not draw at random. If the pool is empty at a position
    the replacement is None, and a hole there is worth its full value.
    """
    best = {}
    for position in positions_started(slots):
        at_position = [p for p in free_agents or [] if p.get("position") == position]
        if not at_position:
            best[position] = None
            continue
        best[position] = max(at_position, key=waivers.per_game_value)
    return best


# ---------------------------------------------------------------------------
# One team's needs and spares
# ---------------------------------------------------------------------------

def profile(players, slots, weeks, first_week, bar, roster_limit=None, replacement=None):
    """
    Every position this team starts, with what a hole there costs them and
    which of their players they could lose without feeling it.

    Both numbers are points per week of best lineup, so they can be compared
    with each other, with a trade's gain, and with a waiver claim.

    Note the asymmetry in how the two are measured, which is deliberate:
    adding a player assumes an open roster spot (an addition through a trade
    comes with the player leaving), while losing one leaves the spot empty
    rather than assuming a free agent fills it. Both choices make trades
    look slightly worse than they are, never better.
    """
    week_count = max(1, len(weeks))
    base = waivers.team_value(players, slots, weeks, first_week)

    profiles = {}
    for position in positions_started(slots):
        filled = players + [average_starter(position, bar.get(position, 0.0))]
        raw_need = (waivers.team_value(filled, slots, weeks, first_week) - base) / week_count

        # What the waiver wire would fix for free. Whatever is left is the
        # only part a trade can claim credit for.
        free_fix = 0.0
        spare_man = (replacement or {}).get(position)
        if spare_man is not None:
            free_fix = max(
                0.0,
                (waivers.team_value(players + [spare_man], slots, weeks, first_week) - base)
                / week_count,
            )
        need = max(0.0, raw_need - free_fix)

        spares = []
        for player in players:
            if player.get("position") != position or not waivers.droppable(player):
                continue
            without = [p for p in players if p is not player]
            cost = (base - waivers.team_value(without, slots, weeks, first_week)) / week_count
            spares.append({"player": player, "cost_per_week": round(cost, 2)})
        spares.sort(key=lambda s: (s["cost_per_week"], -waivers.per_game_value(s["player"])))

        profiles[position] = {
            "position": position,
            "need_per_week": round(need, 2),
            "raw_need_per_week": round(raw_need, 2),
            "free_fix_per_week": round(free_fix, 2),
            "replacement": spare_man,
            "bar": bar.get(position, 0.0),
            "spares": spares,
            "count": sum(1 for p in players if p.get("position") == position),
        }
    return profiles


def holes(team_profile, waiver_aware=True):
    """
    Positions this team is leaking points at, worst first.

    `waiver_aware` picks which of the two prices to read. Use the default
    when deciding what *I* should chase: a hole the wire can fill is not
    worth paying a player for. Use False when judging what the OTHER manager
    will bite on -- he sees the hole in his lineup, not the discount, and in
    any case his lineup really does improve. Getting this backwards is how
    the board ends up either hunting free quarterbacks or refusing to offer
    anyone anything.
    """
    key = "need_per_week" if waiver_aware else "raw_need_per_week"
    return sorted(
        (entry for entry in team_profile.values() if entry.get(key, 0.0) >= NEED_BAR),
        key=lambda entry: entry.get(key, 0.0),
        reverse=True,
    )


def spare_players(team_profile, position=None):
    """
    Real players this team could lose for almost nothing.

    "Real" matters: every team can spare its worst kicker, but nobody trades
    for him. Only players who would start somewhere are listed.
    """
    entries = team_profile.values() if position is None else [team_profile[position]]
    found = []
    for entry in entries:
        if entry["position"] in STREAMED_POSITIONS:
            continue
        real = [
            spare for spare in entry["spares"]
            if spare["cost_per_week"] <= MAX_SPARE_COST
            and waivers.per_game_value(spare["player"]) >= trades.TRADEABLE_POINTS
        ]
        if not real:
            continue
        # On a team of three interchangeable receivers, losing ANY of them
        # costs little, because the next one slides up -- so the raw cost
        # would happily call the nominal WR1 spare. But between two players
        # who fill the same hole for the other team, offering the one that
        # costs me more is strictly worse. Only the cheapest at the position,
        # and anyone within a point a week of him, are pieces worth offering;
        # a better name in that band is still worth keeping, because it is
        # easier to sell.
        cheapest = real[0]["cost_per_week"]
        for spare in real:
            if spare["cost_per_week"] <= cheapest + SPARE_BAR:
                found.append({**spare, "position": entry["position"]})
    found.sort(key=lambda s: (-waivers.per_game_value(s["player"]), s["cost_per_week"]))
    return found


# ---------------------------------------------------------------------------
# Where two teams fit
# ---------------------------------------------------------------------------

def giving_players(team_profile, position):
    """Every player a team has at one position, spare or not."""
    entry = team_profile.get(position)
    if not entry or position in STREAMED_POSITIONS:
        return []
    return [spare["player"] for spare in entry["spares"]]


def overlap(mine, theirs):
    """
    The two halves of a trade that would make sense with one opponent.

    `they_fill` -- positions I am leaking points at where they have a player
    to spare. `i_fill` -- the same in the other direction. A trade needs
    both halves to be worth sending; one half alone is a request, not an
    offer.
    """
    def crossing(wanting, giving, waiver_aware):
        """
        Holes on one side that the other side has anybody to fill.

        The spares are listed because they are the cheap way in and the
        thing to ask for first, but a hole still counts when the other team
        has only players it would miss -- at a scarce position that is the
        normal case, and refusing to look there is how the board ends up
        recommending nothing but quarterbacks.
        """
        found = []
        for hole in holes(wanting, waiver_aware):
            need = hole["need_per_week"] if waiver_aware else hole["raw_need_per_week"]
            at_position = [
                p for p in giving_players(giving, hole["position"])
                if waivers.per_game_value(p) >= trades.TRADEABLE_POINTS
            ]
            if not at_position:
                continue
            found.append({
                "position": hole["position"],
                "need_per_week": round(need, 2),
                "spares": [
                    spare for spare in spare_players(giving, hole["position"])
                    if spare["cost_per_week"] < need
                ],
            })
        return found

    # What I chase is priced after waivers; what they will take is priced the
    # way they see it. See `holes`.
    they_fill = crossing(mine, theirs, True)
    i_fill = crossing(theirs, mine, False)
    return {
        "they_fill": they_fill,
        "i_fill": i_fill,
        # How promising this partner is before any trade is valued: the
        # points each side is leaking where the other has depth to spare.
        "fit": round(
            sum(h["need_per_week"] for h in they_fill)
            + sum(h["need_per_week"] for h in i_fill),
            2,
        ),
        "mutual": bool(they_fill and i_fill),
    }


# ---------------------------------------------------------------------------
# How the offer reads to the other manager
# ---------------------------------------------------------------------------

def perception(result, their_profile):
    """
    What the other manager sees, which is not what the lineup maths sees.

    He compares points per game, and he knows his own roster holes. So an
    offer is an easy yes when he gets at least as many raw points as he
    gives AND the players land on a position he is short at; it needs a
    pitch when the lineup gain is real but the raw points are against him;
    and it is a hard sell when neither is true, however good the maths says
    it is for him.
    """
    give_points, get_points = trades.on_paper(result)
    paper_for_them = round(give_points - get_points, 1)

    fills = [
        {
            "position": player["position"],
            "player": player,
            "need_per_week": their_profile[player["position"]]["raw_need_per_week"],
        }
        for player in result["give"]
        if player.get("position") in their_profile
        and their_profile[player["position"]]["raw_need_per_week"] >= NEED_BAR
    ]
    # One hole per position, filled by the best player going there. Sending
    # two receivers does not fill a 6-point receiver hole twice -- the second
    # one is depth, and saying otherwise oversells the offer to myself.
    fills.sort(key=lambda f: (f["need_per_week"], waivers.per_game_value(f["player"])),
               reverse=True)
    seen_positions, unique = set(), []
    for fill in fills:
        if fill["position"] in seen_positions:
            continue
        seen_positions.add(fill["position"])
        unique.append(fill)
    fills = unique

    if paper_for_them >= -PAPER_GAP and fills:
        reads = "easy yes"
    elif fills:
        reads = "needs a pitch"
    elif paper_for_them >= PAPER_GAP:
        reads = "easy yes"
    else:
        reads = "hard sell"

    return {
        "paper_for_them": paper_for_them,
        "paper_given": give_points,
        "paper_received": get_points,
        "fills": fills,
        "reads": reads,
        "pitch": pitch(result, fills, paper_for_them),
    }


def pitch(result, fills, paper_for_them):
    """The sentence to actually send him. Facts he can check, nothing else."""
    if fills:
        top = fills[0]
        line = (
            f"{top['player']['name']} starts for you at {top['position']} straight away"
            f" -- you are leaving about {top['need_per_week']:.1f} pts/week there."
        )
    else:
        line = "This is depth for depth; it helps you more in the lineup than on paper."
    if paper_for_them >= PAPER_GAP:
        line += f" You also come out {paper_for_them:.1f} pts/week ahead on raw scoring."
    elif paper_for_them <= -PAPER_GAP:
        line += (
            f" On raw scoring you give up {abs(paper_for_them):.1f} pts/week, so lead with"
            " the lineup, not the names."
        )
    return line


# ---------------------------------------------------------------------------
# The whole league, and the ideas that come out of it
# ---------------------------------------------------------------------------

def build(board, free_agents=None, progress=None):
    """
    Needs and spares for every team on an already-built trade board.

    `free_agents` is the waiver pool. Without it every hole is priced as if
    nothing were available for free, which overstates the shallow positions
    and badly overstates quarterback -- so pass it whenever you have it.
    """
    bar = starter_bar(board["rosters"], board["slots"])
    replacement = replacement_level(free_agents, board["slots"])
    profiles = {}
    for team_id, entry in board["rosters"].items():
        if progress:
            progress(entry["team"].team_name)
        profiles[team_id] = profile(
            entry["players"], board["slots"], board["weeks"], board["first_week"], bar,
            board["roster_limit"], replacement,
        )
    return {"bar": bar, "profiles": profiles, "replacement": replacement}


def partners(board, league_needs):
    """Opponents ranked by how well their roster fits mine, best first."""
    mine = league_needs["profiles"][board["team_id"]]
    found = []
    for team_id, entry in board["rosters"].items():
        if team_id == board["team_id"]:
            continue
        match = overlap(mine, league_needs["profiles"][team_id])
        found.append({**match, "team_id": team_id, "team": entry["team"]})
    found.sort(key=lambda m: (m["mutual"], m["fit"]), reverse=True)
    return found


def ideas_with(board, league_needs, match):
    """
    Trades with one opponent, built only from the players the needs board
    says are in play: I ask for their spares at positions I am short of, and
    I offer my spares at positions they are short of.

    Narrowing the search this way is not just speed. An idea built out of
    both teams' spare parts is the one that gets accepted, because neither
    manager is being asked to give up somebody he starts.
    """
    if not match["mutual"]:
        return []

    mine = board["rosters"][board["team_id"]]["players"]
    theirs = board["rosters"][match["team_id"]]["players"]

    # Narrow by POSITION, not by who is spare. Asking only for players the
    # other team can spare works at deep positions and fails exactly where
    # it matters most: nobody has a spare running back, because there are no
    # spare running backs -- which is the whole reason the position is worth
    # trading for. A scarce position has to be PAID for, out of the depth I
    # can spare, and `trades.evaluate` still refuses anything that does not
    # improve both lineups.
    want_positions = {hole["position"] for hole in match["they_fill"]}
    offer_positions = {hole["position"] for hole in match["i_fill"]}
    wanted = [p for p in theirs if p.get("position") in want_positions]
    offered = [p for p in mine if p.get("position") in offer_positions]
    if not wanted or not offered:
        return []

    found = trades.ideas_with(
        mine, theirs, board["roster_limit"], board["slots"],
        board["weeks"], board["first_week"],
        my_pieces=offered, their_pieces=wanted,
    )
    their_profile = league_needs["profiles"][match["team_id"]]
    for idea in found:
        idea["partner"] = match["team"]
        idea["perception"] = perception(idea, their_profile)
        idea["fills_for_me"] = [
            {
                "position": player["position"],
                "player": player,
                "need_per_week": league_needs["profiles"][board["team_id"]][player["position"]][
                    "need_per_week"
                ],
            }
            for player in idea["get"]
            if player.get("position") in league_needs["profiles"][board["team_id"]]
        ]
    return found


def worth_trading_for(idea, my_profile):
    """
    Is any part of what I receive something waivers could not hand me free?

    A trade whose whole gain sits at a position the wire can refill is not a
    good trade, however well it scores -- the honest comparison is not
    "my lineup before vs after" but "this trade vs simply claiming the free
    man", and the free man costs no player. Positions nobody trades (kicker,
    defence) never justify a trade on their own.
    """
    for player in idea["get"]:
        entry = my_profile.get(player.get("position"))
        if entry is None:
            return True
        if player["position"] in STREAMED_POSITIONS:
            continue
        if entry["need_per_week"] >= NEED_BAR:
            return True
    return False


def only_buys_what_waivers_give(idea, my_profile):
    """The reason an idea was set aside, in words, for the page and the CLI."""
    spots = sorted({p["position"] for p in idea["get"]} - STREAMED_POSITIONS)
    free = [
        (my_profile[spot].get("replacement") or {}).get("name")
        for spot in spots
        if spot in my_profile and (my_profile[spot].get("replacement") or {}).get("name")
    ]
    where = " and ".join(spots) or "that spot"
    who = f" ({', '.join(free)} is free)" if free else ""
    return f"Only helps at {where}, which the waiver wire can fix for nothing{who}."


def find_ideas(board, league_needs, progress=None):
    """Needs-matched trade ideas across the league, best for me first."""
    ideas = []
    for match in partners(board, league_needs):
        if progress:
            progress(match["team"].team_name)
        found = ideas_with(board, league_needs, match)
        ideas.extend(found[:IDEAS_PER_OPPONENT])
    ideas.sort(key=lambda r: (r["my_gain"], r["their_gain"]), reverse=True)
    return ideas[:IDEAS_TOTAL]
