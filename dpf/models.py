"""Forecasting methods. Every method predicts the change in log level over h months, with quantiles.

- no_change:   next year's level = today's level (the honest "do nothing" benchmark)
- last_trend:  this segment keeps moving as it did over the last 12 months
- dubai_trend: every area moves like Dubai as a whole did over the last 12 months
- ets:         a classic per-series exponential smoothing model (statsforecast AutoETS)
- gbm:         one gradient-boosted model (LightGBM) trained across all segments, horizons 1-12

Ranges for the simple methods come from their own past errors at the same horizon. Ranges for the
gradient-boosted model come from quantile models, then corrected on the most recent 12 months of
known outcomes so that, in recent history, 80% of real outcomes fell inside the 80% range.
"""
import warnings

import numpy as np
import pandas as pd

from . import config as C
from .features import FEATURES

Q = list(C.QUANTILES)
QCOLS = [f"q{int(q * 100):02d}" for q in Q]
HGROUP = lambda h: (np.asarray(h) - 1) // 3      # 1-3, 4-6, 7-9, 10-12 months ahead


def _with_ranges(test, train, point_test, point_train):
    """Simple-method ranges: quantiles of that method's own past errors, per horizon group."""
    out = pd.DataFrame(index=test.index)
    err = (train["y"] - point_train).groupby(HGROUP(train["h"])).quantile(Q).unstack()
    err = err.sub(err[0.5], axis=0)          # the method's own forecast stays the middle of its range
    g = HGROUP(test["h"])
    for q, c in zip(Q, QCOLS):
        out[c] = point_test + err[q].reindex(g).values
    return out


def no_change(train, test):
    return _with_ranges(test, train, np.zeros(len(test)), np.zeros(len(train)))


def last_trend(train, test):
    f = lambda d: d["r12"].fillna(0).values * d["h"].values / 12
    return _with_ranges(test, train, f(test), f(train))


def dubai_trend(train, test):
    f = lambda d: d["dubai_all_r12"].fillna(0).values * d["h"].values / 12
    return _with_ranges(test, train, f(test), f(train))


def ets(panel, train, test):
    """Per-series AutoETS on the log level, fitted on the months up to the origin."""
    from statsforecast import StatsForecast
    from statsforecast.models import AutoETS

    origin = test["origin"].iloc[0]
    t = panel.col(origin)
    rows = test["row"].unique()
    hist = panel.L[rows, max(0, t - 95):t + 1]
    recs = []
    for r, series in zip(rows, hist):
        s = pd.Series(series).interpolate(limit_area="inside")
        s = s[s.first_valid_index():] if s.first_valid_index() is not None else s.iloc[:0]
        if len(s) < 24 or s.isna().any():
            continue
        ds = pd.period_range(end=origin, periods=len(s), freq="M").to_timestamp()
        recs.append(pd.DataFrame({"unique_id": r, "ds": ds, "y": s.values}))
    point = pd.Series(0.0, index=test.index)
    if recs:
        df = pd.concat(recs, ignore_index=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sf = StatsForecast(models=[AutoETS(season_length=12, model="ZZN")], freq="MS", n_jobs=1)
            fc = sf.forecast(df=df, h=C.HORIZON)
        fc["h"] = fc.groupby("unique_id").cumcount() + 1
        last = df.groupby("unique_id")["y"].last()
        fc["chg"] = fc["AutoETS"].values - last.reindex(fc["unique_id"]).values
        m = fc.set_index(["unique_id", "h"])["chg"]
        key = pd.MultiIndex.from_arrays([test["row"].values, test["h"].values])
        point = pd.Series(m.reindex(key).fillna(0.0).values, index=test.index)
    # ranges: reuse the no-change error spread around the ETS point (ETS ranges are too narrow on this data)
    out = _with_ranges(test, train, point.values, np.zeros(len(train)))
    return out


GBM_PARAMS = dict(
    n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=300,
    subsample=0.7, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
    verbose=-1, n_jobs=4,
)


def _fit_quantiles(train, seed=0, max_rows=600_000):
    import lightgbm as lgb

    if len(train) > max_rows:   # keep training fast; recent rows are kept preferentially
        recent = train["origin"] >= sorted(train["origin"].unique())[-36] if train["origin"].nunique() > 36 else train["origin"].notna()
        keep = train[recent]
        rest = train[~recent]
        n_rest = max(0, max_rows - len(keep))
        train = pd.concat([keep, rest.sample(min(n_rest, len(rest)), random_state=seed)])
    models = {}
    for q in Q:
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, random_state=seed, **GBM_PARAMS)
        m.fit(train[FEATURES], train["y"], sample_weight=train["weight"])
        models[q] = m
    return models


def _predict(models, X):
    P = np.column_stack([models[q].predict(X[FEATURES]) for q in Q])
    return np.sort(P, axis=1)   # quantiles must not cross


def conformal_widths(pred: np.ndarray, y: np.ndarray, h: np.ndarray) -> dict:
    """How much to widen (or narrow) the 50% and 80% ranges, per horizon group, so recent coverage is right."""
    out = {}
    for g in np.unique(HGROUP(h)):
        sel = HGROUP(h) == g
        p, yy = pred[sel], y[sel]
        n = len(yy)
        widths = {}
        for lo, hi, cover in ((0, 4, 0.8), (1, 3, 0.5)):
            score = np.maximum(p[:, lo] - yy, yy - p[:, hi])
            level = min(1.0, np.ceil((n + 1) * cover) / n)
            widths[(lo, hi)] = float(np.quantile(score, level))
        out[int(g)] = widths
    return out


def apply_widths(pred: np.ndarray, h: np.ndarray, widths: dict) -> np.ndarray:
    P = pred.copy()
    for g, w in widths.items():
        sel = HGROUP(h) == g
        for (lo, hi), d in w.items():
            P[sel, lo] -= d
            P[sel, hi] += d
    return np.sort(P, axis=1)


def gbm(train, test, origin_col, calibrate=True, seed=0, return_models=False):
    """Fit on outcomes known at the origin. Calibration: refit without the last 12 months of outcomes,
    measure coverage on those months, then apply the correction to the full model's ranges."""
    tcol = train["t"] + train["h"]
    widths = None
    if calibrate:
        fit = train[tcol <= origin_col - 12]
        cal = train[tcol > origin_col - 12]
        if len(fit) > 1000 and len(cal) > 200:
            mc = _fit_quantiles(fit, seed)
            widths = conformal_widths(_predict(mc, cal), cal["y"].values, cal["h"].values)
    models = _fit_quantiles(train, seed)
    P = _predict(models, test)
    if widths:
        P = apply_widths(P, test["h"].values, widths)
    out = pd.DataFrame(P, columns=QCOLS, index=test.index)
    if return_models:
        return out, models, widths
    return out


METHODS = ["no_change", "last_trend", "dubai_trend", "ets", "gbm"]
LABELS = {
    "no_change": "No change (today's level)",
    "last_trend": "Last year's trend continues",
    "dubai_trend": "Dubai-wide trend applied to every area",
    "ets": "Exponential smoothing, per series (ETS)",
    "gbm": "Gradient boosting across all areas (LightGBM)",
}
