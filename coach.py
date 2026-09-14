"""
The state of your team, and where to focus.

Every other tool here answers one narrow question: who to start, who to
claim, what to trade. This one steps back and asks the questions that come
first:

  1. HOW DID I DO? Last week's result, how you scored against the whole
     league, and how many points you left on your bench -- the one mistake
     that is entirely yours. Then the season so far: record, points scored,
     where you sit in the standings.
  2. WHERE AM I WEAK? Each lineup position compared with the rest of the
     league, using the same normal-week values as waivers and trades. Being
     last in the league at tight end matters more than being fifth at
     running back, and this puts a number on it.
  3. WHAT WOULD HELP MOST? The best move of each kind -- a lineup change, a
     waiver claim, a trade -- all measured in the same unit, points per week,
     so they can be ranked against each other. Then, for your weakest
     positions, the specific options of every kind that fix them.

It adds no new maths of its own. Every number comes from the engines the
other tools already use (lineup, waivers, upside, trades), so a suggestion
here always matches what those tools say in detail.
"""

import statistics

import lineup
import trades
import upside
import waivers


# Lineup slots are grouped into positions for the gap comparison. Flex slots
# get their own group: a weak flex is a depth problem, not a position one.
POSITION_GROUPS = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "FLEX": {"RB/WR", "WR/TE", "RB/WR/TE", "OP"},
    "K": {"K"},
    "D/ST": {"D/ST"},
}

# Which player positions can fix a gap in each group.
FIXED_BY = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"}, "K": {"K"}, "D/ST": {"D/ST"},
}

# A position is only called a gap when it is clearly behind the league.
GAP_POINTS = 1.0


# ---------------------------------------------------------------------------
# 1. How did I do?
# ---------------------------------------------------------------------------

def week_result(league, team_id, week, slots, final=True):
    """
    One week, from your side: both scores, the league-wide ranking of your
    score, and the points left on your bench.
    """
    boxes = league.box_scores(week)
    all_scores, mine = [], None
    for box in boxes:
        for side, other in (("home", "away"), ("away", "home")):
            team = getattr(box, f"{side}_team", None)
            if not team or isinstance(team, int):
                continue
            score = getattr(box, f"{side}_score") or 0.0
            all_scores.append(score)
            if team.team_id == team_id:
                opponent = getattr(box, f"{other}_team", None)
                mine = {
                    "week": week,
                    "score": round(score, 2),
                    "projected": round(getattr(box, f"{side}_projected") or 0.0, 2),
                    "opponent": opponent.team_name if opponent and not isinstance(opponent, int) else "bye",
                    "opponent_score": round(getattr(box, f"{other}_score") or 0.0, 2),
                    "lineup": getattr(box, f"{side}_lineup") or [],
                }
    if mine is None:
        return None

    all_scores.sort(reverse=True)
    mine["league_rank"] = all_scores.index(mine["score"]) + 1 if mine["score"] in all_scores else None
    mine["team_count"] = len(all_scores)

    mine["final"] = final
    if not final:
        # A player who has not played yet shows 0 points, so judging the
        # lineup now would say "you should have benched him" about a man
        # whose game is tonight. The bench review waits for the final score.
        mine.update(best_possible=None, left_on_bench=0.0,
                    should_have_started=[], should_have_benched=[])
        del mine["lineup"]
        return mine

    # The best lineup you could have set, knowing what everyone scored.
    # Players in the IR slot could not have been started, so they are left out.
    played = [
        {"name": p.name, "position": p.position, "score": p.points or 0.0,
         "can_play": True, "slot": p.slot_position}
        for p in mine["lineup"]
        if p.slot_position != "IR"
    ]
    _, best_starters, _ = lineup.best_lineup(played, slots)
    best_total = lineup.lineup_total(best_starters)
    mine["best_possible"] = round(best_total, 2)
    mine["left_on_bench"] = round(max(0.0, best_total - mine["score"]), 2)

    started = {p["name"] for p in played if p["slot"] not in lineup.BENCH_SLOTS}
    should_have = {p["name"] for p in best_starters}
    mine["should_have_started"] = sorted(should_have - started)
    mine["should_have_benched"] = sorted(started - should_have)
    del mine["lineup"]
    return mine


