"""From Land Department records to one clean row per residential deal.

Works on both the full history files and the live feed: their column names differ, so each
field is looked up under all its known names.

Kept: residential apartments and villas or townhouses with a known area, size and amount.
Sales: the "Sales" group only (not mortgages or gifts), ready and off-plan.
Rents: new lease contracts for a single home only (renewals are capped by the rent index and lag
       the market; a contract covering several units has no per-unit size), yearly amount,
       dated by the contract's start date (the only date the history files carry).
Bedrooms: grouped by floor area (see bands.py); the stated bedroom count is kept only to set
          those groups.
"""
import re

import numpy as np
import pandas as pd

from . import bands as B
from . import config as C

FIELDS = {
    "price": {
        "id": ["transaction_number", "transaction_id"],
        "date": ["instance_date"],
        "group": ["group_en", "trans_group_en"],
        "procedure": ["procedure_en", "procedure_name_en"],
        "offplan": ["is_offplan", "reg_type_en"],
        "usage": ["usage_en", "property_usage_en"],
        "area": ["area_en", "area_name_en"],
        "ptype": ["prop_type_en", "property_type_en"],
        "psub": ["prop_sb_type_en", "property_sub_type_en"],
        "amount": ["trans_value", "actual_worth"],
        "size": ["actual_area", "procedure_area"],
        "rooms": ["rooms_en"],
    },
    "rent": {
        # the live feed leaves the contract number empty: duplicates are then found on these fields
        "id": ["contract_id", "contract_number"],
        "id_parts": ["registration_date", "start_date", "area_en", "project_en", "annual_amount", "actual_area"],
        "date": ["contract_start_date", "start_date"],
        "regtype": ["contract_reg_type_en", "version_en"],
        "usage": ["property_usage_en", "usage_en"],
        "area": ["area_name_en", "area_en"],
        "ptype": ["ejari_bus_property_type_en", "prop_type_en"],
        "psub": ["ejari_property_type_en", "prop_sub_type_en"],
        "amount": ["annual_amount"],
        "size": ["actual_area"],
        "rooms": ["ejari_property_sub_type_en", "rooms"],
        "units": ["no_of_prop", "total_properties"],
    },
}


def _col(df, names, required=True):
    for n in names:
        if n in df.columns:
            return df[n]
    if required:
        raise KeyError(f"none of {names} in columns {list(df.columns)[:40]}")
    return pd.Series(np.nan, index=df.index)


