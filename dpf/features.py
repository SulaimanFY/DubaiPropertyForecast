"""Model inputs. Everything here is computed from months up to the forecast origin only (no peeking ahead)."""
import numpy as np
import pandas as pd

from . import config as C
from .panel import Panel

BEDS_CODE = {b: i for i, b in enumerate(C.BEDS)} | {C.ALL: len(C.BEDS)}

FEATURES = [
    "h", "target_moy", "is_price", "is_villa", "beds_code", "is_dubai",
    "r1", "r3", "r6", "r12", "r24", "vol12", "same_period_last_year",
    "parent_r3", "parent_r12", "dubai_r3", "dubai_r12", "dubai_all_r12", "dubai_all_r24", "dubai_dev60",
    "rel_dubai", "log_deals", "deals_change12", "log_yield", "yield_change12", "offplan_share",
]


def _lag(L, t, k):
    return L[:, t - k] if t - k >= 0 else np.full(L.shape[0], np.nan)


def _rows(arr, rows):
    out = np.full(len(rows), np.nan)
    ok = rows >= 0
    out[ok] = arr[rows[ok]]
    return out


def origin_frame(p: Panel, t: int, horizons=range(1, C.HORIZON + 1), with_target=True) -> pd.DataFrame:
    """All eligible segments at origin column t, one row per (segment, horizon)."""
    L, S, T = p.L, p.L.shape[0], p.L.shape[1]
    cur = L[:, t]
    ok = ~np.isnan(cur) & ~np.isnan(_lag(L, t, 12))
    if not ok.any():
        return pd.DataFrame()

    def r(k, rows=None):
        x = cur - _lag(L, t, k)
        return x if rows is None else _rows(L[:, t], rows) - _rows(_lag(L, t, k), rows)

    seg = p.seg
    par, dub, dua, pair = (seg[k + "_row"].values for k in ("parent", "dubai", "dubai_all", "pair"))
    lo = max(0, t - 12)
    with np.errstate(invalid="ignore"):
        vol12 = np.nanstd(np.diff(L[:, lo:t + 1], axis=1), axis=1) if t - lo >= 2 else np.full(S, np.nan)
        dua_hist = L[:, max(0, t - 59):t + 1]
        dev60 = _rows(L[:, t] - np.nanmean(dua_hist, axis=1), dua)
    is_price = (seg["measure"] == "price").values
    pair_cur = _rows(cur, pair)
    pair_l12 = _rows(_lag(L, t, 12), pair)
    log_yield = np.where(is_price, pair_cur - cur, cur - pair_cur)
    log_yield12 = np.where(is_price, pair_l12 - _lag(L, t, 12), _lag(L, t, 12) - pair_l12)

    base = pd.DataFrame({
        "row": np.arange(S),
        "is_price": is_price.astype(int),
        "is_villa": (seg["ptype"] == "villa").values.astype(int),
        "beds_code": seg["beds"].map(BEDS_CODE).values,
        "is_dubai": (seg["area_id"] == C.DUBAI).values.astype(int),
        "r1": r(1), "r3": r(3), "r6": r(6), "r12": r(12), "r24": r(24),
        "vol12": vol12,
        "parent_r3": r(3, par), "parent_r12": r(12, par),
        "dubai_r3": r(3, dub), "dubai_r12": r(12, dub),
        "dubai_all_r12": r(12, dua), "dubai_all_r24": r(24, dua),
        "dubai_dev60": dev60,
        "rel_dubai": cur - _rows(cur, dub),
        "log_deals": np.log1p(p.N3[:, t]),
        "deals_change12": np.log1p(p.N3[:, t]) - np.log1p(p.N3[:, t - 12] if t >= 12 else np.nan),
        "log_yield": log_yield,
        "yield_change12": log_yield - log_yield12,
        "offplan_share": np.where(is_price, p.OFF[:, t], np.nan),
        "weight": np.sqrt(np.minimum(p.N3[:, t], 400.0)),
    })[ok]

    origin = pd.Period(p.months[t], freq="M")
    frames = []
    for h in horizons:
        f = base.copy()
        f["h"] = h
        f["target_moy"] = (origin + h).month
        k = t - 12 + h
        f["same_period_last_year"] = (L[f["row"], k] - L[f["row"], t - 12]) if t - 12 >= 0 and k <= t else np.nan
        if with_target:
            f["y"] = L[f["row"], t + h] - cur[f["row"]] if t + h < T else np.nan
        frames.append(f)
    out = pd.concat(frames, ignore_index=True)
    out["origin"] = p.months[t]
    out["t"] = t
    out["sid"] = seg["sid"].values[out["row"]]
    return out


def all_origins(p: Panel, first_col: int = 24) -> pd.DataFrame:
    """Rows for every origin; y is NaN where the outcome is not observed yet. Built once, then filtered:
    the training set for an origin T is every row with t + h <= T (outcomes already known at T)."""
    frames = [origin_frame(p, t) for t in range(first_col, len(p.months))]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def known_at(frame: pd.DataFrame, origin_col: int) -> pd.DataFrame:
    return frame[(frame["t"] + frame["h"] <= origin_col) & frame["y"].notna()]
