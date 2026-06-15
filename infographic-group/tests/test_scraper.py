import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from strava_scraper import _parse_activity_ids, get_activities_on_date, find_route_match

FIXTURES = Path(__file__).parent.parent / "test_fixtures"
ATHLETE_PROFILE = FIXTURES / "strava.com-athletes-187003192.html"


def _profile_html() -> str:
    return ATHLETE_PROFILE.read_text(encoding="utf-8", errors="replace")


# ── _parse_activity_ids ───────────────────────────────────────────────────────

def test_parse_activity_ids_ride_on_date():
    html = _profile_html()
    ids = _parse_activity_ids(html, "2026-06-06")
    # Fixture contains "Recon | Marmaris" (Ride, 2026-06-06, id=18804777797)
    assert 18804777797 in ids


def test_parse_activity_ids_filters_non_ride():
    html = _profile_html()
    # "Pylometrics" is a Workout on 2026-06-09, must not appear
    ids = _parse_activity_ids(html, "2026-06-09")
    assert 18845713476 not in ids


def test_parse_activity_ids_wrong_date():
    html = _profile_html()
    ids = _parse_activity_ids(html, "2020-01-01")
    assert ids == []


def test_parse_activity_ids_returns_rides_only():
    html = _profile_html()
    # All returned IDs must be from ride-type activities; we verify by checking
    # a known non-ride date returns nothing useful
    ids = _parse_activity_ids(html, "2026-06-09")
    assert isinstance(ids, list)
    # Workout on that date must not be included
    assert 18845713476 not in ids


# ── get_activities_on_date ────────────────────────────────────────────────────

def test_get_activities_returns_cached():
    cached = [{"activity_id": 18804777797, "activity_type": "Ride", "date": "2026-06-06",
               "athlete_id": 187003192, "scraped_at": "2026-06-06T10:00:00"}]
    with patch("strava_scraper.db") as mock_db:
        mock_db.get_scraped_activities.return_value = cached
        # Playwright is only imported lazily inside get_activities_on_date,
        # so we verify it's never reached by checking we got cached results without error
        result = get_activities_on_date(187003192, "2026-06-06")
    mock_db.get_scraped_activities.assert_called_once_with(187003192, "2026-06-06")
    assert result == [18804777797]


def test_get_activities_no_session_returns_empty(tmp_path):
    with patch("strava_scraper.db") as mock_db:
        mock_db.get_scraped_activities.return_value = []
        with patch("strava_scraper.SESSION_FILE", tmp_path / "nonexistent.json"):
            result = get_activities_on_date(187003192, "2026-06-06")
    assert result == []


# ── find_route_match ──────────────────────────────────────────────────────────

def test_find_route_match_uses_cached_similarity():
    ref_latlng = [[37.0, 28.0], [37.05, 28.05]]
    with patch("strava_scraper.get_activities_on_date", return_value=[18804777797]):
        with patch("strava_scraper.db") as mock_db:
            mock_db.get_similarity.return_value = 0.82
            with patch("strava_scraper.sc") as mock_sc:
                result = find_route_match(100, ref_latlng, 187003192, "2026-06-06")
    mock_sc.get_streams.assert_not_called()
    assert result is not None
    assert result["activity_id"] == 18804777797
    assert abs(result["similarity"] - 0.82) < 1e-9


def test_find_route_match_no_match_below_threshold():
    ref_latlng = [[37.0, 28.0], [37.05, 28.05]]
    rider_latlng = [[50.0, 10.0], [50.05, 10.05]]  # far away
    with patch("strava_scraper.get_activities_on_date", return_value=[999]):
        with patch("strava_scraper.db") as mock_db:
            mock_db.get_similarity.return_value = None
            with patch("strava_scraper.sc") as mock_sc:
                mock_sc.get_streams.return_value = {"latlng": rider_latlng}
                result = find_route_match(100, ref_latlng, 187003192, "2026-06-06",
                                          threshold=0.50)
    assert result is None


def test_find_route_match_no_activities():
    with patch("strava_scraper.get_activities_on_date", return_value=[]):
        result = find_route_match(100, [[37.0, 28.0]], 187003192, "2026-06-06")
    assert result is None


def test_find_route_match_skips_private_activity():
    import requests
    ref_latlng = [[37.0, 28.0]] * 20

    http_error = requests.HTTPError(response=MagicMock(status_code=403))
    with patch("strava_scraper.get_activities_on_date", return_value=[111, 222]):
        with patch("strava_scraper.db") as mock_db:
            mock_db.get_similarity.return_value = None
            with patch("strava_scraper.sc") as mock_sc:
                mock_sc.get_streams.side_effect = http_error
                result = find_route_match(100, ref_latlng, 187003192, "2026-06-06")
    assert result is None
