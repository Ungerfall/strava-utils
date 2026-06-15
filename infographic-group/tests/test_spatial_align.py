import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from strava_client import summarize_streams_aligned, _find_idx_at_distance, _nearest_idx_and_dist
from chart_renderer import _interpolate_nones


# ── _find_idx_at_distance ─────────────────────────────────────────────────────

def test_find_idx_exact():
    dist = [0, 1000, 2000, 3000, 4000]
    assert _find_idx_at_distance(dist, 2000) == 2


def test_find_idx_between():
    dist = [0, 1000, 2000, 3000]
    # 1500 is between index 1 and 2; binary search lands on 2 (first >= 1500)
    assert _find_idx_at_distance(dist, 1500) == 2


def test_find_idx_beyond_end():
    dist = [0, 1000, 2000]
    assert _find_idx_at_distance(dist, 5000) == 2


# ── _nearest_idx_and_dist ─────────────────────────────────────────────────────

def test_nearest_exact_match():
    latlng = [[37.0, 28.0], [37.1, 28.1], [37.2, 28.2]]
    idx, dist = _nearest_idx_and_dist(latlng, 37.1, 28.1)
    assert idx == 1
    assert dist < 1.0  # essentially zero


def test_nearest_closest_point():
    latlng = [[37.0, 28.0], [37.05, 28.05], [37.2, 28.2]]
    idx, dist = _nearest_idx_and_dist(latlng, 37.04, 28.04)
    assert idx == 1  # closest to (37.05, 28.05)


# ── summarize_streams_aligned ─────────────────────────────────────────────────

def _make_straight_track(lat0, lon0, lat1, lon1, n):
    return [[lat0 + (lat1 - lat0) * i / (n - 1),
             lon0 + (lon1 - lon0) * i / (n - 1)] for i in range(n)]


def _make_distance(n_points, total_m):
    return [total_m * i / (n_points - 1) for i in range(n_points)]


def test_full_overlap_returns_values():
    """Rider rode the entire reference route — all km positions have data."""
    n = 300
    ref_latlng = _make_straight_track(37.0, 28.0, 37.27, 28.27, n)  # ~30 km
    ref_dist = _make_distance(n, 30_000)

    rider_latlng = ref_latlng[:]   # same track
    cadence = [90] * n
    rider_streams = {"latlng": rider_latlng, "cadence": cadence}

    result = summarize_streams_aligned(ref_latlng, ref_dist, rider_streams, False)
    assert "cadence" in result
    assert len(result["cadence"]) == 30
    assert all(v is not None for v in result["cadence"])


def test_late_join_produces_leading_nones():
    """Rider joined halfway — first half of reference km positions should be None."""
    n = 300
    ref_latlng = _make_straight_track(37.0, 28.0, 37.27, 28.27, n)
    ref_dist = _make_distance(n, 30_000)

    # Rider only covered the second half of the route (km 15–30)
    rider_latlng = ref_latlng[150:]
    cadence = [85] * len(rider_latlng)
    rider_streams = {"latlng": rider_latlng, "cadence": cadence}

    result = summarize_streams_aligned(ref_latlng, ref_dist, rider_streams, False,
                                       max_snap_m=100.0)
    assert "cadence" in result
    km_vals = result["cadence"]
    assert len(km_vals) == 30
    # First ~15 km should be None (rider not present)
    assert all(v is None for v in km_vals[:13])
    # Last ~15 km should have values
    assert all(v is not None for v in km_vals[16:])


def test_early_leave_produces_trailing_nones():
    """Rider left at halfway — second half of reference positions should be None."""
    n = 300
    ref_latlng = _make_straight_track(37.0, 28.0, 37.27, 28.27, n)
    ref_dist = _make_distance(n, 30_000)

    rider_latlng = ref_latlng[:150]
    cadence = [80] * len(rider_latlng)
    rider_streams = {"latlng": rider_latlng, "cadence": cadence}

    result = summarize_streams_aligned(ref_latlng, ref_dist, rider_streams, False,
                                       max_snap_m=100.0)
    km_vals = result["cadence"]
    assert all(v is not None for v in km_vals[:13])
    assert all(v is None for v in km_vals[16:])


def test_disjoint_track_all_nones():
    """Rider was on a completely different route — all None."""
    n = 100
    ref_latlng = _make_straight_track(37.0, 28.0, 37.1, 28.1, n)
    ref_dist = _make_distance(n, 10_000)

    rider_latlng = _make_straight_track(50.0, 10.0, 50.1, 10.1, n)
    rider_streams = {"latlng": rider_latlng, "cadence": [90] * n}

    result = summarize_streams_aligned(ref_latlng, ref_dist, rider_streams, False,
                                       max_snap_m=100.0)
    assert all(v is None for v in result.get("cadence", [None]))


def test_power_excluded_without_device_watts():
    n = 100
    ref_latlng = _make_straight_track(37.0, 28.0, 37.09, 28.09, n)
    ref_dist = _make_distance(n, 9_000)
    rider_streams = {"latlng": ref_latlng, "watts": [200] * n, "cadence": [90] * n}

    result = summarize_streams_aligned(ref_latlng, ref_dist, rider_streams, False)
    assert "watts" not in result
    assert "cadence" in result


def test_power_included_with_device_watts():
    n = 100
    ref_latlng = _make_straight_track(37.0, 28.0, 37.09, 28.09, n)
    ref_dist = _make_distance(n, 9_000)
    rider_streams = {"latlng": ref_latlng, "watts": [200] * n}

    result = summarize_streams_aligned(ref_latlng, ref_dist, rider_streams, True)
    assert "watts" in result


def test_empty_inputs_return_empty():
    result = summarize_streams_aligned([], [], {"latlng": [], "cadence": []}, False)
    assert result == {}


# ── _interpolate_nones ────────────────────────────────────────────────────────

def test_interpolate_small_gap_filled():
    vals = [10.0, None, None, 10.0]
    result = _interpolate_nones(vals, max_gap=3)
    assert all(v is not None for v in result)


def test_interpolate_large_gap_preserved():
    vals = [10.0, None, None, None, None, None, 10.0]  # gap of 5
    result = _interpolate_nones(vals, max_gap=3)
    # Nones in the middle should remain
    assert any(v is None for v in result[1:6])


def test_interpolate_exact_boundary():
    # Gap of exactly max_gap should be filled
    vals = [5.0, None, None, None, 5.0]  # gap of 3
    result = _interpolate_nones(vals, max_gap=3)
    assert all(v is not None for v in result)


def test_interpolate_no_nones_unchanged():
    vals = [1.0, 2.0, 3.0]
    assert _interpolate_nones(vals) == [1.0, 2.0, 3.0]


def test_interpolate_leading_none_uses_next():
    vals = [None, None, 5.0, 6.0]
    result = _interpolate_nones(vals, max_gap=3)
    assert result[0] is not None
    assert result[1] is not None


def test_interpolate_trailing_none_uses_prev():
    vals = [5.0, 6.0, None, None]
    result = _interpolate_nones(vals, max_gap=3)
    assert result[2] is not None
    assert result[3] is not None


def test_interpolate_multiple_independent_gaps():
    # Small gap + large gap — only small one is filled
    vals = [10.0, None, 10.0, None, None, None, None, 10.0]
    result = _interpolate_nones(vals, max_gap=2)
    assert result[1] is not None        # small gap filled
    assert any(v is None for v in result[3:7])  # large gap preserved
