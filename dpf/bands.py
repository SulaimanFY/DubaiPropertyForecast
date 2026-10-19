"""Bedroom groups by floor area.

Rent contracts rarely record the number of bedrooms, and sales record it for most apartments but few
villas. So every home is grouped by its floor area instead, with limits set from the sales that do
state their bedrooms: a home counts as "2 bedrooms" when its size is closer to a typical 2-bedroom
than to a typical 1- or 3-bedroom (the limit is the geometric midpoint of the two median sizes).
The same limits apply to rents and prices, so the two stay comparable (and give a fair yield).

The limits are measured once from the full history, saved in data/size_bands.json and then kept
fixed, so a segment means the same thing every month.
"""
import json

import numpy as np
import pandas as pd

from . import config as C

PATH = C.DATA / "size_bands.json"

# Groups per home type, smallest first. Villas start at "up to 2 bedrooms" ("2" here).
GROUPS = {"apartment": ["studio", "1", "2", "3", "4+"], "villa": ["2", "3", "4+"]}

# Used only until the limits have been measured from the history (typical Dubai sizes, sq ft).
DEFAULT = {"apartment": [600, 1000, 1500, 2200], "villa": [2100, 2900]}

MIN_PER_GROUP = 300


def calibrate(stated: pd.DataFrame) -> dict:
    """stated: rows with ptype, size_sqft and stated_beds (studio, 1, 2, 3, 4+) from sales records."""
    out = {"limits_sqft": {}, "median_sqft": {}, "deals": {}, "source": "default"}
    measured = False
    for pt, groups in GROUPS.items():
        d = stated[(stated["ptype"] == pt) & stated["stated_beds"].notna()].copy()
        if pt == "villa":
            d["stated_beds"] = d["stated_beds"].replace({"studio": "2", "1": "2"})
        med, n = {}, {}
        for g in groups:
            s = d.loc[d["stated_beds"] == g, "size_sqft"]
            n[g] = int(len(s))
            med[g] = float(s.median()) if len(s) else None
        ok = all(n[g] >= MIN_PER_GROUP for g in groups) and all(
            med[a] < med[b] for a, b in zip(groups, groups[1:]))
        if ok:
            limits = [round(float(np.sqrt(med[a] * med[b]))) for a, b in zip(groups, groups[1:])]
            measured = True
        else:
            limits = DEFAULT[pt]
        out["limits_sqft"][pt] = limits
        out["median_sqft"][pt] = {g: (round(v) if v else None) for g, v in med.items()}
        out["deals"][pt] = n
        out.setdefault("measured", {})[pt] = ok
    out["source"] = "sales records with stated bedrooms" if measured else "default"
    return out


def load() -> dict:
    if PATH.exists():
        return json.loads(PATH.read_text())
    return {"limits_sqft": DEFAULT, "source": "default"}


def save(bands: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(bands, indent=2))


def assign(size_sqft: pd.Series, ptype: pd.Series, bands: dict | None = None) -> pd.Series:
    bands = bands or load()
    out = pd.Series(pd.NA, index=size_sqft.index, dtype="object")
    for pt, groups in GROUPS.items():
        m = (ptype == pt).values
        if not m.any():
            continue
        idx = np.searchsorted(np.asarray(bands["limits_sqft"][pt], dtype=float), size_sqft[m].to_numpy(dtype=float),
                              side="right")
        out[m] = np.asarray(groups, dtype=object)[idx]
    return out


def ranges(bands: dict | None = None) -> dict:
    """For the website: {ptype: {group: [from_sqft, to_sqft or None]}}."""
    bands = bands or load()
    out = {}
    for pt, groups in GROUPS.items():
        lim = bands["limits_sqft"][pt]
        edges = [0] + list(lim) + [None]
        out[pt] = {g: [edges[i], edges[i + 1]] for i, g in enumerate(groups)}
    return out
