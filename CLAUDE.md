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
- **Claims at one position are alternatives for one slot, not moves you can
  stack (2026-09-22).** `waivers.rank_claims` keeps the best 1 at QB/K/D-ST
  and 2 at RB/WR/TE and counts the rest, because a run of six quarterbacks
  is one decision with five runners-up and it was burying the running back
  that would actually matter. `waivers.shared_drops` names anyone who is
  the drop on more than one claim — each claim is costed on its own and
  assumes only that move, so the same roster spot gets spent repeatedly
  (every D.C.F. claim dropped Mack Hollins). The CLI had both of these all
  along; **the app had drifted** and showed a flat top-15 with three
  kickers in it. Both are now shown under the claims deck.
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
  specific trade (offered or received) from both sides. `--needs` runs the
  needs model instead: the league's holes and spare parts, who fits me and in
  which direction, then offers built only out of what both sides can spare,
  each with how it reads to the other manager and the line to send him.
- `needs.py` — the needs model, the layer that decides WHERE to look before
  `trades.py` decides whether a trade is good. For every team it prices, in
  the same pts/week currency as everything else: a **need** at a position
  (what that team would gain from one league-average starter there, measured
  by adding a phantom player to `waivers.team_value`) and a **spare** (a
  player worth 6+ pts whom the team could lose for under 1 pt/week, because
  the next man slides into the slot). The bar for "average starter" is the
  median of the top N at that position league-wide, N = teams × slots started,
  with a flex slot split evenly between the positions it accepts — an average
  of everyone rostered would be dragged down by benched streamers and make
  every hole look filled. **Only the cheapest spare at a position is offered**
  (plus anyone within 1 pt/week of him): on a team of interchangeable
  receivers even the nominal WR1 prices as cheap to lose, but offering the
  costlier of two players who fill the same hole is strictly dominated.
  **A need is only worth trading for if the waiver wire cannot fix it
  (2026-09-22).** Every hole is priced twice — against an average starter,
  and against the best player actually free — and only the difference is
  what a trade there is worth. This came from a real complaint: the board
  recommended almost nothing but quarterback trades, because in all three
  leagues a 19-20 pt QB (Bryce Young, Tyler Shough) sits in free agency, so
  a "QB hole" scored +2.8 to +4.4/wk that a waiver claim fixes for nothing.
  After the correction every league's QB need fell to +0.0 and RB/WR
  survived intact — the honest version of "receivers and running backs win
  leagues": not a preference for those positions, but that their pools run
  dry and the QB pool does not. **The discount applies to what I CHASE, not
  to what THEY will accept** (`holes(..., waiver_aware=False)`): the other
  manager sees the hole in his lineup, not the discount, and his lineup
  really does improve. Getting that backwards emptied the board completely
  the first time. `needs.worth_trading_for` applies the same rule to the
  main ideas deck — those trades are set aside with a reason, never
  silently dropped.
  A partner is a "fit" only when the crossing runs BOTH ways — they have
  players at a position I leak points at and vice versa; one direction alone
  is a request, not an offer. Ideas are then narrowed **by position, not by
  spare-ness** — asking only for players the other team can spare works at
  deep positions and fails exactly where it matters, because nobody has a
  spare running back, which is the whole reason the position is worth
  trading for. A scarce position has to be PAID for, out of the depth I can
  spare. (Narrowing by spare-ness hid real RB win-wins — Omarion Hampton,
  McCaffrey — that the unfiltered search found.) The shortlist is handed to
  `trades.ideas_with` (which now takes optional
  `my_pieces`/`their_pieces` shortlists; the valuation is unchanged, only
  the search is narrowed). **Perception is modelled separately from value**
  and never touches it: `needs.perception` reports how the offer reads to
  the other manager — raw points for/against him, whether what he gets lands
  on a hole he can see — as EASY YES / NEEDS A PITCH / HARD SELL, plus the
  sentence to send him. It changes whether a trade is worth sending, never
  whether it is good.
- `test_trades.py` — a WR-rich vs RB-rich pair of teams where the win-win is
  obvious, forced cuts on 2-for-1s, and the padding filter.
- `test_needs.py` — the same mirrored rosters: the flex split, the starter
  bar resisting bench drag, depth that never starts costing nothing to lose,
  the dominated-spare rule, a twin roster being no fit, both perception
  verdicts, and that narrowing the search leaves the valuation identical.
