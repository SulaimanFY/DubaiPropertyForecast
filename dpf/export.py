"""Write the JSON files the website reads. The site itself is static HTML, CSS and JavaScript."""
import json
import re
import shutil
from datetime import date

import numpy as np
import pandas as pd

from . import config as C
from . import models as M
from .panel import Panel

HISTORY_FROM = "2013-01"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def area_names() -> pd.DataFrame:
    p = C.DATA / "area_names.csv"
    if p.exists():
        return pd.read_csv(p, dtype=str).fillna("")
    return pd.DataFrame(columns=["area_id", "name", "aka"])


def _r(x, nd=1):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False))


def build_site(p: Panel, fc: pd.DataFrame, meta: dict, scorecard: dict, checks: list, out=C.SITE_OUT):
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(C.SITE_SRC, out)
    d = out / "data"
    names = area_names().set_index("area_id")
    T0 = len(p.months) - 1
    first = p.months.index(HISTORY_FROM) if HISTORY_FROM in p.months else 0

    fc = fc.copy()
    fc["measure"], fc["area_id"], fc["ptype"], fc["beds"] = zip(*fc["sid"].str.split("|"))
    areas, rankings = [], []
    for area_id, g in fc.groupby("area_id"):
        nm = names["name"].get(area_id, "") or area_id.title()
        official = area_id.title() if area_id != C.DUBAI else "All of Dubai"
        if area_id == C.DUBAI:
            nm = "All of Dubai"
        s = slug(nm if area_id != C.DUBAI else "all-dubai")
        series, avail = {}, {}
        for sid_, f in g.groupby("sid"):
            m, _, pt, b = sid_.split("|")
            row = int(p.seg.index[p.seg["sid"] == sid_][0])
            L = p.L[row]
            hist = [[p.months[t], _r(np.exp(L[t]), 2), int(p.N1[row, t])]
                    for t in range(first, T0 + 1) if np.isfinite(L[t])]
            f = f.sort_values("h")
            lvl = np.exp(L[T0])
            fq = {c: [_r(lvl * np.exp(v), 2) for v in f[c]] for c in M.QCOLS}
            last = f[f["h"] == C.HORIZON].iloc[0]
            series[f"{m}|{pt}|{b}"] = {
                "history": hist,
                "forecast": {"months": list(f["target_month"]), **fq},
                "now": {"level": _r(lvl, 2), "deals3": int(p.N3[row, T0]),
                        "typical_size": _r(p.SIZE12[row, T0], 0), "typical_amount": _r(p.AMT12[row, T0], -2)},
                "change12": {c: _r(np.exp(last[c]) - 1, 4) for c in M.QCOLS},
            }
            avail.setdefault(m, {}).setdefault(pt, []).append(b)
            if area_id != C.DUBAI:
                rankings.append({
                    "slug": s, "name": nm, "measure": m, "ptype": pt, "beds": b,
                    "now": _r(lvl, 2), "deals3": int(p.N3[row, T0]),
                    **{c: _r(np.exp(last[c]) - 1, 4) for c in ("q10", "q50", "q90")},
                })
        for pt_beds in {k.split("|", 1)[1] for k in series}:
            r, pr = series.get(f"rent|{pt_beds}"), series.get(f"price|{pt_beds}")
            if r and pr:
                r["now"]["gross_yield"] = pr["now"]["gross_yield"] = _r(r["now"]["level"] / pr["now"]["level"], 4)
        order = {b: i for i, b in enumerate(list(C.BEDS) + [C.ALL])}
        for m in avail:
            for pt in avail[m]:
                avail[m][pt] = sorted(avail[m][pt], key=order.get)
        aka = names["aka"].get(area_id, "") if area_id in names.index else ""
        areas.append({"id": area_id, "slug": s, "name": nm, "official": official,
                      "aka": [a for a in aka.split(";") if a], "available": avail})
        _write(d / "areas" / f"{s}.json", {"id": area_id, "name": nm, "official": official, "series": series})

    areas.sort(key=lambda a: (a["id"] != C.DUBAI, a["name"]))
    _write(d / "areas.json", areas)
    _write(d / "rankings.json", rankings)
    _write(d / "meta.json", meta)
    _write(d / "scorecard.json", scorecard)
    _write(d / "checks.json", checks)
    return {"areas": len(areas), "series": len(fc["sid"].unique())}


def meta_block(p: Panel, deals: dict, recent_error: float, run_url: str | None) -> dict:
    origin = p.last_month
    nxt = pd.Period(date.today(), freq="M") + 1
    return {
        "updated": date.today().isoformat(),
        "data_through": origin,
        "forecast_to": str(pd.Period(origin, freq="M") + C.HORIZON),
        "next_update": f"{nxt}-03",
        "deals": deals,
        "recent_error": _r(recent_error, 4),
        "run_url": run_url,
        "source": C.SOURCE_NAME,
        "attribution": C.ATTRIBUTION,
    }