def season_so_far(league, team_id, slots):
    """
    Every week played, plus the season totals built from them.

    Built from the box scores rather than ESPN's win-loss record, because
    ESPN only updates the record once a week is fully final -- on a Monday
    it still says 0-0 after a Sunday you lost.
    """
    weeks = []
    for week in range(1, league.current_week + 1):
        result = week_result(league, team_id, week, slots, final=week < league.current_week)
        if result:
            weeks.append(result)

    final = [w for w in weeks if w["final"]]
    wins = sum(1 for w in final if w["score"] > w["opponent_score"])
    losses = sum(1 for w in final if w["score"] < w["opponent_score"])
    ties = len(final) - wins - losses

    team = lineup.my_team(league, team_id)
    return {
        "weeks": weeks,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "points_for": round(sum(w["score"] for w in weeks), 2),
        "left_on_bench": round(sum(w["left_on_bench"] for w in weeks), 2),
        "standing": getattr(team, "standing", None),
        "playoff_chance": getattr(team, "playoff_pct", None),
        "playoff_spots": league.settings.playoff_team_count,
        "team_count": len(league.teams),
    }


# ---------------------------------------------------------------------------
# 2. Where am I weak?
# ---------------------------------------------------------------------------

def normal_week_lineup(players, slots):
    """A team's best lineup in a normal week, grouped by position."""
    weekly = [
        {"name": p["name"], "position": p["position"],
         "score": waivers.per_game_value(p), "can_play": True}
        for p in players
        if (p.get("injury_status") or "ACTIVE") not in {"INJURY_RESERVE", "SUSPENSION"}
    ]
    assigned, _, _ = lineup.best_lineup(weekly, slots)
    groups = {}
    for slot, group in assigned.items():
        name = next((g for g, members in POSITION_GROUPS.items() if slot in members), None)
        if name:
            groups.setdefault(name, []).extend(group)
    return groups


def position_gaps(trade_board):
    """
    Each position group: your starters' normal-week points against the
    league median, and your rank (1 = best in the league).
    """
    slots = trade_board["slots"]
    by_team = {
        team_id: normal_week_lineup(entry["players"], slots)
        for team_id, entry in trade_board["rosters"].items()
    }
    mine = by_team[trade_board["team_id"]]

    rows = []
    for group in POSITION_GROUPS:
        totals = [
            sum(p["score"] for p in lineup_groups.get(group, []))
            for lineup_groups in by_team.values()
        ]
        if not any(totals):
            continue
        my_total = sum(p["score"] for p in mine.get(group, []))
        median = statistics.median(totals)
        rank = sorted(totals, reverse=True).index(my_total) + 1
        rows.append({
            "group": group,
            "mine": round(my_total, 1),
            "median": round(median, 1),
            "difference": round(my_total - median, 1),
            "rank": rank,
            "team_count": len(totals),
            "starters": [p["name"] for p in mine.get(group, [])],
        })
    rows.sort(key=lambda r: r["difference"])
    return rows


# ---------------------------------------------------------------------------
# 3. What would help most?
# ---------------------------------------------------------------------------

