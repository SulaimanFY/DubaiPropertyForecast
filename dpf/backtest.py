"""Honest accuracy: replay the past. At each origin, every method sees only the data known then,
forecasts 1-12 months ahead, and is scored against what really happened.

Origins before TEST_START were used to make design choices (the development period).
Origins from TEST_START on were not looked at until the design was frozen (the test period),
so their scores are the ones quoted.
"""
import time

import numpy as np
import pandas as pd

from . import config as C
from . import models as M
from .features import all_origins, known_at
from .panel import build


def run(methods=M.METHODS, start=C.BACKTEST_START, step=C.BACKTEST_STEP, panel=None, frame=None, log=print):
    p = panel or build()
    frame = frame if frame is not None else all_origins(p)
    last = len(p.months) - 1
    cols = [c for c in range(p.col(start), last) if (c - p.col(start)) % step == 0]
    out = []
    for T0 in cols:
        t0 = time.time()
        train = known_at(frame, T0)
        test = frame[(frame["t"] == T0) & (frame["log_deals"] >= np.log1p(C.MIN_DEALS_PUBLISH))]
        if test.empty or train.empty:
            continue
        keep = test[["sid", "origin", "h", "y", "row", "weight"]].copy()
        for m in methods:
            if m == "gbm":
                pred = M.gbm(train, test, T0)
            elif m == "ets":
                pred = M.ets(p, train, test)
            else:
                pred = getattr(M, m)(train, test)
            r = keep.join(pred)
            r["method"] = m
            out.append(r)
        log(f"backtest origin {p.months[T0]}: {len(test)} rows, {time.time() - t0:.0f}s")
    res = pd.concat(out, ignore_index=True)
    res["period"] = np.where(res["origin"] >= C.TEST_START, "test", "development")
    seg = p.seg.set_index("sid")[["measure", "area_id", "ptype", "beds"]]
    return res.join(seg, on="sid")


def score(res: pd.DataFrame, by=("period", "method")) -> pd.DataFrame:
    r = res[res["y"].notna()].copy()
    r["ape"] = np.abs(np.exp(r["q50"] - r["y"]) - 1)
    r["in80"] = (r["y"] >= r["q10"]) & (r["y"] <= r["q90"])
    r["in50"] = (r["y"] >= r["q25"]) & (r["y"] <= r["q75"])
    moved = r["y"].abs() > 0.02
    r["dir_ok"] = np.where(moved, np.sign(r["q50"]) == np.sign(r["y"]), np.nan)
    g = r.groupby(list(by))
    return pd.DataFrame({
        "median_error": g["ape"].median(),
        "mean_error": g["ape"].mean(),
        "coverage80": g["in80"].mean(),
        "coverage50": g["in50"].mean(),
        "direction_hit": g["dir_ok"].mean(),
        "n": g.size(),
    }).reset_index()


def skill(scores: pd.DataFrame, metric="median_error", base="no_change") -> pd.DataFrame:
    keys = [c for c in scores.columns if c not in ("method", "median_error", "mean_error", "coverage80",
                                                     "coverage50", "direction_hit", "n")]
    b = scores[scores["method"] == base].set_index(keys)[metric]
    s = scores.set_index(keys)
    s["skill_vs_no_change"] = 1 - s[metric] / b.reindex(s.index).values
    return s.reset_index()
