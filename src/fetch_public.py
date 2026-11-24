"""Fetch the public context data (1 request per second at most, generic User-Agent, no key).

    python src/fetch_public.py

1. ECB Data Portal, payment statistics: value of fraudulent credit transfers (millions of EUR, UNIT_MULT = 6),
   half-yearly, for the EU (B0), the euro area (U2), Spain and France. Series key and extraction date are stored.
2. Regulation (EU) 2024/1624 (AMLR), English text from the Publications Office: only the article numbers and titles
   cited in docs/regulatory_context.md are extracted (no legal advice).
Outputs: data/public/ecb_credit_transfer_fraud.csv, data/public/amlr_articles.csv
"""
import io
import re
import time
from datetime import date
from html import unescape
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "public"
UA = {"User-Agent": "aml-case-study/1.0"}
ECB = "https://data-api.ecb.europa.eu/service/data/PAY/H.{zone}.W0.CT0.1.F.N.EUR?format=csvdata"
AMLR = "https://publications.europa.eu/resource/celex/32024R1624"
ZONES = {"B0": "EU", "U2": "Euro area", "ES": "Spain", "FR": "France"}
KEYWORDS = ["Ongoing monitoring", "Record retention", "Reporting of suspicions", "Customer due diligence measures",
            "Scope of application of enhanced due diligence"]


def ecb():
    rows = []
    for z, label in ZONES.items():
        r = requests.get(ECB.format(zone=z), headers=UA, timeout=60)
        time.sleep(1)
        if r.status_code != 200:
            print("ECB", z, r.status_code)
            continue
        d = pd.read_csv(io.StringIO(r.text))
        d = d[["KEY", "TIME_PERIOD", "OBS_VALUE", "UNIT_MULT"]].rename(columns={"KEY": "series_key", "TIME_PERIOD": "period",
                                                                            "OBS_VALUE": "value_eur_m"})
        d["zone"], d["zone_label"] = z, label
        rows.append(d)
    out = pd.concat(rows)
    out["extracted_on"] = date.today().isoformat()
    out.to_csv(OUT / "ecb_credit_transfer_fraud.csv", index=False)
    return out


def amlr():
    r = requests.get(AMLR, headers={**UA, "Accept": "application/xhtml+xml;q=1, text/html;q=0.9", "Accept-Language": "eng"},
                     timeout=120)
    r.raise_for_status()
    text = unescape(re.sub(r"<[^>]+>", "\n", r.text)).replace("\xa0", " ")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows = []
    for i, l in enumerate(lines[:-1]):
        m = re.fullmatch(r"Article (\d+)", l)
        if m and any(lines[i + 1].lower().startswith(k.lower()) for k in KEYWORDS):
            rows.append({"article": int(m.group(1)), "title": lines[i + 1]})
    out = pd.DataFrame(rows).drop_duplicates("article")
    out["source"] = AMLR
    out["mentions_ongoing_monitoring"] = text.lower().count("ongoing monitoring")
    out["extracted_on"] = date.today().isoformat()
    out.to_csv(OUT / "amlr_articles.csv", index=False)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    e = ecb()
    print(e.groupby("zone").tail(3)[["zone", "period", "value_eur_m"]].to_string(index=False))
    time.sleep(1)
    print(amlr().to_string(index=False))


if __name__ == "__main__":
    main()
