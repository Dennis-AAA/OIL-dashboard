#!/usr/bin/env python3
"""Rebuild WTI/OVX indicator series for the static dashboard.

Sources:
  - Yahoo Finance CL=F daily close
  - CBOE _OVX historical daily close
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
DISPLAY_START = date(2023, 9, 11)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_wti() -> list[dict]:
    period1 = int(datetime(2022, 11, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(time.time())
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/CL=F"
        f"?period1={period1}&period2={period2}&interval=1d"
        "&events=div%2Csplit&includePrePost=false"
    )
    raw = fetch_json(url)
    result = raw["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    rows: dict[date, dict] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=NY).date()
        rows[d] = {"date": d, "wti": float(close)}
    return [rows[d] for d in sorted(rows)]


def load_ovx() -> dict[date, float]:
    raw = fetch_json("https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/_OVX.json")
    out: dict[date, float] = {}
    for row in raw["data"]:
        try:
            out[date.fromisoformat(row["date"])] = float(row["close"])
        except (TypeError, ValueError):
            continue
    return out


def rv_at(rows: list[dict], i: int, n: int) -> float | None:
    rets: list[float] = []
    j = i
    while j >= 0 and len(rets) < n:
        r = rows[j]["r"]
        if r is not None:
            rets.append(r)
        j -= 1
    if len(rets) < n:
        return None
    return 100.0 * math.sqrt(252.0 * sum(x * x for x in rets) / n)


def sma_at(rows: list[dict], i: int, n: int) -> float | None:
    if i + 1 < n:
        return None
    return sum(rows[k]["wti"] for k in range(i - n + 1, i + 1)) / n


def percentile_rank(value: float, hist: list[float]) -> float:
    below = sum(1 for x in hist if x < value)
    equal = sum(1 for x in hist if x == value)
    return 100.0 * (below + 0.5 * equal) / len(hist)


def rnd(x: float | None, n: int = 4) -> float | None:
    return None if x is None else round(x, n)


def quikstrike() -> dict:
    series_path = DATA / "series_3y.json"
    if series_path.is_file():
        try:
            prev = json.loads(series_path.read_text(encoding="utf-8"))
            qs = prev.get("quikstrike")
            if isinstance(qs, dict) and qs.get("chain"):
                return qs
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "extract_date": "2026-09-13",
        "settle_date": "2026-09-11",
        "root": "LOV6",
        "expiry": "2026-09-17",
        "dte": 4.02,
        "F": 99.99,
        "ref_vol": 62.57,
        "call_wall": 100,
        "put_wall": 90,
        "rr_25d": 9.44,
        "rr_convention": "call_minus_put",
        "rr_note": "call-rich",
        "atm_gamma": 0.061,
        "oi_put_call": 1.62,
        "chain_note": (
            "仅含已知行权价隐含波动；伽马密度仅含先前计算的峰值"
            "（看涨约1005@100，看跌约430@90），其余行权价密度未知故不填。115无已知波动。"
        ),
        "chain": [
            {"strike": 85, "vol": 68.4, "call_dens": None, "put_dens": None},
            {"strike": 90, "vol": 62.51, "call_dens": None, "put_dens": 430},
            {"strike": 95, "vol": 61.02, "call_dens": None, "put_dens": None},
            {"strike": 100, "vol": 62.57, "call_dens": 1005, "put_dens": None},
            {"strike": 105, "vol": 68.66, "call_dens": None, "put_dens": None},
            {"strike": 110, "vol": 75.28, "call_dens": None, "put_dens": None},
            {"strike": 115, "vol": None, "call_dens": None, "put_dens": None},
        ],
    }


def main() -> None:
    wti = load_wti()
    ovx_map = load_ovx()
    for i, row in enumerate(wti):
        if i == 0:
            row["r"] = None
        else:
            prev = wti[i - 1]["wti"]
            row["r"] = math.log(row["wti"] / prev) if prev > 0 and row["wti"] > 0 else None

    ovx_hist: list[float] = []
    series = []
    for i, row in enumerate(wti):
        ovx = ovx_map.get(row["date"])
        rv10 = rv_at(wti, i, 10)
        rv20 = rv_at(wti, i, 20)
        sma50 = sma_at(wti, i, 50)
        sma200 = sma_at(wti, i, 200)
        if ovx is not None:
            ovx_hist.append(ovx)
            ovx_pctile = percentile_rank(ovx, ovx_hist[-252:]) if len(ovx_hist) >= 20 else None
        else:
            ovx_pctile = None
        if row["date"] < DISPLAY_START:
            continue
        series.append(
            {
                "date": row["date"].isoformat(),
                "wti": rnd(row["wti"]),
                "ovx": rnd(ovx),
                "rv10": rnd(rv10),
                "rv20": rnd(rv20),
                "iv_rv20": rnd(None if ovx is None or rv20 is None else ovx - rv20),
                "sma50": rnd(sma50),
                "sma200": rnd(sma200),
                "ovx_pctile": rnd(ovx_pctile, 2),
                "wti_vs_sma50": rnd(None if not sma50 else 100.0 * (row["wti"] / sma50 - 1.0)),
            }
        )

    qs = quikstrike()
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "display_start": DISPLAY_START.isoformat(),
            "display_end": series[-1]["date"],
            "n_obs": len(series),
            "wti": {"symbol": "CL=F", "source": "Yahoo Finance chart API", "field": "daily close"},
            "ovx": {"symbol": "_OVX", "source": "CBOE delayed historical chart API", "field": "daily close"},
            "formulas": {
                "r": "ln(wti_t / wti_{t-1})",
                "rv_n": "100 * sqrt(252 * mean(r^2, n))  close-to-close, n in {10,20}",
                "iv_rv20": "OVX - RV20",
                "sma_n": "n-day simple moving average of WTI close",
                "ovx_pctile": "percentile rank of OVX among last 252 available OVX closes (0-100)",
                "wti_vs_sma50": "100 * (WTI / SMA50 - 1)",
            },
            "quikstrike": (
                "Snapshot facts from 2026-09-13 extract / 2026-09-11 settle. "
                "Chain vols and dens peaks are only the known values; nothing else invented."
            ),
        },
        "series": series,
        "quikstrike": qs,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "series_3y.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snap_path = DATA / "quikstrike_snapshot.json"
    # Dedicated live LOV6 snapshot stays as uploaded; do not replace it with the series chain blob.
    if not snap_path.is_file():
        snap_path.write_text(json.dumps(qs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "series.js").write_text(
        "window.OIL_DASHBOARD_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {len(series)} rows {series[0]['date']} → {series[-1]['date']}")
    merge = ROOT / "scripts" / "merge_uso_into_series.py"
    if merge.is_file() and (DATA / "uso_options_snapshot.json").is_file():
        subprocess.run([sys.executable, str(merge)], cwd=str(ROOT), check=False)
    scorecard = ROOT / "scripts" / "build_wti_scorecard.py"
    if scorecard.is_file() and (DATA / "wti_scorecard.json").is_file():
        subprocess.run([sys.executable, str(scorecard)], cwd=str(ROOT), check=False)


if __name__ == "__main__":
    main()
