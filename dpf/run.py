"""Command line entry point.

python -m dpf.run rebuild   build the monthly statistics from the full history files (one-off)
python -m dpf.run update    download recent months from the live feed, check them, store their statistics
python -m dpf.run forecast  retrain, forecast 12 months ahead, score past forecasts, save the archive
python -m dpf.run site      write the website (data + pages) into _site/ from what is stored
python -m dpf.run backtest  replay the past to measure accuracy (slow; run when the method changes)
"""
import argparse
import json
import sys
from datetime import date

import numpy as np
import pandas as pd

from . import aggregate as A
from . import config as C
from . import validate as V


def log(*a):
    print(*a, flush=True)


def previous_month(today=None) -> str:
    return str(pd.Period(today or date.today(), freq="M") - 1)


def cmd_rebuild(args):
    from .sources import bulk
    from .clean import clean

    stats, counts = [], {}
    for m in C.MEASURES:
        raw = bulk.load(m)
        rec, cnt = clean(raw, m)
        counts[m] = cnt
        log(f"{m}: {len(rec):,} usable deals from {cnt['rows']:,} in-scope rows")
        stats.append(A.monthly_stats(rec))
    new = pd.concat(stats, ignore_index=True)
    for m in C.MEASURES:
        A.save(new, m)
    checks = V.quality_checks(counts)
    V.save(checks, "rebuild")
    (C.REPORT_DIR / "deal_counts.json").write_text(json.dumps(
        {m: int(new[(new.measure == m) & (new.area_id == C.DUBAI) & (new.beds == C.ALL)]["n"].sum()) for m in C.MEASURES}))
    log("rebuild done")


def cmd_update(args):
    from .sources import gateway
    from .clean import clean

    today = date.today()
    expected = previous_month(today)
    year_end_run = today.month == 12 and today.day == 31
    last_complete = str(pd.Period(today, freq="M")) if year_end_run else expected
    start = max(pd.Period(today, freq="M") - 3, pd.Period(f"{today.year}-01", freq="M"))
    stats, counts = [], {}
    for m in C.MEASURES:
        raw = gateway.fetch(m, start.start_time.date(), today, log=log)
        rec, cnt = clean(raw, m)
        counts[m] = cnt
        rec = rec[rec["month"] <= last_complete]
        log(f"{m}: {len(rec):,} usable deals ({start} to {last_complete})")
        if len(rec):
            stats.append(A.monthly_stats(rec))
    new = pd.concat(stats, ignore_index=True) if stats else pd.DataFrame(columns=A.KEYS + A.STAT_COLS)
    old = pd.concat([A.load(m) for m in C.MEASURES], ignore_index=True)
    merged = A.merge(old, new)
    checks = V.quality_checks(counts) + V.history_checks(new, merged, expected)
    V.save(checks, expected)
    bad = V.failed(checks)
    for c in checks:
        log(f"  [{c['status']}] {c['measure']}: {c['check']} = {c['value']} ({c['rule']})")
    if bad:
        log(f"{len(bad)} data check(s) failed: nothing stored, nothing published.")
        sys.exit(1)
    for m in C.MEASURES:
        A.save(merged, m)
    dc = C.REPORT_DIR / "deal_counts.json"
    dc.write_text(json.dumps(
        {m: int(merged[(merged.measure == m) & (merged.area_id == C.DUBAI) & (merged.beds == C.ALL)]["n"].sum()) for m in C.MEASURES}))
    log("update stored")


