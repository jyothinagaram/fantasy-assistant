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
- `advice.py` — decides who *I* should take, given my roster, who is left,
  and how many picks until my next turn. Snake-draft aware.
- `draft_assistant.py` + `page.py` — the live draft tool. Opens a local web
  page showing the recommended pick and why. Run with
  `.venv/bin/python draft_assistant.py`.
- `draft_rankings.py` — the static cheat-sheet version. Prints a top-60
  board and writes a CSV per league to `output/` (gitignored).
- `check_connection.py` — original sanity check.

Unverified until draft day: whether ESPN publishes picks to its read API
*during* a live draft. `draft_assistant.py` polls for them and uses them if
they appear, but manual click-to-mark is the primary path and works
regardless. Do not "fix" this by assuming sync works.

**Facts vote, prose does not.** Structured facts (rookie, changed teams,
draft round) may nudge the score, and only in the late rounds — the nudge is
zero above rank 100 and reaches its full 12% by rank 250, because that is
where VOR stops separating players. Written sentences are shown and never
scored: "he is not the sleeper everyone thinks" and "he is a sleeper" are
nearly the same sentence, so a misread can never cost a pick. Changing teams
is flagged but deliberately unscored — it cuts both ways.

Still missing: start/sit, waiver, matchup-aware and trade logic. Also not
built yet: sleeper/bust signals derivable from data already on the board
(low roster% against a good expert rank, one analyst ranking someone far
above consensus, age cliffs, suspensions).

Rough build order: (1) draft tooling — done, now blended with FantasyPros,
(2) start/sit and waiver recommendations once the season has live
rosters/matchups, (3) advanced matchup- and trade-aware recommendations
once the basics work.

Known library quirk: `espn_api` keeps scoring rules in a shared dictionary,
so connecting to two leagues in one process makes the first one report the
second one's reception value. Nothing does that today (one league per run).
Anything that touches two leagues at once must read
`leagues.describe_rules()` right after connecting and remember the answer.

## Leagues

Three ESPN leagues for 2026, all 12-team, and they do NOT share rules —
anything that assumes one format is a bug:

| League | ID | My team | Rules |
|---|---|---|---|
| The Boyz are Back | 930020 | 2 | half PPR, **2 flex** |
| D.C.F. | 1648293 | 10 | **full PPR**, 1 flex |
| Only Sig Chi's, Mkay? | 946985 | 8 | half PPR, 1 flex |

## Config

`.env` variables (see `.env.example`): `ESPN_SEASON`, `ESPN_S2`, `ESPN_SWID`.
`ESPN_LEAGUE_ID` / `ESPN_TEAM_ID` are now only a fallback — leagues are
discovered automatically. `ESPN_S2` and `ESPN_SWID` expire periodically and
have to be re-copied from a browser session.
