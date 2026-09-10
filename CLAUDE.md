# Fantasy Football Assistant

A personal tool to help me win my ESPN fantasy football leagues. It reads
data from my ESPN league (rosters, matchups, standings, available players),
blends player rankings/projections and expert commentary pulled from
multiple outside sources, and uses that to recommend:

- **Pre-draft:** who to draft
- **In-season:** who to start/bench each week, and who to drop/pick up off
  waivers
- **Advanced (later phase):** matchup-aware recommendations that factor in
  who I'm playing against that week, plus trade suggestions based on my
  league's other rosters

## Data sources

To make recommendations, the tool should pull from:

- **Rankings and projections from major fantasy sites** (e.g. FantasyPros,
  ESPN's own projections, etc.) — quantitative player rankings
- **Articles and posts from fantasy writers/accounts** with start/sit and
  waiver insight — qualitative, "why" context that pure rankings miss
- **My own ESPN league data** — rosters, matchups, standings, available
  players (already working via `check_connection.py`)

## Important constraints

- **Read-only.** ESPN does not offer a write API, so this tool can only ever
  read data from ESPN — it cannot make roster moves, set lineups, or submit
  waiver claims automatically. Any change ESPN-side has to be done manually
  by me in the ESPN app/website, based on this tool's recommendations.
- **Secrets live in `.env`, never in git.** ESPN league credentials
  (`ESPN_LEAGUE_ID`, `ESPN_S2`, `ESPN_SWID`, `ESPN_SEASON`) are stored in a
  local `.env` file. `.env` is gitignored and must never be committed. See
  `.env.example` for the required variable names (no real values).
- **I'm non-technical.** I'm the primary user of this codebase but I'm not a
  software engineer. Explanations, commit messages, and code comments should
  favor plain language over jargon. When making changes, walk me through
  what's happening and why, not just what.

## Project status

The draft tooling is built and tested. Files:

- `leagues.py` — finds my leagues automatically by asking ESPN's fan API,
  so league IDs never need to be pasted into config. Falls back to
  `ESPN_LEAGUE_ID` in `.env` if that lookup fails.
- `rankings.py` — the value engine. Computes value over replacement (VOR)
  from ESPN projections and the league's own roster rules, then blends three
  signals into one board: VOR 55%, FantasyPros expert consensus 30%, ESPN
  roster percentage 15%. Groups players into tiers (tiers stay VOR-driven).
  Everything is per-league: ESPN returns different projections for a
  full-PPR league than a half-PPR one, so the boards genuinely differ.
- `outside_rankings.py` — the first non-ESPN source. Scrapes FantasyPros
  expert consensus rankings (ECR) for the scoring format that matches the
  league (PPR / half / standard), caches them under `cache/` for 12 hours,
  and matches them to ESPN players by name — with defenses matched by team
  instead, since the two sites name them completely differently. Fails
  quietly to an ESPN-only board if FantasyPros cannot be reached; this is
  tested, and it reproduces the old numbers exactly.
- `commentary.py` — the writer commentary. Pulls each player's latest
  RotoWire note from ESPN's public player feed, then collects every fantasy
  article those players are tagged in, reads each article once, and extracts
  the sentences that name the player. **Design rule: the tool collects what
  writers said, it does not re-derive their conclusions.** If a reporter has
  already written "how will the backfield touches be split between Hubbard
  and Brooks", that sentence beats anything we could infer from a depth
  chart. Also pulls a few checkable facts (draft year/round, experience,
  age, team change) from ESPN's season endpoints.
- `signals.py` — flags the players the three sources disagree about, so a
  bargain or a trap is visible while scanning rather than only after doing
  the arithmetic. Adds `value`, `overpriced` and `experts split` badges. It
  reports disagreement, never a prediction, and reads no prose. Three rules
  it exists to enforce, each found in the real board rather than guessed:
  compare **within a position** (our VOR and the FantasyPros overall list use
  different positional baselines, so a naive comparison called nearly every
  QB overrated and nearly every TE too); **ignore roster% above 99%** (34 of
  the top 150 sit there, so the gaps are rounding, not opinion); and judge
  expert disagreement **against a player's neighbours** (measured naively the
  most agreed-upon player on the board came out the most volatile, because
  half a rank of spread looks huge next to a rank of 1).
- `advice.py` — decides who *I* should take, given my roster, who is left,
  and how many picks until my next turn. Snake-draft aware.
- `draft_assistant.py` + `page.py` — the live draft tool. Opens a local web
  page showing the recommended pick and why. Run with
  `.venv/bin/python draft_assistant.py`.
- `draft_rankings.py` — the static cheat-sheet version. Prints a top-60
  board and writes a CSV per league to `output/` (gitignored).
- `weekly_rankings.py` — this week's expert opinion. FantasyPros rebuilds its
  rankings every week, one page per position, and those pages carry more than
  a rank: FantasyPros' own weekly point projection, how far a player moved
  since the last rebuild, and how widely the analysts disagree about him.
  Cached 3 hours (weekly lists move all week as practice reports land, unlike
  the 12-hour draft board). Refuses a page that comes back for the wrong week
  — FantasyPros rolls over to the next week once games finish, and would
  otherwise hand us the wrong list silently.
