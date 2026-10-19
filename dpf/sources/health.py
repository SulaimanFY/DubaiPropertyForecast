"""Is each data source reachable from where this runs, and how far back does the live feed go?"""
import json
from datetime import date, timedelta

import requests

UA = {"User-Agent": "DubaiPropertyForecast/1.0 (+https://github.com/SulaimanFY/DubaiPropertyForecast)"}
GW = "https://gateway.dubailand.gov.ae/open-data"


def probe(name, method, url, show=160, **kw):
    try:
        r = requests.request(method, url, timeout=60, headers={**UA, **kw.pop("headers", {})}, **kw)
        print(f"{name}: HTTP {r.status_code}, {len(r.content):,} bytes: {r.text[:show]!r}")
        return r
    except Exception as e:  # report and carry on: this is a diagnostic
        print(f"{name}: FAILED {type(e).__name__}: {e}")


def feed(path, d, extra, take=2):
    body = {"P_FROM_DATE": d.strftime("%m/%d/%Y"), "P_TO_DATE": d.strftime("%m/%d/%Y"),
            "P_TAKE": str(take), "P_SKIP": "0", **extra}
    try:
        r = requests.post(f"{GW}/{path}", data=json.dumps(body), timeout=90,
                          headers={**UA, "Content-Type": "application/json"})
        js = r.json()
        res = (js.get("response") or {}).get("result") or []
        total = res[0].get("TOTAL") if res else 0
        errs = js.get("validationErrorsList")
        print(f"{path} {d}: HTTP {r.status_code}, total {total}, errors {errs}")
        return res
    except Exception as e:
        print(f"{path} {d}: FAILED {type(e).__name__}: {e}")
        return []


def main():
    sales = {"P_GROUP_ID": "1", "P_IS_OFFPLAN": "", "P_IS_FREE_HOLD": "", "P_AREA_ID": "", "P_USAGE_ID": "",
             "P_PROP_TYPE_ID": "", "P_SORT": "TRANSACTION_NUMBER_ASC"}
    rents = {"P_DATE_TYPE": "0", "P_IS_FREE_HOLD": "", "P_AREA_ID": "", "P_USAGE_ID": "", "P_PROP_TYPE_ID": "",
             "P_VERSION": "", "P_SORT": "CONTRACT_NUMBER_ASC"}
    recent = date.today() - timedelta(days=3)
    for d in (recent, date(2026, 1, 15), date(2025, 12, 15), date(2025, 6, 16), date(2023, 6, 15), date(2019, 6, 17), date(2012, 6, 18)):
        res = feed("transactions", d, sales)
        if d == recent and res:
            print("  sales fields:", sorted(res[0].keys()))
            print("  sample:", json.dumps(res[0], ensure_ascii=False)[:900])
    for d in (recent, date(2026, 1, 15), date(2025, 12, 15), date(2025, 6, 16), date(2019, 6, 17)):
        res = feed("rents", d, rents)
        if d == recent and res:
            print("  rent fields:", sorted(res[0].keys()))
            print("  sample:", json.dumps(res[0], ensure_ascii=False)[:900])
    probe("DLD open data page", "GET", "https://dubailand.gov.ae/en/open-data/real-estate-data/", show=0)
    probe("data.dubai", "GET", "https://data.dubai/")
    probe("Dubai Pulse", "GET", "https://www.dubaipulse.gov.ae/")


if __name__ == "__main__":
    main()
