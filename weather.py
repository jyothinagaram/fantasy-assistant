"""
Game-time weather for outdoor games.

Weather matters less than people think, with one big exception: WIND. Past
about 15 mph, kickers miss more, quarterbacks throw shorter, and deep
receivers suffer. Heavy rain and hard cold matter a little. Domes and closed
roofs do not matter at all.

Everything here is free and needs no account:

  * ESPN's scoreboard says where each game is played and whether the venue
    is indoors (this also handles international and neutral-site games);
  * Open-Meteo's geocoder turns the city into coordinates (cached for good);
  * Open-Meteo's forecast gives wind, gusts, rain chance and temperature for
    the kickoff hour, once the game is within its 16-day forecast window.

SHOWN, NEVER SCORED. Betting totals and expert projections move with the
forecast during the week, so scoring weather again would double count. It is
here so a windy Sunday does not catch you starting a kicker in a gale.
"""

import json
import os
import time

import requests

import commentary
import outside_rankings
import status as game_status


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_DIR = "cache"
FORECAST_CACHE_HOURS = 3
FORECAST_DAYS = 16

WINDY_MPH = 15
RAIN_LIKELY = 60      # percent chance of precipitation
COLD_F = 25

# Who each kind of weather actually hurts.
HURT_BY = {
    "wind": {"K", "QB", "WR", "TE"},
    "rain": {"K", "QB", "WR"},
    "cold": {"K"},
}


def _cached_json(name, max_age_hours, fetch):
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path) and (max_age_hours is None or time.time() - os.path.getmtime(path) < max_age_hours * 3600):
        try:
            with open(path) as handle:
                return json.load(handle)
        except (OSError, ValueError):
            pass
    try:
        data = fetch()
    except Exception:
        data = None
    if data is not None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w") as handle:
            json.dump(data, handle)
    return data


def geocode(city, state=None, country=None):
    """(latitude, longitude) for a venue city, cached permanently."""
    key = "_".join(x for x in (city, state, country) if x).replace(" ", "-").replace("/", "-")

    def fetch():
        response = requests.get(GEOCODE_URL, params={"name": city, "count": 10}, timeout=20)
        response.raise_for_status()
        return pick_place(response.json().get("results") or [], state, country)

    data = _cached_json(f"geo_{key}.json", None, fetch)
    return (data["lat"], data["lon"]) if data else None


US_STATES = {
    "AL": "Alabama", "AZ": "Arizona", "CA": "California", "CO": "Colorado", "FL": "Florida",
    "GA": "Georgia", "IL": "Illinois", "IN": "Indiana", "LA": "Louisiana", "MA": "Massachusetts",
    "MD": "Maryland", "MI": "Michigan", "MN": "Minnesota", "MO": "Missouri", "NC": "North Carolina",
    "NJ": "New Jersey", "NV": "Nevada", "NY": "New York", "OH": "Ohio", "PA": "Pennsylvania",
    "TN": "Tennessee", "TX": "Texas", "WA": "Washington", "WI": "Wisconsin",
}


def pick_place(results, state=None, country=None):
    """
    The geocoder's best match for a venue city: in the right US state when
    ESPN gives one (there are a lot of Springfields), else the top result.
    """
    if not results:
        return None
    state_name = US_STATES.get(state or "")
    for result in results:
        if state_name and result.get("country_code") == "US" and result.get("admin1") == state_name:
            return {"lat": result["latitude"], "lon": result["longitude"]}
    if country in ("USA", "US"):
        for result in results:
            if result.get("country_code") == "US":
                return {"lat": result["latitude"], "lon": result["longitude"]}
    return {"lat": results[0]["latitude"], "lon": results[0]["longitude"]}


