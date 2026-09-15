"""
The in-season app: team check-up, start/sit, waivers and trades in one page.

    .venv/bin/python app.py

Opens in your browser, and prints a second address for your phone -- any
phone on the same Wi-Fi can open it. Leave the window running.

How it stays fast: working out a league takes a minute or two (it runs every
engine: lineup, waivers, under-the-radar, trades), so it is done in the
background, one league at a time, and saved. The page shows the saved copy
straight away, says how old it is, and has a Refresh button. Saved copies
live in cache/ and survive restarts.

Nothing here can change anything on ESPN -- there is no write API. Every
move it suggests, you make in the ESPN app.

About the phone address: anyone on your Wi-Fi who knows it can see your
teams and rosters (never your ESPN login -- that stays on this computer).
On a home network that is fine; on a coffee-shop network, run it with
APP_LOCAL_ONLY=1 to keep it to this computer.
"""

import json
import os
import socket
import threading
import time
import warnings
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

warnings.filterwarnings("ignore")

import bids
import coach
import leagues
import consistency
import lineup
import matchup
import status
import trades
import usage
import waiver_wire
import waivers
from app_page import PAGE_HTML


PORT = int(os.getenv("APP_PORT", "8780"))
LOCAL_ONLY = os.getenv("APP_LOCAL_ONLY") == "1"
CACHE_DIR = "cache"

# How many rows of each list travel to the page. Phones do not need 150
# free agents; they need the ones worth acting on.
CLAIMS_SHOWN = 15
GEMS_SHOWN = 10


# ---------------------------------------------------------------------------
# Turning engine output into plain data for the page
# ---------------------------------------------------------------------------

def player_view(p):
    """The fields the page shows for any player, whatever list he is in."""
    status_text = p.get("injury_status") or "ACTIVE"
    return {
        "id": p.get("player_id"),
        "name": p.get("name"),
        "position": p.get("position"),
        "team": p.get("pro_team") or p.get("team"),
        "injury": None if status_text in {"ACTIVE", "NORMAL"} else status_text.replace("_", " ").title(),
        "normal_week": round(waivers.per_game_value(p), 1) if "season_projected_avg" in p else None,
        "this_week": round(p["score"], 1) if p.get("score") is not None else None,
        "owned": round(p.get("percent_owned") or 0),
        "opponent": p.get("opponent"),
        "usage": usage.describe(p.get("usage")),
        "ros_rank": p.get("ros_pos_rank"),
        "matchup": p.get("matchup"),
        "matchup_quality": p.get("matchup_quality"),
        "playoffs": p.get("playoffs"),
        "playoff_bye": bool(p.get("playoff_bye")),
    }


def start_sit_view(board, head_to_head=None):
    if not board:
        return None

    def row(p, slot=None):
        view = player_view(p)
        view.update(
            slot=slot,
            espn=p.get("espn_projection"),
            experts=p.get("weekly_projection"),
            locks_in=p.get("locks_in"),
            locked=bool(p.get("locked")),
            reasons=lineup.reasons(p),
            practice=status.describe_practice(p),
            note=p.get("note_headline"),
            consistency=consistency.describe(p.get("consistency")),
        )
        return view

    order = sorted(board["assigned"], key=lambda s: len(lineup.SLOT_ELIGIBILITY[s]))
    gain = round(board["recommended_total"] - board["current_total"], 1)
    return {
        "week": board["week"],
        "lineup": [row(p, slot) for slot in order for p in board["assigned"][slot]],
        "bench": [row(p) for p in sorted(board["bench"], key=lambda p: p["score"], reverse=True)],
        "changes": [{"out": row(o), "in": row(i)} for o, i in board["changes"]],
        "recommended_total": board["recommended_total"],
        "current_total": board["current_total"],
        "gain": gain,
        "worth_changing": gain >= 0.5,
        "experts_loaded": bool(board["expert_summary"]),
        "matchup": None if not head_to_head else {
            "opponent": head_to_head["opponent"],
            "mine": head_to_head["my_projected"],
            "theirs": head_to_head["their_projected"],
            "chance": round(matchup.rounded(head_to_head["win_probability"]) * 100),
            "situation": head_to_head["situation"],
            "tiebreaks": [
                {"start": t["start"]["name"], "over": t["over"]["name"], "slot": t["slot"], "reason": t["reason"]}
                for t in head_to_head["tiebreaks"]
            ],
        },
    }