- `situation.py` — games that no longer describe the player. A season
  average is only evidence if the games in it were played in the situation
  he is in now. Two kinds of game are marked `stale_games`, and
  `waivers.per_game_value` stops counting them: **(1) a different
  quarterback** — a receiver's passes thrown by somebody other than the man
  his team should be starting now (from the nflverse play-by-play already
  on disk); **(2) a game he did not play** — one cut short by injury, from
  the snap counts. Kyler Murray played 11 snaps, 17% of week 1, and scored
  −0.38; that number says nothing about how he plays and everything about
  when he left, and it was holding him at 13.9 against an 18.5 projection.
  After: 17.5. (It also made Bryce Young look like a +3.3/wk claim; he is
  +2.6 once Murray is priced properly — the two corrections interact.)
  A cut-short game is judged against the player's OWN median snap share
  (`PART_OF_HIS_NORMAL`), so a committee back at 30% every week is not
  mistaken for a limp-off. With fewer than two other games to compare,
  **only quarterbacks** get an absolute floor (`QB_PLAYED_THE_GAME`),
  because a starting QB plays every snap and 17% cannot mean anything else;
  there is deliberately no floor at the other positions, whose roles vary
  too much for one to be honest. Snap counts also tell us **which** weeks a
  player actually played, which is better than the old "last N weeks" guess — so his value falls back
  toward the projections. **The case that prompted it (2026-09-22):** Drake
  London's only two games were thrown by Cooper Rush with Michael Penix Jr.
  hurt, so his 7.2 average was a real number about an offence that no longer
  exists; it was dragging him to 12.5 against a 15.4 projection. After:
  15.2. **It cuts both ways** — Jaxon Smith-Njigba's flattering 34.4 with
  D.Lock stopped inflating him (25.1 → 20.5).
  The expected starter is the best FIT quarterback the league can see, and
  **the waiver pool has to be included** — that was the bug in the first
  version: Penix was unrostered while injured, so a search of rosters alone
  found no Atlanta starter and changed nothing. **Quarterbacks are matched
  by nflverse→ESPN id, never by name**, because "A.St. Brown" would fail a
  first-initial match and a mismatch looks exactly like the thing being
  detected — it would mark whole rosters stale and move every number.
  Guards: a quarterback who is hurt/suspended/IR is never the benchmark (he
  cannot be who they start), and a sub-10-point quarterback is not treated
  as anyone's plan (a rostered third-stringer on a team whose real starter
  nobody rosters would otherwise mark every week stale). **Running backs are
  deliberately excluded** — carries arrive whoever is under centre, and
  marking a back's whole average stale would throw away the part of his game
  that did not change. Attached in `trades.build`, `waivers.build` and
  `lineup.build`, so trades, start/sit and add/drop all move together. A
  missing play-by-play file marks nothing and changes nothing.
- `test_situation.py` — the London case, the mirror case that flatters, the
  no-change case, the injured/third-string guards, the unrostered-starter
  bug, running backs untouched, a missing file; and for cut-short games:
  Murray's 17%, a full game left alone, a committee back at a steady 30%
  NOT flagged, the same back flagged when he drops to 5%, and no absolute
  floor away from quarterback.
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
- `consistency.py` — week-to-week swings from nflverse weekly stats, LAST
  season + this season, most recent 17 games (min 6; games under 0.5 pts
  skipped as cameos/early exits), in the league's scoring: floor (20th pct),
  ceiling (80th pct), swing (coefficient of variation) → steady / normal /
  boom-or-bust. Shown, never scored.
- `matchup.py` — this week's head-to-head. Builds the OPPONENT's best lineup
  with `lineup.build` (assumes they set their best), win chance from a bell
  curve whose width comes from every starter's swing (default 0.6 when
  unmeasured), shown to the nearest 5% — and the favourite/underdog label
  uses that ROUNDED number so "35%" never reads "toss-up". Favourite ≥65%,
  underdog ≤35%. Never changes the recommended lineup; only "close calls"
  (bench within 1.5 pts of a starter at an eligible slot, neither locked):
  underdog leans to a ceiling 2+ pts higher, favourite to a floor 2+ higher.
  In `start_sit.py`, the check-up (`coach.build` → `matchup`) and the app
  (win % on Team and Start/Sit tabs).
- `test_matchup.py` — profiles, labels, win chance with 9-man lineups (one-man
  lineups swing too much to test with), underdog/favourite leans, toss-up,
  far gaps and wrong positions ignored.
- `redzone.py` — red-zone (inside the 20) and goal-line (inside the 5)
  carries+targets per player and share of team red-zone chances, from
  nflverse play-by-play (`play_by_play_<season>.csv.gz`, 6h cache). Merged
  into the `usage.py` summary so it appears in every usage line; in
  `upside.py` 25%+ of team red-zone chances (3+ opportunities) is +0.5.
- `weather.py` — kickoff-hour forecast for OUTDOOR games only, free and
  keyless: ESPN scoreboard gives venue city/state/country and `indoor`
  (handles neutral-site/international games); Open-Meteo geocodes the city
  (cached permanently; picks the right US state — many Springfields) and
  forecasts wind/gusts/rain chance/temperature (3h cache, 16-day window).
  Flags wind 15+ mph (K, QB, WR, TE), rain 60%+ (K, QB, WR), 25°F or colder
  (K) — only on the positions each hurts. Shown, never scored (betting totals
  and projections move with forecasts). In start/sit reasons, "watch" list,
  and the app.
