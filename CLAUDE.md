# Fantasy Football Assistant

A personal tool for managing my ESPN fantasy football team. It reads data from
my ESPN league (rosters, matchups, standings, available players), blends
player rankings pulled from multiple outside sources, and uses that to
recommend:

- Draft picks
- Weekly start/sit decisions
- Waiver wire pickups/drops

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
`espn-api` and prints teams/rosters as a sanity check. Ranking-blending
and recommendation logic (draft, start/sit, waiver) not yet implemented.

## Config

`.env` variables (see `.env.example`): `ESPN_LEAGUE_ID`, `ESPN_S2`,
`ESPN_SWID`, `ESPN_SEASON`, `ESPN_TEAM_ID` (my team within the league,
"@ Heylils", id 8).
