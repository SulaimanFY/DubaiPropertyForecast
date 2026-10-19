"""Find the request format of the Land Department's open data feed from its own web page scripts."""
import re
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 DubaiPropertyForecast/1.0"}
PAGE = "https://dubailand.gov.ae/en/open-data/real-estate-data/"


def main():
    html = requests.get(PAGE, headers=UA, timeout=60).text
    srcs = set(re.findall(r'src="([^"]+\.js[^"]*)"', html)) | set(re.findall(r"src='([^']+\.js[^']*)'", html))
    inline = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S)
    texts = [("inline", "\n".join(inline))]
    for s in sorted(srcs):
        url = s if s.startswith("http") else "https://dubailand.gov.ae" + (s if s.startswith("/") else "/" + s)
        try:
            texts.append((url, requests.get(url, headers=UA, timeout=60).text))
        except Exception as e:
            print("skip", url, e)
    print(f"{len(texts)} scripts")
    for name, t in texts:
        for kw in ("open-data/rents", "rents", "P_DATE_TYPE", "P_VERSION", "open-data/"):
            for m in re.finditer(re.escape(kw), t):
                a, b = max(0, m.start() - 300), min(len(t), m.end() + 500)
                snippet = re.sub(r"\s+", " ", t[a:b])
                print(f"--- {name} [{kw}]: {snippet}")
                break
    sys.stdout.flush()


if __name__ == "__main__":
    main()