def waivers_view(report, gems):
    by_id = {s["add"].get("player_id"): s for s in report["swaps"]}

    def claim(swap):
        return {
            "add": player_view(swap["add"]),
            "drop": player_view(swap["drop"]) if swap["drop"] else None,
            "bid": swap["bid"],
            "gain_per_week": swap["gain_per_week"],
            "reasons": waiver_wire.reasons(swap, report),
        }

    worth = [s for s in report["swaps"] if s["gain_per_week"] >= waivers.WORTH_A_CLAIM]
    gem_rows = []
    for gem in gems[:GEMS_SHOWN]:
        swap = by_id.get(gem["player_id"])
        view = player_view(gem)
        view.update(
            upside=gem["upside"],
            reasons=gem["upside_reasons"],
            note=gem.get("note"),
            note_date=(gem.get("note_date") or "")[:10] or None,
            claim=claim(swap) if swap and swap["gain_per_week"] >= waivers.WORTH_A_CLAIM else None,
        )
        gem_rows.append(view)

    settings = report["settings"]
    return {
        "schedule": waiver_wire.describe_schedule(settings),
        "budget_left": report["budget_left"],
        "minimum_bid": settings["minimum_bid"],
        "richest": report["opponents"][:3],
        "market": bids.describe(report.get("market")),
        "big_spenders": [m for m in (report.get("market") or {}).get("managers", [])][:4],
        "gems": gem_rows,
        "claims": [claim(s) for s in worth[:CLAIMS_SHOWN]],
        "weeks": [report["weeks"][0], report["weeks"][-1]] if report["weeks"] else None,
    }


def trade_view(result):
    give_points, get_points = trades.on_paper(result)
    return {
        "partner": result["partner"].team_name if hasattr(result["partner"], "team_name") else result["partner"],
        "partner_id": result["partner"].team_id if hasattr(result["partner"], "team_id") else result.get("partner_id"),
        "give": [player_view(p) for p in result["give"]],
        "get": [player_view(p) for p in result["get"]],
        "my_gain_per_week": result["my_gain_per_week"],
        "their_gain_per_week": result["their_gain_per_week"],
        "i_cut": [p["name"] for p in result["i_cut"]],
        "they_cut": [p["name"] for p in result["they_cut"]],
        "paper_give": give_points,
        "paper_get": get_points,
    }


def home_view(report):
    """Strengths and weaknesses, each with the moves that act on it."""
    def claim_ref(swap):
        return {
            "kind": "waiver",
            "id": swap["add"].get("player_id"),
            "title": f"Add {swap['add']['name']} ({swap['add']['position']})",
            "detail": (f"drop {swap['drop']['name']}, " if swap["drop"] else "")
                      + f"bid ${swap['bid']} · +{swap['gain_per_week']:.1f} pts/wk",
        }

    def gem_ref(gem):
        return {
            "kind": "gem",
            "id": gem["player_id"],
            "title": f"Stash {gem['name']} ({gem['position']}, {gem['team']})",
            "detail": gem["upside_reasons"][0] if gem["upside_reasons"] else "",
        }

    def trade_ref(trade, index):
        return {
            "kind": "trade",
            "id": index,
            "title": "Get " + " + ".join(p["name"] for p in trade["get"]),
            "detail": "for " + " + ".join(p["name"] for p in trade["give"])
                      + f" · {trade['partner'].team_name} · +{trade['my_gain_per_week']:.1f} pts/wk",
        }

    trade_index = {id(t): n for n, t in enumerate(report["trade_ideas"])}
    weaknesses = [
        {
            "position": fix["gap"],
            "moves": [claim_ref(s) for s in fix["waivers"]]
                     + [gem_ref(g) for g in fix["gems"]]
                     + [trade_ref(t, trade_index[id(t)]) for t in fix["trades"]],
        }
        for fix in report["fixes"]
    ]
    strengths = [
        {
            "position": entry["strength"],
            "moves": [trade_ref(t, trade_index[id(t)]) for t in entry["trades"]],
        }
        for entry in report["strengths"]
    ]
    return {
        "season": report["season"],
        "positions": sorted(report["gaps"], key=lambda r: r["difference"], reverse=True),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "moves": report["moves"],
    }


