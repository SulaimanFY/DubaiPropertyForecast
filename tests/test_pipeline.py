import numpy as np
import pandas as pd

from dpf import aggregate as A
from dpf import config as C
from dpf import models as M
from dpf import validate as V
from dpf.features import FEATURES, all_origins, known_at, origin_frame
from dpf.panel import build


def test_rollups_count_every_deal(deals):
    s = A.monthly_stats(deals)
    total = len(deals)
    dub_all = s[(s.area_id == C.DUBAI) & (s.beds == C.ALL)]
    assert dub_all["n"].sum() == total
    assert s[(s.area_id != C.DUBAI) & (s.beds != C.ALL)]["n"].sum() == total


def test_trimming_drops_extremes_each_side():
    df = pd.DataFrame({"measure": "rent", "month": "2024-01", "area_id": "X", "ptype": "apartment", "beds": "1",
                       "ppsf": [1.0] + [100.0] * 38 + [10_000.0], "size_sqft": 800.0, "amount": 1.0, "offplan": False})
    s = A.monthly_stats(df)
    row = s[(s.area_id == "X") & (s.beds == "1")].iloc[0]
    assert row.n == 40 and row.n_trim == 36           # 5% of 40 = 2 dropped on each side
    assert np.isclose(np.exp(row.sum_log / row.n_trim), 100.0)


def test_merge_replaces_only_new_months(deals):
    s = A.monthly_stats(deals)
    newer = s[s["month"] == s["month"].max()].copy()
    newer["n"] = newer["n"] + 1
    merged = A.merge(s, newer)
    assert len(merged) == len(s)
    last = merged[merged["month"] == s["month"].max()]
    assert (last["n"].values == newer.sort_values(A.KEYS)["n"].values).all()


def test_level_is_pooled_three_months(deals):
    s = A.monthly_stats(deals)
    p = build(s)
    sid = "rent|AREA A|apartment|1"
    row = p.seg.index[p.seg["sid"] == sid][0]
    g = s[(s.measure == "rent") & (s.area_id == "AREA A") & (s.ptype == "apartment") & (s.beds == "1")].sort_values("month")
    t = 10
    expect = g["sum_log"].iloc[t - 2:t + 1].sum() / g["n_trim"].iloc[t - 2:t + 1].sum()
    assert np.isclose(p.L[row, t], expect)


def test_features_do_not_look_ahead(deals):
    """Changing every month after the origin must not change the features at the origin."""
    s = A.monthly_stats(deals)
    p = build(s)
    t = 40
    a = origin_frame(p, t, with_target=False)
    p.L[:, t + 1:] += 0.5
    p.N3[:, t + 1:] *= 3
    b = origin_frame(p, t, with_target=False)
    pd.testing.assert_frame_equal(a[FEATURES], b[FEATURES])


def test_training_rows_only_use_known_outcomes(deals):
    p = build(A.monthly_stats(deals))
    frame = all_origins(p)
    T0 = 50
    tr = known_at(frame, T0)
    assert (tr["t"] + tr["h"] <= T0).all() and tr["y"].notna().all()


def test_conformal_widths_reach_target_coverage():
    rng = np.random.default_rng(1)
    n = 4000
    y = rng.normal(0, 1, n)
    pred = np.tile(np.array([-0.3, -0.2, 0, 0.2, 0.3]), (n, 1))   # far too narrow on purpose
    h = rng.integers(1, 13, n)
    w = M.conformal_widths(pred, y, h)
    P = M.apply_widths(pred, h, w)
    cov80 = ((y >= P[:, 0]) & (y <= P[:, 4])).mean()
    cov50 = ((y >= P[:, 1]) & (y <= P[:, 3])).mean()
    assert 0.78 <= cov80 <= 0.83 and 0.48 <= cov50 <= 0.53


def test_quality_checks_fail_on_bad_data():
    good = V.quality_checks({"rent": {"rows": 1000, "missing": 10, "out_of_bounds": 5, "duplicates": 0}})
    assert not V.failed(good)
    bad = V.quality_checks({"rent": {"rows": 1000, "missing": 400, "out_of_bounds": 5, "duplicates": 50}})
    names = {c["check"] for c in V.failed(bad)}
    assert {"missing area, size or amount", "duplicate records"} <= names


def test_volume_check_catches_a_collapse(deals):
    s = A.monthly_stats(deals)
    last = s["month"].max()
    crashed = s.copy()
    crashed.loc[crashed["month"] == last, "n"] = 1
    checks = V.history_checks(crashed[crashed["month"] == last], crashed, last)
    assert any(c["status"] == "fail" and c["check"].startswith("deal count") for c in checks)


def test_simple_methods_give_ordered_quantiles(deals):
    p = build(A.monthly_stats(deals))
    frame = all_origins(p)
    T0 = 60
    train, test = known_at(frame, T0), frame[frame["t"] == T0]
    for f in (M.no_change, M.last_trend, M.dubai_trend):
        q = f(train, test)[M.QCOLS].values
        assert (np.diff(q, axis=1) >= -1e-12).all()