- `test_weather.py` — thresholds, wording, state matching, affected positions.
- `playoffs.py` — each player's NFL opponents in the league's fantasy
  playoff weeks (from settings: reg season + ceil(log2(playoff teams))
  rounds x period length → weeks 15-17 for all three leagues), from ESPN's
  `proTeamSchedules_wl`. Flags a BYE in a playoff week; rates the run
  soft/neutral/tough by average `defense.py` rank, but only once every
  opponent defence has 4+ games. Shown on trades (CLI + app), never scored.
- `test_playoffs.py` — playoff weeks per settings, bye flag, rating waits
  for games, unknown teams.
- `test_usage.py` — ID matching, snap trend, preseason rows ignored, shares,
  and missing files.
- `app.py` + `app_page.py` — the in-season web app, the main way the user
  wants to use the tool. `.venv/bin/python app.py` opens it in the browser
  and prints a phone address (same Wi-Fi; binds 0.0.0.0 unless
  `APP_LOCAL_ONLY=1`). Tabs: **Team** (home — record/standing, position bars
  vs league, biggest WEAKNESSES then STRENGTHS, each with waiver/stash/trade
  suggestions that jump to and highlight the matching card on the Waivers or
  Trades tab; strengths list trades that SELL from that depth), **Start/Sit**,
  **Waivers** (under-the-radar first, then claims), **Trades** (the needs
  board — "What I need" (priced after waivers, showing what the wire already
  fixes), "What I can spare", "Offers built from what both sides can spare",
  then a "Who fits" deck of the teams that cross with mine in both
  directions — followed by the full both-lineups ideas deck, a collapsed
  "N more that waivers can fix for free" section, and a checkbox trade
  checker), **Guide** (plain-language explanation of every
  feature, data source and ground rule; static, works before data loads —
  keep it in sync when features change). Phone-first: tabs at the bottom under 760px. Lists of cards (weaknesses,
  strengths, under-the-radar, claims, trade ideas) are "decks": on a phone one
  swipeable row with the next card peeking in (86% width, scroll-snap); from
  760px a grid of as many 330px+ columns as fit. Page widens to 1320px for
  decks; Start/Sit and Guide stay 980px for reading. Jump-to links use
  `scrollIntoView` so they reach cards inside a sideways row. On a trade card
  the other team's name opens their ROSTER (inside the Trades tab, state
  `rosterTeam`): record/standing, starters/bench/IR as set on ESPN grouped by
  position with normal-week points, usage, playoff schedule, "In a trade
  idea" links, and "Build a trade with them" which preselects the checker. The roster view
  works from any tab (Team tab has "My roster").
  **Live scoreboard** at the top of Team: `/api/scoreboard/<league>` →
  `app.build_scoreboard` from `league.box_scores(current_week)`, cached 60s,
  polled every minute while on Team. It REUSES the worker's league
  connection (`AppState.connections`) — never opens a new one, because
  connecting resets espn_api's shared scoring settings mid-build. Game state
  per player from kickoff time (upcoming / live for 3.5h / final); "on pace"
  = points so far + projection for players yet to play (half for games in
  progress).
  Each league is built by `coach.build` in ONE background worker thread, one
  league at a time (the scoring-rules quirk), saved to `cache/app_<id>.json`
  and served instantly on restart; the page polls and shows data age, and has
  **Every trade card in the app — an idea, a needs-matched offer, or one the
  checker just valued — carries a "how it reads to them" block**: EASY YES /
  NEEDS A PITCH / HARD SELL, which of their holes the players land on, and
  the line to send. It comes from `needs.perception` and never touches the
  numbers above it (see `needs.py`). The checker works it out from the saved
  private board in ~40ms, so it costs no extra ESPN call.
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
trades (`trades.py`, `trade_finder.py`, `needs.py`). Still missing: matchup-aware logic
(who I play this week), broader data collection. The UI is built (`app.py`). The user chose FREE
data sources only, in this order: snap counts and target data (nflverse) —
DONE, rest-of-season FantasyPros rankings, defence vs position from
ESPN box scores, league bid history for FAAB — DONE (`bids.py`), opponent-aware
start/sit — DONE (`matchup.py` + `consistency.py`), red-zone touches — DONE
(`redzone.py`), weather — DONE (`weather.py`),
playoff-week schedules — DONE (`playoffs.py`). The planned free-data list
is complete as of 2026-09-14. Sleeper and bust
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
(4) trades — done, including the needs model and situation-aware values
(`needs.py`, `situation.py`, 2026-09-22);
matchup-aware still to do, (5) UI and more data sources.

**Never guess a bye from a zero projection (fixed 2026-09-14).** ESPN
projects 0 for a player it expects to miss a game — Kyler Murray in the
concussion protocol showed as "BYE" in week 2 because
`rankings.find_bye_week` treats any zero week as the bye. In-season code
must use `waivers.bye_weeks(league)` (ESPN's real per-team bye table);
`lineup.roster` now does. `find_bye_week` is only a draft-time fallback.

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
