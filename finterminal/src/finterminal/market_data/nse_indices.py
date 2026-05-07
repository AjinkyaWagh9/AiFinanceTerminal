from __future__ import annotations
import csv
import io
from datetime import date

_BASE = "https://nsearchives.nseindia.com/content/indices"

def url_for(d: date) -> str:
    return f"{_BASE}/ind_close_all_{d.day:02d}{d.month:02d}{d.year}.csv"

def parse_csv(blob: bytes, *, trade_date: date) -> list[dict]:
    text = blob.decode("utf-8")
    out: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("Index Name", "").strip() != "Nifty 50":
            continue
        out.append({
            "trade_date": trade_date,
            "ticker": "_NIFTY50",
            "open":   float(row["Open Index Value"]),
            "high":   float(row["High Index Value"]),
            "low":    float(row["Low Index Value"]),
            "close":  float(row["Closing Index Value"]),
            "volume": int(float(row["Volume"])) if row.get("Volume") else None,
        })
    return out
