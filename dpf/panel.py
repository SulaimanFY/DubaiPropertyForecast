"""Monthly levels per segment, stored as matrices (segments x months) for fast feature building.

Level = the typical price (or rent) per sq ft over the last 3 months: the geometric mean of the
deals that are left after trimming the 5% most extreme on each side, pooled over 3 months.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from .aggregate import load


def sid(measure, area_id, ptype, beds):
    return f"{measure}|{area_id}|{ptype}|{beds}"


def month_range(first: str, last: str):
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def add_months(month: str, k: int) -> str:
    return str(pd.Period(month, freq="M") + k)


@dataclass
class Panel:
    seg: pd.DataFrame      # one row per segment, index aligned with matrix rows
    months: list           # month labels, aligned with matrix columns
    L: np.ndarray          # log level (NaN where too few deals)
    N3: np.ndarray         # deals in the 3-month window
    N1: np.ndarray         # deals in the month
    OFF: np.ndarray        # off-plan share in the 3-month window (sales only)
    SIZE12: np.ndarray     # typical size in sq ft over 12 months
    AMT12: np.ndarray      # typical yearly rent or price over 12 months

    def col(self, month: str) -> int:
        return self.months.index(month)

    @property
    def last_month(self) -> str:
        return self.months[-1]


def _rolling_sum(a: np.ndarray, w: int) -> np.ndarray:
    c = np.cumsum(np.nan_to_num(a), axis=1)
    out = c.copy()
    out[:, w:] = c[:, w:] - c[:, :-w]
    return out


def build(aggs: pd.DataFrame | None = None, last_month: str | None = None) -> Panel:
    if aggs is None:
        aggs = pd.concat([load(m) for m in C.MEASURES], ignore_index=True)
    aggs = aggs.copy()
    if last_month is not None:
        aggs = aggs[aggs["month"] <= last_month]
    aggs["sid"] = aggs["measure"] + "|" + aggs["area_id"] + "|" + aggs["ptype"] + "|" + aggs["beds"]
    months = month_range(aggs["month"].min(), aggs["month"].max() if last_month is None else last_month)
    seg = (aggs[["sid", "measure", "area_id", "ptype", "beds"]].drop_duplicates("sid")
           .sort_values("sid").reset_index(drop=True))
    S, T = len(seg), len(months)
    ri = pd.Series(np.arange(S), index=seg["sid"])
    ci = pd.Series(np.arange(T), index=months)
    r = ri[aggs["sid"]].values
    c = ci[aggs["month"]].values

    def mat(col, fill=0.0):
        m = np.full((S, T), fill)
        m[r, c] = aggs[col].astype(float).values
        return m

    n, nt, sl, off = mat("n"), mat("n_trim"), mat("sum_log"), mat("n_offplan")
    w = C.WINDOW
    N3, NT3, SL3, OFF3 = (_rolling_sum(x, w) for x in (n, nt, sl, off))
    with np.errstate(invalid="ignore", divide="ignore"):
        L = np.where((N3 >= C.MIN_DEALS_LEVEL) & (NT3 > 0), SL3 / NT3, np.nan)
        OFF = np.where(N3 > 0, OFF3 / N3, np.nan)
        size, amt = mat("med_size", np.nan), mat("med_amount", np.nan)
        n12 = _rolling_sum(n, 12)
        SIZE12 = np.where(n12 > 0, _rolling_sum(np.nan_to_num(size) * n, 12) / n12, np.nan)
        AMT12 = np.where(n12 > 0, _rolling_sum(np.nan_to_num(amt) * n, 12) / n12, np.nan)

    # links between segments, used as features
    seg["parent"] = [sid(m, a, p, C.ALL) for m, a, p in zip(seg.measure, seg.area_id, seg.ptype)]
    seg["dubai"] = [sid(m, C.DUBAI, p, b) for m, p, b in zip(seg.measure, seg.ptype, seg.beds)]
    seg["dubai_all"] = [sid(m, C.DUBAI, p, C.ALL) for m, p in zip(seg.measure, seg.ptype)]
    other = {"rent": "price", "price": "rent"}
    seg["pair"] = [sid(other[m], a, p, b) for m, a, p, b in zip(seg.measure, seg.area_id, seg.ptype, seg.beds)]
    for k in ("parent", "dubai", "dubai_all", "pair"):
        seg[k + "_row"] = seg[k].map(ri).fillna(-1).astype(int)
    return Panel(seg, months, L, N3, n, OFF, SIZE12, AMT12)
