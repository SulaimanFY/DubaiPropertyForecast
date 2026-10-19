"""Turn individual deals into monthly statistics per segment.

A segment is one measure (rent or price) for one area, home type and bedroom count.
Each month we keep numbers that can be added up later (deal count, sum of log price per sq ft
after trimming), so a 3-month or 12-month level can be computed exactly from the monthly rows
without keeping the individual records. Roll-ups (all bedrooms, all of Dubai) are computed
from the deals themselves, not averaged from smaller segments.
"""
import numpy as np
import pandas as pd

from . import config as C

KEYS = ["measure", "area_id", "ptype", "beds", "month"]
STAT_COLS = ["n", "n_trim", "sum_log", "q25", "q50", "q75", "med_size", "med_amount", "n_offplan"]


def _segment_stats(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(KEYS + ["lp"], kind="mergesort")
    g = df.groupby(KEYS, sort=False, observed=True)
    pos = g.cumcount()
    size = g["lp"].transform("size")
    k = np.floor(C.TRIM * size)
    keep = (pos >= k) & (pos < size - k)
    trimmed = df[keep.values]
    tg = trimmed.groupby(KEYS, sort=False, observed=True)

    out = g.agg(
        n=("lp", "size"),
        q50=("ppsf", "median"),
        med_size=("size_sqft", "median"),
        med_amount=("amount", "median"),
        n_offplan=("offplan", "sum"),
    )
    out["q25"] = g["ppsf"].quantile(0.25)
    out["q75"] = g["ppsf"].quantile(0.75)
    out = out.join(tg.agg(n_trim=("lp", "size"), sum_log=("lp", "sum")))
    return out.reset_index()[KEYS + STAT_COLS]


def monthly_stats(records: pd.DataFrame) -> pd.DataFrame:
    """records: one row per deal with measure, month, area_id, ptype, beds, ppsf, size_sqft, amount, offplan."""
    rec = records[["measure", "month", "area_id", "ptype", "beds", "ppsf", "size_sqft", "amount", "offplan"]].copy()
    rec["offplan"] = rec["offplan"].fillna(False).astype(int)
    rec["lp"] = np.log(rec["ppsf"].astype(float))
    parts = []
    for area_all in (False, True):
        for beds_all in (False, True):
            r = rec
            if area_all or beds_all:
                r = rec.copy()
                if area_all:
                    r["area_id"] = C.DUBAI
                if beds_all:
                    r["beds"] = C.ALL
            parts.append(_segment_stats(r))
    out = pd.concat(parts, ignore_index=True)
    for c in ("q25", "q50", "q75", "med_size", "med_amount"):
        out[c] = out[c].round(2)
    out["sum_log"] = out["sum_log"].round(6)
    return out.sort_values(KEYS).reset_index(drop=True)


def merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Replace the months present in `new` (per measure), keep every other month of `old`."""
    if old is None or old.empty:
        return new.sort_values(KEYS).reset_index(drop=True)
    replaced = new[["measure", "month"]].drop_duplicates()
    keep = old.merge(replaced, on=["measure", "month"], how="left", indicator=True)
    keep = keep[keep["_merge"] == "left_only"].drop(columns="_merge")
    return pd.concat([keep, new], ignore_index=True).sort_values(KEYS).reset_index(drop=True)


def path(measure: str):
    return C.AGG_DIR / f"{measure}_monthly.csv.gz"


def load(measure: str) -> pd.DataFrame:
    p = path(measure)
    if not p.exists():
        return pd.DataFrame(columns=KEYS + STAT_COLS)
    return pd.read_csv(p, dtype={"area_id": str, "beds": str, "month": str})


def save(df: pd.DataFrame, measure: str) -> None:
    C.AGG_DIR.mkdir(parents=True, exist_ok=True)
    df[df["measure"] == measure].to_csv(path(measure), index=False, compression={"method": "gzip", "mtime": 0})
