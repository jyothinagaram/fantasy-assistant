"""
Your live draft assistant.

Run this when your draft starts. It opens a page in your browser showing
who you should take next and why, updating as players come off the board.

    .venv/bin/python draft_assistant.py

How it keeps up with the draft:

  1. It tries to read picks straight from ESPN every few seconds. If that
     works, the board updates on its own and you do nothing.
  2. If ESPN does not publish picks live -- which we cannot verify until
     you are actually in a draft -- you click players off yourself. One
     click marks someone as taken, another marks him as YOURS.

Either way the recommendations are identical. The automatic sync is a
convenience, not something the tool depends on.

Nothing here can change anything in ESPN. It only reads. Every pick you
make still has to be made in the ESPN app.
"""

import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import advice
import leagues
import rankings
from page import PAGE_HTML


PORT = int(os.getenv("DRAFT_ASSISTANT_PORT", "8770"))
SYNC_SECONDS = 5

# How far down the board the page can see. It has to cover a whole draft --
# twelve teams times fourteen rounds is 168 players -- plus enough beyond
# that to search for somebody and to spot a value worth waiting on.
BOARD_DEPTH = 220

# How many of those carry their full write-up. Every article sentence and
# injury paragraph for 220 players is a megabyte of JSON, re-sent every two
# and a half seconds, and you only ever read the write-up for players you are
# actually choosing between. The rest travel light.
DETAIL_DEPTH = 40

# Dropped from the light rows. The short note stays -- it is one line and it
# is the bit worth seeing at a glance.
HEAVY_FIELDS = ("note_detail", "quotes", "articles", "facts")


def slim(player):
    """The same player, without the reading material."""
    return {k: v for k, v in player.items() if k not in HEAVY_FIELDS}


class DraftState:
    """
    Everything the tool knows about the draft in progress.

    The board is built once at startup and then held in memory -- during a
    draft you have about a minute per pick, so there is no time to re-download
    500 players every time somebody gets taken.
    """

    def __init__(self, league, league_info, creds):
        self.lock = threading.Lock()
        self.league = league
        self.league_info = league_info
        self.creds = creds

        board = rankings.build_board(league)
        self.board = board["players"]
        self.replacement = board["replacement"]
        self.plan = advice.roster_plan(league)

        self.by_id = {p["player_id"]: p for p in self.board}
        self.drafted = {}       # player_id -> "me" or "other"
        self.history = []       # player_ids in the order they came off
        self.draft_slot = None  # which seat you are in; set from the page
        self.sync_status = "waiting for first check"
        self.sync_live = False

    # -- marking players off -------------------------------------------------

    def take(self, player_id, mine, source="you"):
        with self.lock:
            if player_id in self.drafted or player_id not in self.by_id:
                return False
            self.drafted[player_id] = "me" if mine else "other"
            self.history.append(player_id)
            return True

    def undo(self):
        with self.lock:
            if not self.history:
                return False
            self.drafted.pop(self.history.pop(), None)
            return True

    def set_slot(self, slot):
        with self.lock:
            self.draft_slot = int(slot)

    # -- reading picks from ESPN --------------------------------------------

    def sync_from_espn(self):
        """
        Asks ESPN for the picks made so far. Returns how many new ones it
        found. Written defensively: if ESPN does not expose live picks, this
        quietly finds nothing and manual mode carries on unaffected.
        """
        try:
            self.league.refresh_draft()
            picks = getattr(self.league, "draft", None) or []
        except Exception as error:
            self.sync_status = f"ESPN sync unavailable ({type(error).__name__})"
            self.sync_live = False
            return 0

        my_team_id = self.league_info.get("team_id")
        added = 0

        for pick in picks:
            player_id = getattr(pick, "playerId", None)
            if player_id is None or player_id in self.drafted:
                continue
            if player_id not in self.by_id:
                continue  # someone outside our 500-player pool

            picked_by = getattr(pick, "team", None)
            team_id = getattr(picked_by, "team_id", None)
            mine = my_team_id is not None and team_id == my_team_id

            with self.lock:
                self.drafted[player_id] = "me" if mine else "other"
                self.history.append(player_id)
            added += 1

        if picks:
            self.sync_live = True
            self.sync_status = f"live from ESPN -- {len(picks)} picks seen"
        else:
            self.sync_status = "ESPN has no picks yet -- click players yourself"
        return added

    # -- what the page renders ----------------------------------------------

    def snapshot(self):
        my_roster = [self.by_id[pid] for pid, who in self.drafted.items() if who == "me"]
        picks_made = len(self.drafted)
        slot = self.draft_slot or 1

        result = advice.recommend(
            board=self.board,
            drafted_ids=set(self.drafted),
            my_roster=my_roster,
            plan=self.plan,
            draft_slot=slot,
            picks_made=picks_made,
            limit=BOARD_DEPTH,
        )

        rows = [
            row if place < DETAIL_DEPTH else slim(row)
            for place, row in enumerate(result["recommendations"])
        ]

        return {
            "league": {
                "name": self.league_info["name"],
                "rules": leagues.describe_rules(self.league),
                "teams": self.plan["teams"],
                "rounds": self.plan["total_rounds"],
            },
            "draft_slot": self.draft_slot,
            "picks_made": picks_made,
            "turn": result["turn"],
            "open_slots": result["open_slots"],
            "recommendations": rows,
            "my_roster": sorted(my_roster, key=lambda p: p["overall_rank"]),
            "roster_plan": self.plan,
            "sync": {"status": self.sync_status, "live": self.sync_live},
            "can_undo": bool(self.history),
        }


def background_sync(state):
    """Checks ESPN for new picks on a loop, quietly, in the background."""
    while True:
        try:
            state.sync_from_espn()
        except Exception:
            pass  # never let a sync problem take the page down mid-draft
        time.sleep(SYNC_SECONDS)


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # keep the terminal quiet during the draft

        def _send(self, payload, content_type="application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/state"):
                self._send(state.snapshot())
            elif self.path in ("/", "/index.html"):
                self._send(PAGE_HTML.encode(), "text/html; charset=utf-8")
            else:
                self.send_error(404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")

            if self.path == "/api/pick":
                state.take(data.get("player_id"), bool(data.get("mine")))
            elif self.path == "/api/undo":
                state.undo()
            elif self.path == "/api/slot":
                state.set_slot(data.get("slot"))
            elif self.path == "/api/sync":
                state.sync_from_espn()
            else:
                return self.send_error(404)

            self._send(state.snapshot())

    return Handler


def main():
    creds = leagues.load_credentials()

    print("Finding your leagues...")
    league_info = leagues.choose_league(creds, "Which draft are you doing?")

    print(f"\nConnecting to {league_info['name']}...")
    league = leagues.connect(league_info["league_id"], creds)
    print(f"  {leagues.describe_rules(league)}")

    print("Building your board (this takes a few seconds)...")
    state = DraftState(league, league_info, creds)
    print(f"  {len(state.board)} players ranked for this league's rules.")

    threading.Thread(target=background_sync, args=(state,), daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(state))
    url = f"http://127.0.0.1:{PORT}/"

    print(f"\nDraft assistant is running: {url}")
    print("Opening it in your browser now. Leave this window open.")
    print("Press Control-C here when the draft is over.\n")

    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGood luck this season.")


if __name__ == "__main__":
    main()
