"""Data checks run on every update, before anything is retrained or published.

A failed check stops the run: the website keeps the last good forecast and the run is reported as failed.
"""
import json

import numpy as np
import pandas as pd

from . import config as C
from .panel import build


def _check(name, measure, value, ok, rule, unit="share", warn=False):
    """unit: share (shown as %), ratio, count or none."""
    status = "pass" if ok else ("warn" if warn else "fail")
    v = None if value is None or (isinstance(value, float) and np.isnan(value)) else round(float(value), 4)
    return {"check": name, "measure": measure, "value": v, "unit": unit, "rule": rule, "status": status}


def quality_checks(counts: dict) -> list:
    """counts[measure] = dict(rows, missing, out_of_bounds, duplicates) from the cleaning step."""
    out = []
    g = C.GATES
    for m, c in counts.items():
        rows = max(c["rows"], 1)
        out.append(_check("rows received", m, c["rows"], c["rows"] > 0, "> 0", unit="count"))
        out.append(_check("missing area, size or amount", m, c["missing"] / rows,
                          c["missing"] / rows <= g["max_missing_share"], f"<= {g['max_missing_share']:.0%}"))
        out.append(_check("outside plausible range", m, c["out_of_bounds"] / rows,
                          c["out_of_bounds"] / rows <= g["max_out_of_bounds_share"],
                          f"<= {g['max_out_of_bounds_share']:.0%}"))
        out.append(_check("duplicate records", m, c["duplicates"] / rows,
                          c["duplicates"] / rows <= g["max_duplicate_share"], f"<= {g['max_duplicate_share']:.1%}"))
    return out


def history_checks(new_aggs: pd.DataFrame, all_aggs: pd.DataFrame, expected_month: str) -> list:
    """Compare the new months with the history already stored."""
    out = []
    g = C.GATES
    lo, hi = g["volume_ratio"]
    for m in C.MEASURES:
        dub = all_aggs[(all_aggs["measure"] == m) & (all_aggs["area_id"] == C.DUBAI) & (all_aggs["beds"] == C.ALL)]
        dub = dub.groupby("month")["n"].sum().sort_index()
        new_months = sorted(new_aggs.loc[new_aggs["measure"] == m, "month"].unique())
        stored = all_aggs.loc[all_aggs["measure"] == m, "month"]
        latest = stored.max() if len(stored) else None
        out.append(_check("data reaches the expected month", m, None, latest is not None and latest >= expected_month,
                          f"latest month {latest} >= {expected_month}", unit="none"))
        for month in new_months:
            prev = dub[dub.index < month].tail(12)
            if len(prev) < 6 or month not in dub.index:
                continue
            ratio = dub[month] / prev.median()
            out.append(_check(f"deal count {month} vs previous 12 months", m, ratio, lo <= ratio <= hi,
                              f"between {lo} and {hi}", unit="ratio"))
    p = build(all_aggs)
    for m in C.MEASURES:
        for pt in C.PTYPES:
            sid = f"{m}|{C.DUBAI}|{pt}|{C.ALL}"
            if sid not in set(p.seg["sid"]):
                continue
            row = p.seg.index[p.seg["sid"] == sid][0]
            L = p.L[row]
            if len(L) < 2 or np.isnan(L[-1]) or np.isnan(L[-2]):
                continue
            jump = abs(np.exp(L[-1] - L[-2]) - 1)
            out.append(_check(f"Dubai {pt} level change in one month", m, jump,
                              jump <= g["max_dubai_level_jump"], f"<= {g['max_dubai_level_jump']:.0%}"))
    return out


def model_checks(recent_error: float, previous_error: float | None, forecast: pd.DataFrame) -> list:
    g = C.GATES
    out = []
    if previous_error:
        worse = recent_error / previous_error - 1
        out.append(_check("recent error vs last run", "model", worse, worse <= g["max_error_worsening"],
                          f"<= +{g['max_error_worsening']:.0%}"))
    big = forecast[(forecast["h"] == C.HORIZON)]
    extreme = (np.abs(np.exp(big["q50"]) - 1) > g["max_abs_12m_change"]).mean() if len(big) else 0.0
    out.append(_check("12-month forecasts beyond +/-60%", "model", extreme, extreme <= 0.01, "<= 1% of segments"))
    return out


def failed(checks: list) -> list:
    return [c for c in checks if c["status"] == "fail"]


def save(checks: list, run_month: str) -> None:
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (C.REPORT_DIR / "data_checks.json").write_text(json.dumps({"run": run_month, "checks": checks}, indent=1))