def opportunities(start_sit_board, waiver_report, gems, trade_ideas, gaps):
    """
    The best move of each kind in one unit -- points per week -- ranked.

    A lineup change only counts for this week, while claims and trades pay
    every week. Both are shown in points per week, but the lineup change is
    labelled "this week only" so the two are not confused.
    """
    moves = []

    if start_sit_board and start_sit_board["changes"]:
        gain = round(start_sit_board["recommended_total"] - start_sit_board["current_total"], 1)
        if gain >= 0.5:
            moves.append({
                "kind": "LINEUP",
                "gain": gain,
                "when": "this week only",
                "summary": "; ".join(
                    f"start {i['name']} over {o['name']}" for o, i in start_sit_board["changes"]
                ),
            })

    claims = [s for s in waiver_report["swaps"] if s["gain_per_week"] >= waivers.WORTH_A_CLAIM]
    if claims:
        best = claims[0]
        drop = f", drop {best['drop']['name']}" if best["drop"] else ""
        moves.append({
            "kind": "WAIVER",
            "gain": best["gain_per_week"],
            "when": "every week",
            "summary": f"add {best['add']['name']} ({best['add']['position']}){drop}, bid ${best['bid']}",
        })

    if trade_ideas:
        best = trade_ideas[0]
        moves.append({
            "kind": "TRADE",
            "gain": best["my_gain_per_week"],
            "when": "every week",
            "summary": (
                f"give {' + '.join(p['name'] for p in best['give'])}, get "
                f"{' + '.join(p['name'] for p in best['get'])} ({best['partner'].team_name})"
            ),
        })

    if gems:
        top = gems[0]
        moves.append({
            "kind": "STASH",
            "gain": None,
            "when": "a bet, not yet in the numbers",
            "summary": f"{top['name']} ({top['position']}, {top['team']}) -- "
                       + (top["upside_reasons"][0] if top["upside_reasons"] else ""),
        })

    moves.sort(key=lambda m: -1 if m["gain"] is None else m["gain"], reverse=True)

    # For each real gap, every kind of fix for that position.
    fixes = []
    for gap in gaps:
        if gap["difference"] > -GAP_POINTS:
            continue
        positions = FIXED_BY[gap["group"]]
        fixes.append({
            "gap": gap,
            "waivers": [
                s for s in claims if s["add"]["position"] in positions
            ][:2],
            "gems": [g for g in gems if g["position"] in positions][:2],
            "trades": [
                t for t in trade_ideas
                if any(p["position"] in positions for p in t["get"])
            ][:2],
        })
    return moves, fixes


# ---------------------------------------------------------------------------
# Everything, for one league
# ---------------------------------------------------------------------------

def build(league, team_id, season, use_experts=True, force_refresh=False, progress=None):
    step = progress or (lambda _: None)
    slots = lineup.open_slots(league)

    step("results")
    season_view = season_so_far(league, team_id, slots)

    first_week = waivers.first_playable_week(league, season)

    step("lineup")
    try:
        start_sit_board = lineup.build(
            league, team_id, first_week, season,
            use_experts=use_experts, force_refresh=force_refresh,
        )
    except Exception:
        start_sit_board = None

    step("opponent")
    head_to_head = None
    if start_sit_board:
        try:
            import matchup
            head_to_head = matchup.build(
                league, team_id, first_week, season, start_sit_board,
                use_experts=use_experts, force_refresh=force_refresh,
            )
        except Exception:
            head_to_head = None

    step("waivers")
    waiver_report = waivers.build(
        league, team_id, season, week=first_week,
        use_experts=use_experts, force_refresh=force_refresh,
    )
    try:
        gems = upside.find(league, season, first_week)
    except Exception:
        gems = []

    step("trades")
    trade_board = trades.build(
        league, team_id, season, week=first_week,
        use_experts=use_experts, force_refresh=force_refresh,
    )
    trade_ideas = trades.find_ideas(trade_board)

    gaps = position_gaps(trade_board)
    moves, fixes = opportunities(start_sit_board, waiver_report, gems, trade_ideas, gaps)

    return {
        "league_name": league.settings.name,
        "first_week": first_week,
        "season": season_view,
        "gaps": gaps,
        "moves": moves,
        "fixes": fixes,
        "strengths": strengths(gaps, trade_ideas),
        # The detail behind every suggestion, for the tools and pages that
        # show it in full.
        "start_sit": start_sit_board,
        "matchup": head_to_head,
        "waivers": waiver_report,
        "gems": gems,
        "trade_board": trade_board,
        "trade_ideas": trade_ideas,
    }


def strengths(gaps, trade_ideas):
    """
    Positions clearly ahead of the league, with the trades that SELL from
    them. Depth you cannot start is only worth something once it is traded
    for a position you need.
    """
    out = []
    for row in sorted(gaps, key=lambda r: r["difference"], reverse=True):
        if row["difference"] < GAP_POINTS:
            continue
        positions = FIXED_BY[row["group"]]
        out.append({
            "strength": row,
            "trades": [
                t for t in trade_ideas
                if any(p["position"] in positions for p in t["give"])
            ][:2],
        })
    return out