def cmd_forecast(args):
    from .features import all_origins
    from .forecast import make, save, live_scorecard
    from .panel import build

    p = build()
    log(f"panel: {len(p.seg)} segments, {p.months[0]} to {p.last_month}")
    frame = all_origins(p)
    fc, recent_error, widths, importance = make(p, frame)
    log(f"forecast: {fc['sid'].nunique()} segments, recent error {recent_error:.3%}")
    runs_path = C.REPORT_DIR / "runs.csv"
    runs = pd.read_csv(runs_path, dtype={"data_through": str}) if runs_path.exists() else pd.DataFrame()
    prev = runs[runs["data_through"] < p.last_month]["recent_error"].iloc[-1] if len(runs) and (runs["data_through"] < p.last_month).any() else None
    mchecks = V.model_checks(recent_error, prev, fc)
    checks_file = C.REPORT_DIR / "data_checks.json"
    data_checks = json.loads(checks_file.read_text())["checks"] if checks_file.exists() else []
    data_checks = [c for c in data_checks if c["measure"] != "model"] + mchecks
    V.save(data_checks, p.last_month)
    for c in mchecks:
        log(f"  [{c['status']}] {c['check']} = {c['value']} ({c['rule']})")
    if V.failed(mchecks):
        log("model check failed: nothing published.")
        sys.exit(1)
    saved = save(fc, overwrite=args.overwrite)
    log("archived" if saved else "archive for this month already exists (kept unchanged)")
    cur = fc.copy()
    cur.to_csv(C.REPORT_DIR / "forecast_current.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    live = live_scorecard(p)
    live.to_csv(C.REPORT_DIR / "live_scorecard.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    row = {"data_through": p.last_month, "run_date": date.today().isoformat(), "segments": int(fc["sid"].nunique()),
           "recent_error": round(recent_error, 5), "run_url": args.run_url or ""}
    runs = pd.concat([runs[runs.get("data_through", pd.Series(dtype=str)) != p.last_month] if len(runs) else runs,
                      pd.DataFrame([row])], ignore_index=True)
    runs.to_csv(runs_path, index=False)
    importance.rename("gain").to_csv(C.REPORT_DIR / "feature_importance.csv")
    (C.REPORT_DIR / "data_through.txt").write_text(p.last_month)
    log("forecast done")


def cmd_site(args):
    from .export import build_site, meta_block
    from .panel import build
    from .scorecard import summary

    p = build()
    fc = pd.read_csv(C.REPORT_DIR / "forecast_current.csv.gz", dtype={"origin": str, "target_month": str})
    if fc["origin"].iloc[0] != p.last_month:
        p = build(last_month=fc["origin"].iloc[0])   # the site always shows the stored forecast's own month
    runs = pd.read_csv(C.REPORT_DIR / "runs.csv", dtype={"data_through": str})
    run = runs[runs["data_through"] == p.last_month].iloc[-1]
    deals = json.loads((C.REPORT_DIR / "deal_counts.json").read_text())
    run_url = run["run_url"] if isinstance(run["run_url"], str) and run["run_url"] else None
    meta = meta_block(p, deals, float(run["recent_error"]), run_url)
    meta["updated"] = run["run_date"]
    meta["default_area"] = C.DEFAULT_AREA_SLUG
    checks = json.loads((C.REPORT_DIR / "data_checks.json").read_text())
    info = build_site(p, fc, meta, summary(), checks)
    log(f"site written to {C.SITE_OUT}: {info}")


def cmd_backtest(args):
    from .backtest import run, score
    from .features import all_origins
    from .panel import build

    p = build()
    frame = all_origins(p)
    methods = args.methods.split(",") if args.methods else None
    res = run(methods=methods or __import__("dpf.models", fromlist=["METHODS"]).METHODS, panel=p, frame=frame, log=log)
    res.to_csv(C.REPORT_DIR / "backtest_results.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    s = score(res, by=("measure", "period", "method", "h"))
    s.to_csv(C.REPORT_DIR / "backtest_scores.csv", index=False)
    log(score(res[res["h"] == C.HORIZON], by=("measure", "period", "method")).to_string())


def main():
    ap = argparse.ArgumentParser(prog="dpf")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rebuild")
    sub.add_parser("update")
    f = sub.add_parser("forecast")
    f.add_argument("--run-url", default="")
    f.add_argument("--overwrite", action="store_true")
    sub.add_parser("site")
    b = sub.add_parser("backtest")
    b.add_argument("--methods", default="")
    args = ap.parse_args()
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    {"rebuild": cmd_rebuild, "update": cmd_update, "forecast": cmd_forecast, "site": cmd_site,
     "backtest": cmd_backtest}[args.cmd](args)


if __name__ == "__main__":
    main()
