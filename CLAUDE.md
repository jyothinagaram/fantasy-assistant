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
- `status.py` — how real that "Questionable" is, and when the decision
  expires. Two jobs. (1) **Severity.** "Questionable" is a weak word doing
  several jobs — some players are genuinely fifty-fifty, some are listed that
  way so the other team has to game-plan for both. The designation cannot
  separate those; practice participation largely can, and RotoWire publishes
  it in a formulaic sentence. So the practice level is lifted out as a fact
  and allowed to vote; the coach quotes around it are shown verbatim and
  never scored. (2) **Lock times.** Each player locks when HIS game kicks
  off, so a Thursday player is decided before most of the week's news exists.
  One scoreboard call covers all 16 games.
- `test_status.py` — tests the practice reader, which is the riskiest code in
  the project: everywhere else the tool reads numbers, here it reads English.
  Mostly tests sentences that must NOT match.
- `waivers.py` — the waiver engine. Values every possible swap (add this
  free agent, drop that player of mine) by playing out each remaining
  regular-season week, solving the best lineup each week with the start/sit
  solver, and summing the points. The gain is the pickup's value, so starting
  potential, bye-week cover and each league's slots are all handled by one
  number. The first playable week uses the start/sit score (ESPN + experts,
  injuries); later weeks use a per-game value that blends ESPN's projection
  with points actually scored (actual scoring counts as much as the
  projection after 4 games; 10 games for K and D/ST, which are too noisy).
  IR and suspended players are assumed to miss 4 weeks (ESPN gives no return
  date). Players in the IR slot are never suggested as drops. **Ties are
  common** — two bench players who never start cost the same to drop — so
  ties drop the weaker player. FAAB bids are a flagged heuristic: a share of
  budget *remaining*, tiered by points/week gained, x1.5 if the player is over
  50% owned across ESPN. Recalibrate once real bid history exists.