- `lineup.py` — the start/sit engine. Averages ESPN's weekly projection with
  FantasyPros' weekly projection 50/50 (both are already in points, so no
  rank juggling), applies injury designations, and solves for the best legal
  lineup. **The flex trap:** "start your highest projections" is not the same
  as "start the best lineup". The solver fills the fussiest slots first — a
  QB-only slot before a flex that takes almost anyone — which is optimal here
  because every flexible slot accepts a superset of what the stricter ones
  accept. Filling flex first can strand a dedicated slot empty.
- `start_sit.py` — the weekly command. `.venv/bin/python start_sit.py` prints
  a board per league: recommended lineup, what to change and why, starters to
  watch, and the bench. Won't recommend a change worth less than 0.5 points —
  both projections have real error bars and churning the lineup over a tenth
  of a point makes the tool feel unreliable.
- `test_lineup.py` — checks the solver against brute force (every legal
  arrangement, tried one at a time), including 200 random rosters. The solver
  is the one piece that can be quietly wrong: a lineup leaving half a point
  on the table looks completely normal in the output.
- `check_connection.py` — original sanity check.

Unverified until draft day: whether ESPN publishes picks to its read API
*during* a live draft. `draft_assistant.py` polls for them and uses them if
they appear, but manual click-to-mark is the primary path and works
regardless. Do not "fix" this by assuming sync works.

The live page sends 220 players deep, enough to cover a whole 12x14 draft
and to search for anyone, but the full write-up (articles, quotes, long
injury notes) only travels for the top 40. Sending all of it for all of them
was a megabyte of JSON every 2.5 seconds for reading material nobody opens.

**Facts vote, prose does not.** Structured facts (rookie, changed teams,
draft round) may nudge the score, and only in the late rounds — the nudge is
zero above rank 100 and reaches its full 12% by rank 250, because that is
where VOR stops separating players. Written sentences are shown and never
scored: "he is not the sleeper everyone thinks" and "he is a sleeper" are
nearly the same sentence, so a misread can never cost a pick. Changing teams
is flagged but deliberately unscored — it cuts both ways.

Start/sit is now built (`weekly_rankings.py`, `lineup.py`, `start_sit.py`).
Still missing: waiver, matchup-aware and trade logic. Sleeper and bust
signals are built (`signals.py`), but only the ones that come from source
disagreement — age cliffs and suspensions are still not modelled, because
neither is in the data the board already pulls.

Rough build order: (1) draft tooling — done, blended with FantasyPros,
(2) start/sit — done, (3) waiver and pickup/drop recommendations,
(4) advanced matchup- and trade-aware recommendations.

Known library quirk: `espn_api` keeps scoring rules in a shared dictionary,
so connecting to two leagues in one process makes the first one report the
second one's reception value. `start_sit.py` DOES do this — it walks all
three leagues in one run — so it connects, reads `leagues.describe_rules()`
and builds that league's whole board before connecting to the next one.
Anything else that touches two leagues at once must do the same: read the
rules right after connecting and remember the answer. Reordering that loop
so connections happen up front would silently give two leagues the wrong
scoring format, and the boards would still look perfectly reasonable.

## Leagues

Three ESPN leagues for 2026, all 12-team, and they do NOT share rules —
anything that assumes one format is a bug:

| League | ID | My team | Rules | Waivers | Trades |
|---|---|---|---|---|---|
| The Boyz are Back | 930020 | 2 | half PPR, **2 flex**, 8 playoff teams | FAAB **$100**, min bid $0, 12:00, every day but Tue | **no deadline**, 4 veto votes |
| D.C.F. | 1648293 | 10 | **full PPR**, 1 flex, 8 playoff teams | FAAB **$75**, min bid $1, 11:00, every day but Sun/Tue | deadline Dec 4, 4 veto votes |
| Only Sig Chi's, Mkay? | 946985 | 8 | half PPR, 1 flex, **6 playoff teams** | FAAB **$100**, min bid $1, 12:00, every day but Mon/Tue | deadline Dec 2, **0 veto votes** |

Read from ESPN on 2026-09-09, not assumed. Notes that matter:

- **All three are FAAB**, so there is no waiver-priority mode to build.
- **None of them use the classic Tuesday-night wire.** Each processes almost
  daily at its own hour, and Tuesday is the one day none of them run. Any
  waiver alerting must read each league's real schedule.
- Waiver process hours are ESPN's raw values; **the timezone is unconfirmed**
  and should be checked against a real processed claim before alarms depend
  on it.
- `acquisitionBudgetSpent` per team is readable, so the tool always knows
  what every opponent has left to bid.
- Bid history exists (`bidAmount` on every transaction) but as of Week 1
  there were only 6 real claims across all three leagues, all $1–$2. FAAB
  recommendations have to start on a heuristic and calibrate as the season
  fills that history in.

## Config

`.env` variables (see `.env.example`): `ESPN_SEASON`, `ESPN_S2`, `ESPN_SWID`.
`ESPN_LEAGUE_ID` / `ESPN_TEAM_ID` are now only a fallback — leagues are
discovered automatically. `ESPN_S2` and `ESPN_SWID` expire periodically and
have to be re-copied from a browser session.
