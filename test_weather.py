"""
Checks weather rules and the city matching -- no network.

Run with:  .venv/bin/python test_weather.py
"""

import weather


def test_thresholds():
    calm = {"wind_mph": 8, "gust_mph": 12, "rain_chance": 20, "temp_f": 60}
    storm = {"wind_mph": 21, "gust_mph": 34, "rain_chance": 80, "temp_f": 18}
    assert weather.conditions(calm) == set()
    assert weather.conditions(storm) == {"wind", "rain", "cold"}
    assert weather.conditions(None) == set()


def test_describe_only_mentions_what_matters():
    windy = {"wind_mph": 18.4, "gust_mph": 29.6, "rain_chance": 10, "temp_f": 55}
    text = weather.describe(windy, weather.conditions(windy))
    assert text == "weather: wind 18 mph (gusts 30)", text
    assert weather.describe(windy, set()) is None


def test_the_right_springfield():
    results = [
        {"latitude": 1, "longitude": 1, "country_code": "US", "admin1": "Missouri"},
        {"latitude": 2, "longitude": 2, "country_code": "US", "admin1": "Massachusetts"},
    ]
    assert weather.pick_place(results, "MA", "USA") == {"lat": 2, "lon": 2}
    assert weather.pick_place(results, None, "USA") == {"lat": 1, "lon": 1}
    assert weather.pick_place([], "MA", "USA") is None


def test_only_affected_positions_get_a_note(monkeypatch=None):
    original = weather.by_team
    weather.by_team = lambda season, week: {
        "BUF": {"forecast": {}, "conditions": ["wind"], "text": "weather: wind 22 mph (gusts 35)"},
    }
    try:
        players = [{"position": "K", "pro_team": "BUF"}, {"position": "RB", "pro_team": "BUF"},
                   {"position": "K", "pro_team": "MIA"}]
        weather.attach(players, 2026, 2)
        assert [p["weather"] is not None for p in players] == [True, False, False]
    finally:
        weather.by_team = original


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} weather tests passed.")