def roster_for_checker(board):
    """
    Every team's roster -- for the trade checker's lists and for the roster
    page you reach by tapping a team's name on a trade.
    """
    def row(p):
        view = player_view(p)
        slot = p.get("current_slot") or ""
        view["slot"] = slot
        view["starting"] = slot not in lineup.BENCH_SLOTS and slot != ""
        view["on_ir"] = slot == "IR"
        return view

    teams = []
    for team_id, entry in board["rosters"].items():
        team = entry["team"]
        teams.append({
            "team_id": team_id,
            "name": team.team_name,
            "mine": team_id == board["team_id"],
            "record": f"{team.wins}-{team.losses}" + (f"-{team.ties}" if getattr(team, "ties", 0) else ""),
            "standing": getattr(team, "standing", None),
            "players": sorted([row(p) for p in entry["players"]], key=lambda p: -(p["normal_week"] or 0)),
        })
    return teams


def private_board(board):
    """
    What the trade checker needs to value a trade later without asking ESPN
    again: every rostered player's valuation fields, plus the league's shape.
    Kept server-side; never sent to the page.
    """
    keep = ("player_id", "name", "position", "pro_team", "injury_status", "current_slot",
            "bye_week", "season_projected_avg", "season_actual_avg", "games_played",
            "score", "percent_owned", "usage", "ros_expert_avg")
    return {
        "team_id": board["team_id"],
        "slots": board["slots"],
        "weeks": board["weeks"],
        "first_week": board["first_week"],
        "roster_limit": board["roster_limit"],
        "teams": {
            str(team_id): {
                "name": entry["team"].team_name,
                "players": [{k: p.get(k) for k in keep} for p in entry["players"]],
            }
            for team_id, entry in board["rosters"].items()
        },
    }


def page_payload(report):
    board = report["trade_board"]
    return {
        "league_name": report["league_name"],
        "week": report["first_week"],
        "home": home_view(report),
        "start_sit": start_sit_view(report["start_sit"], report.get("matchup")),
        "waivers": waivers_view(report["waivers"], report["gems"]),
        "trades": {
            "deadline": board["settings"]["deadline"],
            "veto_votes": board["settings"]["veto_votes"],
            "ideas": [trade_view(t) for t in report["trade_ideas"]],
            "teams": roster_for_checker(board),
        },
    }


# ---------------------------------------------------------------------------
# Keeping every league's data fresh
# ---------------------------------------------------------------------------

