from __future__ import annotations
import csv
import io
import zipfile
from datetime import date

_BASE = "https://nsearchives.nseindia.com/content/historical/EQUITIES"
_MONTHS = ("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC")

def url_for(d: date) -> str:
    mmm = _MONTHS[d.month - 1]
    fname = f"cm{d.day:02d}{mmm}{d.year}bhav.csv.zip"
    return f"{_BASE}/{d.year}/{mmm}/{fname}"

def parse_zip(blob: bytes, *, trade_date: date) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        text = zf.read(name).decode("utf-8")
    out: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("SERIES", "").strip() != "EQ":
            continue
        out.append({
            "trade_date": trade_date,
            "ticker": row["SYMBOL"].strip(),
            "open":   float(row["OPEN"]),
            "high":   float(row["HIGH"]),
            "low":    float(row["LOW"]),
            "close":  float(row["CLOSE"]),
            "volume": int(float(row["TOTTRDQTY"])),
        })
    return out
