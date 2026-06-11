import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from strava_scraper import gps_similarity


def _line(lat_start, lon_start, lat_end, lon_end, n=100):
    return [
        [lat_start + (lat_end - lat_start) * i / (n - 1),
         lon_start + (lon_end - lon_start) * i / (n - 1)]
        for i in range(n)
    ]


def test_identical_tracks():
    track = _line(37.0, 28.0, 37.1, 28.1)
    assert gps_similarity(track, track) == 1.0


def test_disjoint_tracks():
    track_a = _line(37.0, 28.0, 37.1, 28.1)
    track_b = _line(50.0, 10.0, 50.1, 10.1)  # far away
    assert gps_similarity(track_a, track_b) < 0.05


def test_subset_track():
    full = _line(37.0, 28.0, 37.2, 28.2, n=200)
    half = full[:100]  # exact first half — same geographic points
    score = gps_similarity(full, half)
    # rev fraction = 1.0 (all half points are in full); max(fwd~0.5, rev=1.0) = 1.0
    assert score >= 0.45


def test_single_point_tracks():
    a = [[37.0, 28.0]]
    b = [[37.0, 28.0]]
    assert gps_similarity(a, b) == 1.0


def test_empty_tracks():
    assert gps_similarity([], [[37.0, 28.0]]) == 0.0
    assert gps_similarity([[37.0, 28.0]], []) == 0.0
    assert gps_similarity([], []) == 0.0


def test_threshold_respected():
    # Two parallel lines ~100m apart — beyond 25m threshold, within 150m threshold
    import math
    deg_100m = 100 / 111_000
    track_a = _line(37.0, 28.0, 37.1, 28.0)
    track_b = _line(37.0, 28.0 + deg_100m, 37.1, 28.0 + deg_100m)
    score_strict = gps_similarity(track_a, track_b, threshold_m=25.0)
    score_loose = gps_similarity(track_a, track_b, threshold_m=150.0)
    assert score_strict < 0.1
    assert score_loose > 0.9
