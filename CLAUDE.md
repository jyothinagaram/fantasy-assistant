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

Early stage. `check_connection.py` connects to the ESPN league via
`espn-api` and prints teams/rosters as a sanity check. Nothing yet pulls
outside rankings/projections/articles, and no recommendation logic (draft,
start/sit, waiver, matchup-aware, trades) is implemented.

Rough build order: (1) draft rankings blender, since draft comes first
chronologically, (2) start/sit and waiver recommendations once the season
has live rosters/matchups, (3) advanced matchup- and trade-aware
recommendations once the basics work.

## Config

`.env` variables (see `.env.example`): `ESPN_LEAGUE_ID`, `ESPN_S2`,
`ESPN_SWID`, `ESPN_SEASON`, `ESPN_TEAM_ID` (my team within the league,
"@ Heylils", id 8).