def venues(season, week):
    """{team code: {"city", "state", "country", "indoor", "kickoff"}} for the week."""
    data = commentary.get_json(game_status.SCOREBOARD_URL % (week, season))
    out = {}
    for event in (data or {}).get("events") or []:
        for competition in event.get("competitions") or []:
            venue = competition.get("venue") or {}
            address = venue.get("address") or {}
            kickoff = game_status.parse_time(event.get("date"))
            for competitor in competition.get("competitors") or []:
                code = outside_rankings.normalize_team((competitor.get("team") or {}).get("abbreviation"))
                out[code] = {
                    "city": address.get("city"),
                    "state": address.get("state"),
                    "country": address.get("country"),
                    "indoor": bool(venue.get("indoor")),
                    "kickoff": kickoff,
                }
    return out


def forecast_at(lat, lon, kickoff):
    """Wind, gusts, rain chance and temperature for the kickoff hour, or None."""
    if kickoff is None:
        return None
    hours_away = (kickoff.timestamp() - time.time()) / 3600
    if hours_away > FORECAST_DAYS * 24 or hours_away < -4:
        return None

    def fetch():
        response = requests.get(FORECAST_URL, params={
            "latitude": round(lat, 2), "longitude": round(lon, 2),
            "hourly": "wind_speed_10m,wind_gusts_10m,precipitation_probability,temperature_2m",
            "wind_speed_unit": "mph", "temperature_unit": "fahrenheit",
            "timezone": "UTC", "forecast_days": FORECAST_DAYS,
        }, timeout=20)
        response.raise_for_status()
        return response.json()

    data = _cached_json(f"forecast_{round(lat, 2)}_{round(lon, 2)}.json", FORECAST_CACHE_HOURS, fetch)
    hourly = (data or {}).get("hourly") or {}
    target = kickoff.strftime("%Y-%m-%dT%H:00")
    try:
        index = hourly["time"].index(target)
    except (KeyError, ValueError):
        return None
    return {
        "wind_mph": hourly["wind_speed_10m"][index],
        "gust_mph": hourly["wind_gusts_10m"][index],
        "rain_chance": hourly["precipitation_probability"][index],
        "temp_f": hourly["temperature_2m"][index],
    }


def conditions(forecast):
    """Which weather worth mentioning is expected: a set of 'wind', 'rain', 'cold'."""
    if not forecast:
        return set()
    found = set()
    if (forecast.get("wind_mph") or 0) >= WINDY_MPH:
        found.add("wind")
    if (forecast.get("rain_chance") or 0) >= RAIN_LIKELY:
        found.add("rain")
    if forecast.get("temp_f") is not None and forecast["temp_f"] <= COLD_F:
        found.add("cold")
    return found


def describe(forecast, found):
    if not forecast or not found:
        return None
    parts = []
    if "wind" in found:
        parts.append(f"wind {forecast['wind_mph']:.0f} mph (gusts {forecast['gust_mph']:.0f})")
    if "rain" in found:
        parts.append(f"{forecast['rain_chance']:.0f}% chance of rain/snow")
    if "cold" in found:
        parts.append(f"{forecast['temp_f']:.0f}°F")
    return "weather: " + ", ".join(parts)


def by_team(season, week):
    """{team code: {"forecast", "conditions", "text"}} -- indoor games left out."""
    out = {}
    places = {}
    for team, venue in venues(season, week).items():
        if venue["indoor"] or not venue["city"]:
            continue
        spot = (venue["city"], venue["state"], venue["country"])
        if spot not in places:
            places[spot] = geocode(*spot)
        if not places[spot]:
            continue
        forecast = forecast_at(*places[spot], venue["kickoff"])
        found = conditions(forecast)
        out[team] = {"forecast": forecast, "conditions": sorted(found), "text": describe(forecast, found)}
    return out


def attach(players, season, week):
    """`weather` (a sentence, or None) on each player it could actually affect."""
    try:
        table = by_team(season, week)
    except Exception:
        table = {}
    for player in players:
        entry = table.get(outside_rankings.normalize_team(player.get("pro_team") or player.get("team")))
        affected = entry and any(player.get("position") in HURT_BY[c] for c in entry["conditions"])
        player["weather"] = entry["text"] if affected else None
    return players
