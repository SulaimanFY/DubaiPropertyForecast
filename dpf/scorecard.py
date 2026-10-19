"""The numbers behind the Track record page: backtest summary and the live record."""
import numpy as np
import pandas as pd

from . import config as C
from .models import LABELS
from .forecast import load_archive

REPO_RAW = "https://github.com/SulaimanFY/DubaiPropertyForecast/blob/main/data/forecasts"


def _f(x, nd=4):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _p(x):
    return f"{x * 100:.1f}%"


PHRASE = {"no_change": "assuming no change", "last_trend": "continuing last year's trend",
          "dubai_trend": "applying the Dubai-wide trend to every area", "ets": "exponential smoothing per series"}


def verdict(m: str, h: dict) -> str:
    """Plain sentences, written from the numbers, on whether the model beat the simple benchmarks."""
    what = "rents" if m == "rent" else "sale prices"
    e, naive, best, be = h["error12"], h["naive12"], h["best_benchmark"], h["best_benchmark12"]
    if naive is not None and e > naive:
        s = [f"For {what}, the model did worse than {PHRASE['no_change']} on the test years "
             f"({_p(e)} against {_p(naive)} typical error 12 months ahead)."]
    elif best is None or e <= be:
        s = [f"For {what}, the model was the most accurate method on the test years: {_p(e)} typical error "
             f"12 months ahead, against {_p(naive)} for {PHRASE['no_change']}."]
    else:
        s = [f"For {what}, the model beat {PHRASE['no_change']} ({_p(e)} against {_p(naive)} typical error "
             f"12 months ahead), but {PHRASE.get(best, best)} did better on the test years, at {_p(be)}."]
    cov = h["coverage80"]
    if cov is not None and cov < 0.75:
        s.append(f"Its ranges were too narrow: {round(cov * 10)} in 10 real outcomes landed inside the 8-in-10 range.")
    return " ".join(s)


def summary() -> dict:
    s = pd.read_csv(C.REPORT_DIR / "backtest_scores.csv")
    out = {"headline": {}, "by_h": [], "table": []}
    test = s[s["period"] == "test"]
    first, last = C.TEST_START[:4], None
    o_path = C.REPORT_DIR / "backtest_origins.csv"
    if o_path.exists():   # forecasts made in the test period whose 12-month outcome is known
        o = pd.read_csv(o_path, dtype={"origin": str})
        t = o[(o["period"] == "test") & (o["max_h_scored"] >= C.HORIZON)]["origin"]
        last = t.max()[:4] if len(t) else None
    period = f"{first} to {last}" if last and last != first else first
    for m in C.MEASURES:
        g = test[(test["measure"] == m) & (test["h"] == C.HORIZON)].set_index("method")
        if "gbm" not in g.index:
            continue
        bench = g.drop(index="gbm")["median_error"]
        out["headline"][m] = {
            "period": period, "error12": _f(g.loc["gbm", "median_error"]),
            "naive12": _f(g.loc["no_change", "median_error"]) if "no_change" in g.index else None,
            "coverage80": _f(g.loc["gbm", "coverage80"]), "direction": _f(g.loc["gbm", "direction_hit"]),
            "n": int(g.loc["gbm", "n"]),
            "best_benchmark": bench.idxmin() if len(bench) else None,
            "best_benchmark12": _f(bench.min()) if len(bench) else None,
        }
        out["headline"][m]["verdict"] = verdict(m, out["headline"][m])
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
