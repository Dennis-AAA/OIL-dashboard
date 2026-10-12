#!/usr/bin/env python3
"""Merge quikstrike_extract + snapshot into series_3y.json / series.js. Preserve public series."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_js(path: Path) -> dict:
    text = path.read_text()
    assert "window.OIL_DASHBOARD_DATA" in text
    payload = text.split("=", 1)[1].strip()
    if payload.endswith(";"):
        payload = payload[:-1]
    return json.loads(payload)


def main() -> None:
    series_path = DATA / "series_3y.json"
    js_path = DATA / "series.js"
    extract_path = DATA / "quikstrike_extract.json"
    snap_path = DATA / "quikstrike_snapshot.json"
    pub_path = DATA / "public_refresh_summary.json"

    if series_path.exists():
        s = json.loads(series_path.read_text())
    else:
        s = load_js(js_path)

    extract = json.loads(extract_path.read_text())
    snap = json.loads(snap_path.read_text())
    pub = json.loads(pub_path.read_text()) if pub_path.exists() else {}

    # Build dens-enriched chain near ATM (±~25 strikes of F) for dashboard smile/gex
    F = float(extract.get("F") or snap.get("F"))
    rows = extract.get("rows") or []
    chain = []
    for r in rows:
        strike = r.get("strike")
        if strike is None:
            continue
        try:
            k = float(strike)
        except (TypeError, ValueError):
            continue
        if abs(k - F) > 25:
            continue
        gamma = r.get("gamma")
        call_oi = r.get("call_oi")
        put_oi = r.get("put_oi")
        dens_call = r.get("dens_call")
        dens_put = r.get("dens_put")
        if dens_call is None and gamma is not None and call_oi is not None:
            dens_call = float(gamma) * float(call_oi)
        if dens_put is None and gamma is not None and put_oi is not None:
            dens_put = float(gamma) * float(put_oi)
        dens_total = None
        if dens_call is not None or dens_put is not None:
            dens_total = (dens_call or 0) + (dens_put or 0)
        chain.append(
            {
                "strike": k,
                "call": r.get("call"),
                "put": r.get("put"),
                "call_settle": r.get("call_settle"),
                "put_settle": r.get("put_settle"),
                "vol": r.get("vol"),
                "call_delta": r.get("call_delta"),
                "put_delta": r.get("put_delta"),
                "gamma": gamma,
                "vega": r.get("vega"),
                "theta": r.get("theta"),
                "straddle": r.get("straddle"),
                "call_oi": call_oi,
                "put_oi": put_oi,
                "call_volume": r.get("call_volume"),
                "put_volume": r.get("put_volume"),
                "dens_call": dens_call,
                "dens_put": dens_put,
                "dens_total": dens_total,
            }
        )
    chain.sort(key=lambda x: x["strike"])

    rr = snap.get("rr_25d")
    if rr is None and isinstance(extract.get("skew"), dict):
        rr = extract["skew"].get("rr_25d")

    s["quikstrike"] = {
        "meta": {
            "asof": extract.get("asof") or snap.get("asof_page"),
            "expiry": extract.get("expiry") or snap.get("expiry"),
            "F": extract.get("F") or snap.get("F"),
            "ref_vol": extract.get("ref_vol") or snap.get("ref_vol"),
            "rr_25d": rr,
            "n_chain": len(chain),
            "n_extract_rows": len(rows),
            "source": extract.get("source")
            or "Live QuikStrike Pricing Sheets, Open Interest, Vol Tools, Futures Info",
        },
        "chain": chain,
    }

    # Merge snapshot into latest_snapshot; keep public wti/ovx and uso_options
    prev = s.get("latest_snapshot") or {}
    latest = dict(prev)
    for k, v in snap.items():
        if k == "uso_options":
            continue
        latest[k] = v
    if pub:
        if "wti_last" in pub:
            latest["wti"] = pub["wti_last"]
        if "ovx_last" in pub:
            latest["ovx"] = pub["ovx_last"]
    if "uso_options" in prev and "uso_options" not in latest:
        latest["uso_options"] = prev["uso_options"]
    s["latest_snapshot"] = latest

    if pub.get("as_of"):
        s["as_of"] = pub["as_of"]
        s["end"] = pub.get("end") or pub["as_of"]

    series_path.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n")
    js_path.write_text(
        "window.OIL_DASHBOARD_DATA = " + json.dumps(s, ensure_ascii=False) + ";\n"
    )
    print(
        json.dumps(
            {
                "as_of": s.get("as_of"),
                "F": s["quikstrike"]["meta"]["F"],
                "ref_vol": s["quikstrike"]["meta"]["ref_vol"],
                "rr_25d": s["quikstrike"]["meta"]["rr_25d"],
                "n_chain": len(chain),
                "call_wall": latest.get("call_wall"),
                "put_wall": latest.get("put_wall"),
                "wti": latest.get("wti"),
                "ovx": latest.get("ovx"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
