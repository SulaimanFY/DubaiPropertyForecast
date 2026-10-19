"""The Dubai Land Department open data feed (current calendar year), queried day by day.

Sales: POST https://gateway.dubailand.gov.ae/open-data/transactions
Rents: POST https://gateway.dubailand.gov.ae/open-data/rents
No login. Results come in pages of up to 5,000 rows; each row carries the total count.
"""
import json
import time
from datetime import date, timedelta

import pandas as pd
import requests

BASE = "https://gateway.dubailand.gov.ae/open-data"
UA = {"User-Agent": "DubaiPropertyForecast/1.0 (+https://github.com/SulaimanFY/DubaiPropertyForecast)",
      "Content-Type": "application/json", "Accept": "application/json"}
PAGE = 5000

ENDPOINTS = {
    "price": ("transactions", {"P_GROUP_ID": "1", "P_IS_OFFPLAN": "", "P_IS_FREE_HOLD": "", "P_AREA_ID": "",
                               "P_USAGE_ID": "", "P_PROP_TYPE_ID": "", "P_SORT": "TRANSACTION_NUMBER_ASC"}),
    "rent": ("rents", {"P_DATE_TYPE": "0", "P_IS_FREE_HOLD": "", "P_AREA_ID": "", "P_USAGE_ID": "",
                       "P_PROP_TYPE_ID": "", "P_VERSION": "", "P_SORT": "CONTRACT_NUMBER_ASC"}),
}


def _post(session, url, body, tries=6):
    err = None
    for i in range(tries):
        try:
            r = session.post(url, data=json.dumps(body), headers=UA, timeout=180)
            r.raise_for_status()
            js = r.json()
            return js["response"]["result"] or []
        except Exception as e:  # network hiccups are common on long downloads: back off and retry
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url} failed after {tries} tries: {err}")


def fetch_day(session, measure, d: date) -> list:
    path, extra = ENDPOINTS[measure]
    url = f"{BASE}/{path}"
    rows, skip = [], 0
    while True:
        body = {"P_FROM_DATE": d.strftime("%m/%d/%Y"), "P_TO_DATE": d.strftime("%m/%d/%Y"),
                "P_TAKE": str(PAGE), "P_SKIP": str(skip), **extra}
        res = _post(session, url, body)
        rows += res
        total = res[0].get("TOTAL", len(res)) if res else 0
        if not res or len(rows) >= total:
            return rows
        skip += len(res)


def fetch(measure: str, start: date, end: date, log=print) -> pd.DataFrame:
    s = requests.Session()
    out, d = [], start
    while d <= end:
        rows = fetch_day(s, measure, d)
        out += rows
        if d.day == 1 or d == end:
            log(f"  {measure} {d}: {len(out):,} rows so far")
        d += timedelta(days=1)
    return pd.DataFrame(out)
