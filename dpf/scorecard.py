"""The numbers behind the Track record page: backtest summary and the live record."""
import numpy as np
import pandas as pd

from . import config as C
from .models import LABELS
from .forecast import load_archive

REPO_RAW = "https://github.com/SulaimanFY/DubaiPropertyForecast/blob/main/data/forecasts"


def _f(x, nd=4):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def summary() -> dict:
    s = pd.read_csv(C.REPORT_DIR / "backtest_scores.csv")
    out = {"headline": {}, "by_h": [], "table": []}
    test = s[s["period"] == "test"]
    first, last = C.TEST_START[:4], None
    res_path = C.REPORT_DIR / "backtest_results.csv.gz"
    if res_path.exists():
        origins = pd.read_csv(res_path, usecols=["origin", "period"]).drop_duplicates()
        t = origins[origins["period"] == "test"]["origin"]
        last = t.max()[:4] if len(t) else None
    period = f"{first} to {last}" if last and last != first else first
    for m in C.MEASURES:
        g = test[(test["measure"] == m) & (test["h"] == C.HORIZON)].set_index("method")
        if "gbm" not in g.index:
            continue
        out["headline"][m] = {
            "period": period, "error12": _f(g.loc["gbm", "median_error"]),
            "naive12": _f(g.loc["no_change", "median_error"]) if "no_change" in g.index else None,
            "coverage80": _f(g.loc["gbm", "coverage80"]), "direction": _f(g.loc["gbm", "direction_hit"]),
            "n": int(g.loc["gbm", "n"]),
        }
    for r in s[s["period"] == "test"].itertuples():
        out["by_h"].append({"measure": r.measure, "method": r.method, "period": r.period, "h": int(r.h),
                            "median_error": _f(r.median_error), "coverage80": _f(r.coverage80), "n": int(r.n)})
    for (m, per, meth), g in s.groupby(["measure", "period", "method"]):
        g = g.set_index("h")
        w = g["n"]
        out["table"].append({
            "measure": m, "period": per, "method": meth, "label": LABELS.get(meth, meth),
            "e3": _f(g.loc[3, "median_error"]) if 3 in g.index else None,
            "e6": _f(g.loc[6, "median_error"]) if 6 in g.index else None,
            "e12": _f(g.loc[12, "median_error"]) if 12 in g.index else None,
            "coverage80": _f((g["coverage80"] * w).sum() / w.sum()),
            "direction": _f(g.loc[12, "direction_hit"]) if 12 in g.index and meth != "no_change" else None,
        })
    order = {k: i for i, k in enumerate(["gbm", "ets", "last_trend", "dubai_trend", "no_change"])}
    out["table"].sort(key=lambda r: (r["measure"], r["period"] != "test", order.get(r["method"], 9)))
    out["live"] = live_summary()
    return out


def live_summary() -> dict:
    a = load_archive()
    if a.empty:
        return {"first_origin": None, "archives": []}
    lv_path = C.REPORT_DIR / "live_scorecard.csv.gz"
    lv = pd.read_csv(lv_path, dtype={"origin": str}) if lv_path.exists() else pd.DataFrame(columns=["origin"])
    if len(lv):
        lv["ape"] = np.abs(np.exp(lv["q50"] - lv["y"]) - 1)
        lv["in80"] = (lv["y"] >= lv["q10"]) & (lv["y"] <= lv["q90"])
    arch = []
    for origin, g in a.groupby("origin"):
        L = lv[lv["origin"] == origin] if len(lv) else lv
        arch.append({
            "origin": origin, "segments": int(g["sid"].nunique()), "matured": int(len(L)),
            "median_error": _f(L["ape"].median()) if len(L) else None,
            "coverage80": _f(L["in80"].mean()) if len(L) else None,
            "url": f"{REPO_RAW}/forecast_{origin}.csv.gz",
        })
    return {"first_origin": min(a["origin"]), "archives": arch}