class AppState:
    def __init__(self, creds):
        self.creds = creds
        self.lock = threading.Lock()
        self.work = threading.Condition(self.lock)
        self.queue = []
        self.leagues = [L for L in leagues.available_leagues(creds) if L.get("team_id")]
        self.data = {}      # league_id -> {"payload", "private", "updated"}
        self.status = {}    # league_id -> text shown while working
        for entry in self.leagues:
            saved = self.load(entry["league_id"])
            if saved:
                self.data[entry["league_id"]] = saved

    def cache_file(self, league_id):
        return os.path.join(CACHE_DIR, f"app_{league_id}.json")

    def load(self, league_id):
        try:
            with open(self.cache_file(league_id)) as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def save(self, league_id, entry):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(self.cache_file(league_id), "w") as handle:
            json.dump(entry, handle, default=str)

    def request_refresh(self, league_id=None):
        with self.work:
            targets = [league_id] if league_id else [L["league_id"] for L in self.leagues]
            for target in targets:
                if target not in self.queue:
                    self.queue.append(target)
                    self.status[target] = "queued"
            self.work.notify()

    def worker(self):
        """
        One league at a time, never in parallel: the ESPN library shares
        scoring settings between connections, so two leagues built at once
        could quietly swap scoring formats. See CLAUDE.md.
        """
        while True:
            with self.work:
                while not self.queue:
                    self.work.wait()
                league_id = self.queue[0]
            entry = next(L for L in self.leagues if L["league_id"] == league_id)
            try:
                self.status[league_id] = "reading ESPN"
                league = leagues.connect(league_id, self.creds)
                report = coach.build(
                    league, entry["team_id"], self.creds["season"],
                    progress=lambda step: self.status.__setitem__(league_id, f"working: {step}"),
                )
                # Round-trip through JSON so kickoff times and other oddities
                # become plain text once, here, rather than at every request.
                result = json.loads(json.dumps({
                    "payload": page_payload(report),
                    "private": private_board(report["trade_board"]),
                    "updated": time.time(),
                }, default=str))
                with self.lock:
                    self.data[league_id] = result
                self.save(league_id, result)
                self.status[league_id] = None
            except Exception as error:
                self.status[league_id] = f"failed: {error}"
            finally:
                with self.work:
                    self.queue.remove(league_id)

    def overview(self):
        with self.lock:
            return [
                {
                    "league_id": L["league_id"],
                    "name": L["name"],
                    "updated": (self.data.get(L["league_id"]) or {}).get("updated"),
                    "status": self.status.get(L["league_id"]),
                }
                for L in self.leagues
            ]

    def league(self, league_id):
        with self.lock:
            entry = self.data.get(league_id)
            return entry["payload"] if entry else None

    def check_trade(self, league_id, give_ids, get_ids):
        with self.lock:
            entry = self.data.get(league_id)
        if not entry:
            return {"error": "This league has not loaded yet."}
        board = entry["private"]
        teams = board["teams"]
        mine = teams[str(board["team_id"])]["players"]

        give = [p for p in mine if p["player_id"] in give_ids]
        partner_id = next(
            (tid for tid, t in teams.items() if tid != str(board["team_id"])
             and any(p["player_id"] in get_ids for p in t["players"])),
            None,
        )
        if not give or partner_id is None:
            return {"error": "Pick at least one player to give and one to get."}
        theirs = teams[partner_id]["players"]
        get = [p for p in theirs if p["player_id"] in get_ids]

        result = trades.evaluate(
            mine, theirs, give, get, board["roster_limit"], board["slots"],
            board["weeks"], board["first_week"],
        )
        result["partner"] = teams[partner_id]["name"]
        result["partner_id"] = int(partner_id)
        return trade_view(result)


# ---------------------------------------------------------------------------
# The web server
# ---------------------------------------------------------------------------

def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, payload, content_type="application/json", code=200):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(PAGE_HTML.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/leagues":
                self._send(state.overview())
            elif self.path.startswith("/api/league/"):
                try:
                    league_id = int(self.path.rsplit("/", 1)[1])
                except ValueError:
                    return self.send_error(404)
                payload = state.league(league_id)
                self._send(payload if payload else {"loading": True})
            else:
                self.send_error(404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self.send_error(400)

            if self.path == "/api/refresh":
                state.request_refresh(data.get("league_id"))
                self._send(state.overview())
            elif self.path == "/api/trade-check":
                self._send(state.check_trade(
                    int(data.get("league_id") or 0),
                    set(data.get("give") or []),
                    set(data.get("get") or []),
                ))
            else:
                self.send_error(404)

    return Handler


def phone_address():
    """This computer's address on the Wi-Fi, for opening the app on a phone."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            return probe.getsockname()[0]
    except OSError:
        return None


def main():
    creds = leagues.load_credentials()
    print("Finding your leagues...")
    state = AppState(creds)
    if not state.leagues:
        raise SystemExit("Could not find any ESPN leagues -- check ESPN_S2 and ESPN_SWID in .env.")

    threading.Thread(target=state.worker, daemon=True).start()
    state.request_refresh()

    host = "127.0.0.1" if LOCAL_ONLY else "0.0.0.0"
    server = ThreadingHTTPServer((host, PORT), make_handler(state))
    url = f"http://127.0.0.1:{PORT}/"

    print(f"\nFantasy assistant is running: {url}")
    address = phone_address()
    if address and not LOCAL_ONLY:
        print(f"On your phone (same Wi-Fi):   http://{address}:{PORT}/")
    print("\nFresh numbers for every league are being worked out in the background")
    print("(a minute or two each). Leave this window open; Control-C to stop.\n")

    if os.getenv("APP_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
