"""Is each data source reachable from where this runs? Prints one line per source."""
import json
from datetime import date, timedelta

import requests

UA = {"User-Agent": "DubaiPropertyForecast/1.0 (+https://github.com/SulaimanFY/DubaiPropertyForecast)"}


def probe(name, method, url, **kw):
    try:
        r = requests.request(method, url, timeout=60, headers={**UA, **kw.pop("headers", {})}, **kw)
        body = r.text[:160].replace("\n", " ")
        print(f"{name}: HTTP {r.status_code}, {len(r.content):,} bytes: {body}")
    except Exception as e:  # report and carry on: this is a diagnostic
        print(f"{name}: FAILED {type(e).__name__}: {e}")


def main():
    d = date.today() - timedelta(days=3)
    body = {"P_FROM_DATE": d.strftime("%m/%d/%Y"), "P_TO_DATE": (d + timedelta(days=1)).strftime("%m/%d/%Y"),
            "P_GROUP_ID": "1", "P_IS_OFFPLAN": "", "P_IS_FREE_HOLD": "", "P_AREA_ID": "", "P_USAGE_ID": "",
            "P_PROP_TYPE_ID": "", "P_TAKE": "5", "P_SKIP": "0", "P_SORT": "TRANSACTION_NUMBER_ASC"}
    probe("DLD live feed, sales", "POST", "https://gateway.dubailand.gov.ae/open-data/transactions",
          data=json.dumps(body), headers={"Content-Type": "application/json"})
    probe("DLD website", "GET", "https://dubailand.gov.ae/en/open-data/real-estate-data/")
    probe("data.dubai", "GET", "https://data.dubai/")
    probe("Dubai Pulse", "GET", "https://www.dubaipulse.gov.ae/")


if __name__ == "__main__":
    main()