- `waiver_wire.py` — the waiver command. `.venv/bin/python waiver_wire.py`
  prints, per league: waiver schedule, FAAB left (yours and the richest
  opponents'), and ranked ADD / DROP / bid suggestions with the facts behind
  each. Won't suggest a claim worth under 0.5 pts/week. A pickup's first week
  is the week after the current one once any of its games has kicked off.
- `upside.py` — the UNDER THE RADAR section of the waiver report: RB/WR/TE
  available in the league, under 60% owned, whose situation just changed
  before their numbers caught up. The user asked for this explicitly: QB
  pickups are obvious from the ESPN app; hidden skill players are not. Four
  fact signals add up to an "upside score", each with its own sentence:
  **opening** (teammate at his position OUT/IR/doubtful/suspended, weighted by
  that teammate's projection; WR and TE share targets at half weight),
  **role** (carries+targets per game for RBs, target share for WR/TE),
  **crowd** (ESPN ownership % change this week), **matchup** (team's implied
  points from the DraftKings total and spread on ESPN's scoreboard — betting
  markets price defences and injuries better than any rank). Rules learned
  from the first real run: an injury is only news if the injured player has
  played this season (otherwise his teammates' usage already reflects it —
  30% credit); an opening barely helps a player with under 12% target share
  or 3 targets a game (40% credit — practice-squad receivers were making the
  list); matchup alone never qualifies; max 2 players per team. The RotoWire
  note is printed verbatim, never scored. Each player is marked CLAIM (helps
  the lineup today, with drop and bid) or STASH (a bet on the situation).
  The claims list below it is RB/WR/TE only unless `--all-positions`.
- `test_upside.py` — fresh vs old injury, unused players, the injured player
  himself, matchup-only, and crowd/bad-matchup arithmetic.
- `test_waivers.py` — hand-built rosters where the right answer is obvious:
  upgrade drops the worst player, useless pickups aren't suggested, bye cover
  is worth exactly the bye week, IR slot is never dropped, bids never exceed
  budget and never go down as the gain goes up.
- `trades.py` — the trade engine. Values a trade for EACH team the same way
  waivers are valued: best lineup every remaining week, before vs after
  (`waivers.team_value`). The finder tries every 1-for-1, 2-for-1 and 1-for-2
  with each opponent (players worth 6+ pts in a normal week; 2-player sides
  use each team's top 8) and keeps only trades that help BOTH lineups by
  0.5+ pts/week — one-sided offers get rejected or vetoed. Uneven trades:
  the side receiving more players cuts whoever costs it least; the side
  receiving fewer is NOT assumed to fill the spot (conservative). **Padding
  filter:** a trade is dropped if a smaller version of it (fewer given, same
  or more received) is worth about the same to me — otherwise the list
  suggests throwing in a player for nothing. An "on paper" line compares raw
  normal-week points, which is how the other manager and veto voters will
  judge it, even when lineup maths says it helps them.
- `trade_finder.py` — the trade command. No arguments: up to 2 ideas per
  opponent, 10 total, per league. `--league X --give A B --get C` checks one
  specific trade (offered or received) from both sides.
- `test_trades.py` — a WR-rich vs RB-rich pair of teams where the win-win is
  obvious, forced cuts on 2-for-1s, and the padding filter.
- `coach.py` + `team_report.py` — the team check-up, meant to be run FIRST
  each week. (1) Results: last week's score, league-wide rank of that score,
  points left on the bench (best legal lineup from actual points, IR slot
  excluded), season record built from box scores (ESPN's W-L lags until a
  week is final), standing and ESPN's playoff %. The bench review is skipped
  until a week is final — unplayed players show 0 and would be wrongly
  called bench mistakes. (2) Gaps: each position group's normal-week starter
  points vs the league median, with rank. (3) Where to focus: the best
  LINEUP / WAIVER / TRADE move ranked in points per week (lineup marked
  "this week only"), plus the top under-the-radar STASH; then for each gap
  (1+ pt below median) the waiver, stash and trade options that fix it. No
  new maths — everything comes from lineup, waivers, upside and trades, so it
  always agrees with the detailed tools. Slow: ~1.5 min per league.
- `usage.py` — FREE snap counts and target data from nflverse
  (github.com/nflverse/nflverse-data releases: `snap_counts_<season>.csv`,
  `stats_player_week_<season>.csv`, `players.csv`), cached 6 hours (players
  table 7 days). Matched to ESPN by **espn_id** via nflverse's players table
  (pfr_id for snaps, gsis_id for stats) — never by name. Per player: latest
  snap %, snap trend vs his earlier games, target share / air-yards share /
  WOPR averaged over the last 2 weeks. nflverse posts a day or two after
  games. Shown as a "usage" line in start/sit, waivers, trades and the app.
  In `upside.py` snaps VOTE: +1.5 for a snap jump of 15+ pts ("ROLE
  GROWING", usually a week before targets follow), +0.5 for 70%+ snaps, and
  40%+ snaps counts as next-in-line for an opening. **Snaps only count if
  the ball comes his way** (10%+ target share, or 8+ touches for RBs) —
  Rashod Bateman made the list on 78% snaps and 4% of targets, a blocker.
  nflverse's target share replaces the ESPN-pool estimate when present.
- `ros_rankings.py` — FantasyPros REST-OF-SEASON consensus (`ros-*.php`
  pages, per scoring format for RB/WR/TE), cached 12h. Uses `r2p_pts` (their
  projected rest-of-season points) divided by games left (weeks to 18, minus
  a bye still to come). **Calibrated per position**: FantasyPros totals ran
  ~10% above ESPN at every position (K ~1%) — scale, not opinion — so each
  position is rescaled so its median player matches ESPN; otherwise ranked
  players get a free boost over unranked ones. `waivers.per_game_value` now
  blends ESPN season projection and this 50/50 (ESPN alone if unranked), so
  waivers, trades, gaps and the app all use it. Shown as "rest of season:
  experts X/game (WR22), ESPN Y/game".
- `defense.py` — defence vs position: fantasy points each defence allowed
  per game to QB/RB/WR/TE, from nflverse weekly stats (`opponent_team`,
  `fantasy_points` / `_ppr`; half PPR = their average), in the league's own
  format, only from weeks BEFORE the one being previewed. Ranked 1 = most
  generous; pulled toward league average with a 3-game prior. **Shown, never
  scored** — ESPN and FantasyPros projections already price in the opponent,
  so scoring it would count the defence twice. "soft"/"tough" labels (top/
  bottom 8) only once a defence has 2+ games; one game is mostly who it
  played. Appears in start/sit reasons, waiver reasons, under-the-radar and
  the app (green soft, red tough).
- `test_defense.py` — crediting and ranking, previewed week excluded, scoring
  formats, the prior, and no label after one game.
- `bids.py` — each league's real FAAB prices from ESPN `mTransactions2`
  (read week by week; WAIVER type, EXECUTED = won, FAILED* = lost, when
  ESPN exposes them). Summarises contested claims (bid above the minimum):
  median winning bid, the bid that wins 3 in 4 (75th percentile), largest
  bid, each manager's claims/spend. Once 5+ contested claims exist it
  adjusts the rule-of-thumb bid: pickups worth 3+ pts/wk are raised to at
  least the 3-in-4 price; smaller ones are capped at 1.25x the median, so
  budget is not wasted in a cheap league. Below 5 it changes nothing and
  says so. As of 2026-09-14: 0, 1 and 3 claims — all rule of thumb.
- `test_bids.py` — too little history, minimum-bid claims not contested,
  raise/cap, budget ceiling, rival counting.
- `test_usage.py` — ID matching, snap trend, preseason rows ignored, shares,
  and missing files.
- `app.py` + `app_page.py` — the in-season web app, the main way the user
  wants to use the tool. `.venv/bin/python app.py` opens it in the browser
  and prints a phone address (same Wi-Fi; binds 0.0.0.0 unless
  `APP_LOCAL_ONLY=1`). Tabs: **Team** (home — record/standing, position bars
  vs league, biggest WEAKNESSES then STRENGTHS, each with waiver/stash/trade
  suggestions that jump to and highlight the matching card on the Waivers or
  Trades tab; strengths list trades that SELL from that depth), **Start/Sit**,
  **Waivers** (under-the-radar first, then claims), **Trades** (ideas + a
  checkbox trade checker). Phone-first: tabs at the bottom under 760px.
  Each league is built by `coach.build` in ONE background worker thread, one
  league at a time (the scoring-rules quirk), saved to `cache/app_<id>.json`
  and served instantly on restart; the page polls and shows data age, and has
  Refresh. The trade checker values trades from a server-side copy of every
  roster's valuation fields, so it never re-asks ESPN. No build step, no new
  dependencies. `APP_NO_BROWSER=1` skips opening a browser (for testing).
- `check_connection.py` — original sanity check.

Unverified until draft day: whether ESPN publishes picks to its read API
*during* a live draft. `draft_assistant.py` polls for them and uses them if
they appear, but manual click-to-mark is the primary path and works
regardless. Do not "fix" this by assuming sync works.

The live page sends 220 players deep, enough to cover a whole 12x14 draft
and to search for anyone, but the full write-up (articles, quotes, long
injury notes) only travels for the top 40. Sending all of it for all of them
was a megabyte of JSON every 2.5 seconds for reading material nobody opens.

**Facts vote, prose does not.** In-season this rule is what lets the tool
read a practice report without reading a writer's opinion: "was a full
participant in Friday's practice" is formulaic enough to be a fact, so it
votes; "all signs point to him being out there" is an opinion, so it is
shown and never scored. `status.py` also refuses to guess — a sentence it
cannot parse yields no report, which is a no-op, so an unreadable note costs
the extra insight and never costs a lineup.

On the draft board, structured facts (rookie, changed teams,
draft round) may nudge the score, and only in the late rounds — the nudge is
zero above rank 100 and reaches its full 12% by rank 250, because that is
where VOR stops separating players. Written sentences are shown and never
scored: "he is not the sleeper everyone thinks" and "he is a sleeper" are
nearly the same sentence, so a misread can never cost a pick. Changing teams
is flagged but deliberately unscored — it cuts both ways.

Start/sit is now built (`weekly_rankings.py`, `lineup.py`, `status.py`,
`start_sit.py`), including the pre-kickoff check: `start_sit.py --lock`.
Waivers are built too (`waivers.py`, `waiver_wire.py`, `upside.py`), and
trades (`trades.py`, `trade_finder.py`). Still missing: matchup-aware logic
(who I play this week), broader data collection. The UI is built (`app.py`). The user chose FREE
data sources only, in this order: snap counts and target data (nflverse) —
DONE, rest-of-season FantasyPros rankings, defence vs position from
ESPN box scores, league bid history for FAAB, opponent-aware start/sit. Sleeper and bust
signals are built (`signals.py`), but only the ones that come from source
disagreement — age cliffs and suspensions are still not modelled, because
neither is in the data the board already pulls.

**Questionable players are not discounted twice.** ESPN and FantasyPros have
already priced the average questionable player into the projections we
average, so a further injury haircut would charge him twice for the same
ankle — `INJURY_MULTIPLIERS["QUESTIONABLE"]` is deliberately 1.0. What is
NOT priced in is how *this* questionable player differs from that average,
which is what the practice multipliers in `status.py` express: they are
relative to the typical questionable player, not to a healthy one. That is
why full participation is only +10% (he must never end up worth more than
he would be healthy) while no practice at all is -45%.

Rough build order: (1) draft tooling — done, blended with FantasyPros,
(2) start/sit — done, (3) waiver and pickup/drop recommendations — done (bids still heuristic),
(4) trades — done; matchup-aware still to do, (5) UI and more data sources.

**Next-week projections bug (fixed 2026-09-14).** `league.teams[...].roster`
only carries projections for `league.current_week`. Planning for the next
week from it gave every ROSTERED player 0 while free agents (fetched per
week) had real numbers — inflating every pickup's gain and emptying next
week's start/sit. `lineup.rosters_for_week(league, week)` re-reads rosters via
the `mRoster` view with `scoringPeriodId=week`; lineup, waivers and trades all
use it. Anything new that plans a future week must too.

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
| D.C.F. | 1648293 | 10 | **full PPR**, 1 flex, **6 playoff teams** | FAAB **$75**, min bid $1, 11:00, every day but Sun/Tue | deadline Dec 4, 4 veto votes |
| Only Sig Chi's, Mkay? | 946985 | 8 | half PPR, 1 flex, 8 playoff teams | FAAB **$100**, min bid $1, 12:00, every day but Mon/Tue | deadline Dec 2, **0 veto votes** |

Read from ESPN on 2026-09-09, not assumed. (Playoff counts corrected
2026-09-14 from `scheduleSettings.playoffTeamCount`: D.C.F. 6, Sig Chi's 8.) Notes that matter:

- **All three are FAAB**, so there is no waiver-priority mode to build.
- **None of them use the classic Tuesday-night wire.** Each processes almost
  daily at its own hour, and Tuesday is the one day none of them run. Any
  waiver alerting must read each league's real schedule.
- Waiver process hours are ESPN's raw values; **the timezone is unconfirmed**
  and should be checked against a real processed claim before alarms depend
  on it.
- `acquisitionBudgetSpent` per team is readable, so the tool always knows
  what every opponent has left to bid.
- ESPN's league-wide injuries feed
  (`site.web.api.espn.com/.../nfl/injuries`) is NOT worth using: its comment
  fields just echo the status (`longComment: "questionable"`). The useful
  text is the RotoWire note on the player overview endpoint instead. Also
  note `site.api.espn.com` returns 403 — use `site.web.api.espn.com`.
- Bid history exists (`bidAmount` on every transaction) but as of Week 1
  there were only 6 real claims across all three leagues, all $1–$2. FAAB
  recommendations have to start on a heuristic and calibrate as the season
  fills that history in.

## Config

`.env` variables (see `.env.example`): `ESPN_SEASON`, `ESPN_S2`, `ESPN_SWID`.
`ESPN_LEAGUE_ID` / `ESPN_TEAM_ID` are now only a fallback — leagues are
discovered automatically. `ESPN_S2` and `ESPN_SWID` expire periodically and
have to be re-copied from a browser session.