def _dates(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    out = pd.to_datetime(s, format="%d-%m-%Y", errors="coerce")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y %I:%M:%S %p"):
        miss = out.isna()
        if not miss.any():
            break
        out[miss] = pd.to_datetime(s[miss], format=fmt, errors="coerce")
    miss = out.isna()
    if miss.any():
        out[miss] = pd.to_datetime(s[miss].str.slice(0, 10), errors="coerce")
    return out


ROOM_PATTERNS = [
    (re.compile(r"studio|single room", re.I), "studio"),
    (re.compile(r"^\s*1\b|\b1\s*b|one\s*bed|1bed", re.I), "1"),
    (re.compile(r"^\s*2\b|\b2\s*b|two\s*bed|2bed", re.I), "2"),
    (re.compile(r"^\s*3\b|\b3\s*b|three\s*bed|3bed", re.I), "3"),
    (re.compile(r"^\s*(?:[4-9]|1[0-9])\b|\b(?:[4-9]|1[0-9])\s*b|(?:four|five|six|seven)\s*bed|[4-9]bed", re.I), "4+"),
]


def bedrooms(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str)
    out = pd.Series(pd.NA, index=s.index, dtype="object")
    for pat, lab in ROOM_PATTERNS:
        hit = out.isna() & s.str.contains(pat)
        out[hit] = lab
    return out


def home_type(ptype: pd.Series, psub: pd.Series) -> pd.Series:
    p = ptype.fillna("").astype(str).str.lower()
    sub = psub.fillna("").astype(str).str.lower()
    out = pd.Series(pd.NA, index=p.index, dtype="object")
    villa = sub.str.contains("villa|townhouse|town house") | p.str.contains("villa")
    flat = sub.str.contains("flat|apartment") | (p.str.contains("unit") & ~sub.str.contains(
        "office|shop|hotel|warehouse|retail|store|clinic|showroom|labor|labour|staff|parking|restaurant|gym|school"))
    out[flat] = "apartment"
    out[villa] = "villa"
    return out


def _ids(df, F):
    if "id_parts" not in F:
        return _col(df, F["id"]).astype(str)
    ids = _col(df, F["id"], required=False)
    if ids.notna().any():
        return ids.astype(str)
    parts = [_col(df, [c], required=False).astype(str) for c in F["id_parts"]]
    return pd.Series(["|".join(t) for t in zip(*parts)], index=df.index) if parts else ids.astype(str)


def clean(raw: pd.DataFrame, measure: str, bands: dict | None = None):
    """Returns (records, counts). counts feed the data checks."""
    cols = ["measure", "month", "date", "area_id", "ptype", "beds", "stated_beds", "ppsf", "size_sqft", "amount",
            "offplan"]
    if raw.empty:
        return pd.DataFrame(columns=cols), {"rows": 0, "missing": 0, "out_of_bounds": 0, "duplicates": 0}
    df = raw.rename(columns=str.lower)
    F = FIELDS[measure]
    usage = _col(df, F["usage"]).fillna("").astype(str).str.lower()
    keep = usage.str.startswith("residential")
    if measure == "price":
        keep &= _col(df, F["group"]).fillna("").astype(str).str.lower().str.contains("sale")
        proc = _col(df, F["procedure"], required=False).fillna("").astype(str).str.lower()
        keep &= ~proc.str.contains("mortgage|gift|grant|inherit|lease")
    else:
        keep &= _col(df, F["regtype"]).fillna("").astype(str).str.lower().str.startswith("new")
        units = pd.to_numeric(_col(df, F["units"], required=False), errors="coerce")
        keep &= units.isna() | (units == 1)
    df = df[keep]

    ptype = home_type(_col(df, F["ptype"]), _col(df, F["psub"], required=False))
    rec = pd.DataFrame({
        "id": _ids(df, F),
        "date": _dates(_col(df, F["date"])),
        "area_id": _col(df, F["area"]).astype(str).str.strip().str.upper().replace({"NAN": np.nan, "": np.nan}),
        "ptype": ptype,
        "stated_beds": bedrooms(_col(df, F["rooms"], required=False)),
        "amount": pd.to_numeric(_col(df, F["amount"]), errors="coerce"),
        "size_sqft": pd.to_numeric(_col(df, F["size"]), errors="coerce") * C.SQM_TO_SQFT,
    }, index=df.index)
    if measure == "price":
        off = _col(df, F["offplan"], required=False)
        rec["offplan"] = off.astype(str).str.lower().isin(["1", "true", "off-plan properties", "off-plan", "offplan"])
    else:
        rec["offplan"] = False
    rec = rec[rec["ptype"].notna()]
    rows = len(rec)
    dup = rec["id"].duplicated()
    duplicates = int(dup.sum())
    rec = rec[~dup]
    missing = rec[["date", "area_id", "amount", "size_sqft"]].isna().any(axis=1) | (rec["amount"] <= 0) | (rec["size_sqft"] <= 0)
    n_missing = int(missing.sum())
    rec = rec[~missing].copy()
    rec["ppsf"] = rec["amount"] / rec["size_sqft"]
    lo, hi = C.BOUNDS[measure]
    s_lo = rec["ptype"].map({k: v[0] for k, v in C.SIZE_BOUNDS_SQFT.items()})
    s_hi = rec["ptype"].map({k: v[1] for k, v in C.SIZE_BOUNDS_SQFT.items()})
    bad = (rec["ppsf"] < lo) | (rec["ppsf"] > hi) | (rec["size_sqft"] < s_lo) | (rec["size_sqft"] > s_hi)
    n_bad = int(bad.sum())
    rec = rec[~bad].copy()
    rec["beds"] = B.assign(rec["size_sqft"], rec["ptype"], bands)
    rec["month"] = rec["date"].dt.to_period("M").astype(str)
    rec["measure"] = measure
    counts = {"rows": rows, "missing": n_missing, "out_of_bounds": n_bad, "duplicates": duplicates}
    return rec[cols], counts
