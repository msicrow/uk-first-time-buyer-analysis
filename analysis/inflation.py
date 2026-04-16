"""UK CPIH deflator helper.

Fetches the ONS CPIH All-Items index (series L522, 2015=100) from
ons.gov.uk, caches it locally, and exposes helpers to deflate nominal
£ series to Jan 2026 real pounds.

Why CPIH, not CPI or RPI: ONS's preferred headline measure, and the
National Statistic used for real-earnings comparisons. Covers owner-
occupier housing costs (OOH), so it's also a more honest deflator for
housing analysis than headline CPI (which excludes OOH).
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache" / "cpih_monthly.json"
ONS_URL = ("https://www.ons.gov.uk/economy/inflationandpriceindices/"
           "timeseries/l522/mm23/data")
UA = "Mozilla/5.0 (analysis script; michaelscrow@gmail.com)"

_MONTH = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _fetch() -> list[dict]:
    req = urllib.request.Request(
        ONS_URL, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data["months"]


def load_cpih() -> pd.Series:
    """Return a monthly CPIH series indexed by first-of-month Timestamp."""
    if CACHE.exists():
        rows = json.loads(CACHE.read_text())
    else:
        rows = _fetch()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(rows))

    parsed = []
    for row in rows:
        yr, mo = row["date"].split(" ")
        parsed.append((pd.Timestamp(year=int(yr), month=_MONTH[mo], day=1),
                       float(row["value"])))
    s = pd.Series(dict(parsed), name="cpih").sort_index()
    s.index.name = "Date"
    return s


def deflator(reference_date: pd.Timestamp) -> pd.Series:
    """Multiplier that converts nominal £ at each date into reference-date £.

    Example: deflator(Jan 2026) gives 1.0 at Jan 2026, ~1.47 at Jan 2012
    (because Jan 2012 pounds need to be multiplied by ~1.47 to have the
    same purchasing power as Jan 2026 pounds).
    """
    cpih = load_cpih()
    ref = cpih.loc[reference_date]
    return ref / cpih


if __name__ == "__main__":
    s = load_cpih()
    print(f"CPIH series: {s.index.min().date()} → {s.index.max().date()} "
          f"({len(s)} months)")
    print(f"Jan 2012 = {s.loc['2012-01-01']}")
    print(f"Jan 2026 = {s.loc['2026-01-01']}")
    total = s.loc["2026-01-01"] / s.loc["2012-01-01"] - 1
    print(f"CPIH inflation Jan 2012 → Jan 2026: {total*100:+.1f}%")
