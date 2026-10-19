"""This month's forecast, plus the public archive of every past forecast."""
import numpy as np
import pandas as pd

from . import config as C
from . import models as M
from .features import known_at
from .panel import Panel


def publishable(p: Panel, t: int) -> np.ndarray:
    lo = max(0, t - 47)
    history = (~np.isnan(p.L[:, lo:t + 1])).sum(axis=1)
    return (p.N3[:, t] >= C.MIN_DEALS_PUBLISH) & (history >= C.MIN_HISTORY_MONTHS) & ~np.isnan(p.L[:, t])


def make(p: Panel, frame: pd.DataFrame, seed=0):
    """Returns (forecast rows, recent error of the calibration model, calibration widths)."""
    T0 = len(p.months) - 1
    train = known_at(frame, T0)
    ok = publishable(p, T0)
    test = frame[(frame["t"] == T0) & ok[frame["row"].clip(lower=0)]]
    # calibration model: trained without the last 12 months of outcomes, scored on them
    tcol = train["t"] + train["h"]
    fit, cal = train[tcol <= T0 - 12], train[tcol > T0 - 12]
    mc = M._fit_quantiles(fit, seed)
    pc = M._predict(mc, cal)
    widths = M.conformal_widths(pc, cal["y"].values, cal["h"].values)
    cal_pub = cal["log_deals"].values >= np.log1p(C.MIN_DEALS_PUBLISH)
    recent_error = float(np.median(np.abs(np.exp(pc[cal_pub, 2] - cal["y"].values[cal_pub]) - 1)))
    models = M._fit_quantiles(train, seed)
    P = M.apply_widths(M._predict(models, test), test["h"].values, widths)

    out = test[["sid", "row", "origin", "h"]].copy().reset_index(drop=True)
    out[M.QCOLS] = P
    out["target_month"] = [str(pd.Period(o, freq="M") + h) for o, h in zip(out["origin"], out["h"])]
    out["level_now"] = np.exp(p.L[out["row"], T0])
    out["typical_size"] = p.SIZE12[out["row"], T0]
    out["typical_amount"] = p.AMT12[out["row"], T0]
    importance = pd.Series(models[0.5].booster_.feature_importance("gain"), index=models[0.5].feature_name_)
    return out.drop(columns="row"), recent_error, widths, importance.sort_values(ascending=False)


def archive_path(origin: str):
    return C.FORECAST_DIR / f"forecast_{origin}.csv.gz"


def save(fc: pd.DataFrame, overwrite=False) -> bool:
    """Each month's forecast is written once and never changed, so the scorecard cannot be rewritten later."""
    C.FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    origin = fc["origin"].iloc[0]
    path = archive_path(origin)
    if path.exists() and not overwrite:
        return False
    cols = ["sid", "origin", "h", "target_month"] + M.QCOLS + ["level_now"]
    out = fc[cols].copy()
    for c in M.QCOLS:
        out[c] = out[c].round(5)
    out["level_now"] = out["level_now"].round(2)
    out.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    return True


def load_archive() -> pd.DataFrame:
    files = sorted(C.FORECAST_DIR.glob("forecast_*.csv.gz"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f, dtype={"origin": str, "target_month": str}) for f in files], ignore_index=True)


def live_scorecard(p: Panel) -> pd.DataFrame:
    """Every archived forecast whose target month has now happened, with the real outcome."""
    a = load_archive()
    if a.empty:
        return a
    rows = pd.Series(np.arange(len(p.seg)), index=p.seg["sid"])
    cols = pd.Series(np.arange(len(p.months)), index=p.months)
    a = a[a["target_month"].isin(cols.index) & a["sid"].isin(rows.index)].copy()
    if a.empty:
        return a
    actual = p.L[rows[a["sid"]].values, cols[a["target_month"]].values]
    a["actual_level"] = np.exp(actual)
    a["y"] = actual - np.log(a["level_now"])
    return a[a["y"].notna()]
