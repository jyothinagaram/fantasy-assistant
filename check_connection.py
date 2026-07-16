"""
Quick sanity check: connects to your ESPN league using the credentials
in .env and prints each team's name and roster. Run this to confirm the
connection works before building anything on top of it.
"""

import os
import sys

from dotenv import load_dotenv
from espn_api.football import League

load_dotenv()

required_vars = ["ESPN_LEAGUE_ID", "ESPN_SEASON"]
missing = [name for name in required_vars if not os.getenv(name)]
if missing:
    sys.exit(
        f"Missing required .env values: {', '.join(missing)}. "
        "Copy .env.example to .env and fill them in."
    )

league = League(
    league_id=int(os.getenv("ESPN_LEAGUE_ID")),
    year=int(os.getenv("ESPN_SEASON")),
    espn_s2=os.getenv("ESPN_S2") or None,
    swid=os.getenv("ESPN_SWID") or None,
)

print(f"Connected to league: {league.settings.name}")
print(f"Current week: {league.current_week}\n")

for team in league.teams:
    print(f"[{team.team_id}] {team.team_name} ({team.wins}-{team.losses})")
    for player in team.roster:
        print(f"    {player.name} - {player.position}")
    print()
