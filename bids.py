"""
What waiver claims actually cost in each of your leagues.

The bid in `waivers.suggest_bid` is a rule of thumb: a share of your budget,
bigger when the pickup helps more. Rules of thumb ignore the one thing that
decides a FAAB auction -- what the other eleven managers in THIS league are
willing to pay. Some leagues hand over $30 for a backup running back; others
let the same player go for $1. Overbidding in a cheap league wastes budget
you will want in November; underbidding in an aggressive one loses the
player.

ESPN keeps every processed claim with its bid, so this reads them all and
learns the league's prices:

  * the typical winning bid, and the price that wins three claims in four,
    for claims that were actually contested (above the minimum bid), and
  * each manager's appetite: how many claims, how much spent, largest bid.

Then it adjusts the rule of thumb in two directions, and only once there is
enough history to trust (MIN_CONTESTED claims):

  * a pickup that clearly matters (3+ pts a week) is bid at least at the
    price that wins three claims in four here, so a cheap rule of thumb does
    not lose a player the league clearly values;
  * a marginal pickup is capped near what claims usually go for here, so a
    big rule-of-thumb bid is not wasted in a league that pays $1.

Until then the rule of thumb stands, and the report says how many claims the
league has made so far.
"""

import statistics


# Claims above the minimum bid needed before the league's prices are trusted.
MIN_CONTESTED = 5

# Pickups worth this many points a week or more are bid at least at the
# league's "wins three in four" price.
IMPORTANT_GAIN = 3.0

# Marginal pickups are capped at this multiple of the league's typical
# winning bid.
MARGINAL_CAP = 1.25


def fetch_claims(league):
    """
    Every waiver claim ESPN will show for this league, oldest first.

    ESPN files transactions by scoring period, so each week is read in turn.
    Claims that lost are included when ESPN exposes them (their status starts
    with FAILED), which is what reveals how many managers wanted a player.
    """
    names = getattr(league, "player_map", {}) or {}
    seen, claims = set(), []
    for week in range(1, league.current_week + 1):
        try:
            data = league.espn_request.league_get(
                params={"view": "mTransactions2", "scoringPeriodId": week}
            )
        except Exception:
            continue
        for transaction in data.get("transactions") or []:
            if transaction.get("type") != "WAIVER" or transaction.get("id") in seen:
                continue
            seen.add(transaction.get("id"))
            status = transaction.get("status") or ""
            added = next(
                (i for i in transaction.get("items") or [] if i.get("type") == "ADD"), None
            )
            if not added or not (status == "EXECUTED" or status.startswith("FAILED")):
                continue
            claims.append({
                "player_id": added.get("playerId"),
                "player": names.get(added.get("playerId"), str(added.get("playerId"))),
                "team_id": transaction.get("teamId"),
                "bid": transaction.get("bidAmount") or 0,
                "won": status == "EXECUTED",
                "week": transaction.get("scoringPeriodId") or week,
                "processed": transaction.get("processDate") or transaction.get("proposedDate") or 0,
            })
    claims.sort(key=lambda c: c["processed"])
    return claims


def percentile(values, share):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return ordered[index]


def summarise(claims, budget, minimum_bid, teams=None):
    """The league's prices and each manager's appetite. Pure, for testing."""
    won = [c for c in claims if c["won"]]
    contested = [c for c in won if c["bid"] > minimum_bid]
    rivals = {}
    for claim in claims:
        for other in claims:
            if (other is not claim and other["player_id"] == claim["player_id"]
                    and other["processed"] == claim["processed"]):
                rivals[id(claim)] = rivals.get(id(claim), 0) + 1

    managers = {}
    for claim in won:
        entry = managers.setdefault(claim["team_id"], {"claims": 0, "spent": 0, "largest": 0})
        entry["claims"] += 1
        entry["spent"] += claim["bid"]
        entry["largest"] = max(entry["largest"], claim["bid"])
    if teams:
        for team_id, entry in managers.items():
            entry["team"] = teams.get(team_id, str(team_id))

    bids = [c["bid"] for c in contested]
    return {
        "claims": len(won),
        "contested": len(contested),
        "trusted": len(contested) >= MIN_CONTESTED,
        "median_bid": statistics.median(bids) if bids else None,
        "winning_bid_75": percentile(bids, 0.75),
        "largest_bid": max((c["bid"] for c in won), default=None),
        "budget": budget,
        "managers": sorted(managers.values(), key=lambda m: m["spent"], reverse=True),
        "recent": [
            {**c, "rivals": rivals.get(id(c), 0)} for c in sorted(won, key=lambda c: -c["processed"])[:8]
        ],
    }


def adjust(bid, gain_per_week, budget_left, minimum_bid, market):
    """
    Moves a rule-of-thumb bid toward what this league actually pays.
    Returns (bid, a sentence explaining any change or None).
    """
    if not market or not market["trusted"] or budget_left <= 0:
        return bid, None

    if gain_per_week >= IMPORTANT_GAIN and market["winning_bid_75"]:
        floor = min(budget_left, int(market["winning_bid_75"]))
        if floor > bid:
            return floor, (
                f"raised to ${floor}: in this league ${market['winning_bid_75']:.0f} "
                f"wins three contested claims in four"
            )
    elif gain_per_week < IMPORTANT_GAIN and market["median_bid"]:
        cap = max(minimum_bid, int(round(market["median_bid"] * MARGINAL_CAP)))
        if bid > cap:
            return cap, (
                f"lowered to ${cap}: contested claims here usually go for "
                f"${market['median_bid']:.0f}"
            )
    return bid, None


def describe(market):
    """One line for the report header."""
    if not market or not market["claims"]:
        return "No waiver claims processed in this league yet -- bids use the rule of thumb."
    if not market["trusted"]:
        return (
            f"{market['claims']} claim(s) so far, {market['contested']} above the minimum -- "
            f"too few to learn prices from (need {MIN_CONTESTED}); bids use the rule of thumb."
        )
    return (
        f"Winning bids here: typically ${market['median_bid']:.0f}, "
        f"${market['winning_bid_75']:.0f} wins three in four, largest ${market['largest_bid']} "
        f"({market['contested']} contested claims)."
    )


def history(league, budget, minimum_bid):
    teams = {t.team_id: t.team_name for t in league.teams}
    return summarise(fetch_claims(league), budget, minimum_bid, teams)
