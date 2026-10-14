#!/usr/bin/env python3
"""Databento (GLBX.MDP3) replacement for the QuikStrike builders.
Writes data/quikstrike_extract.json, quikstrike_snapshot.json,
quikstrike_refresh_summary.json, quikstrike_gex.csv (same names/schema, source="databento").
IV/greeks via Black-76 from CME settlement prices; OI from statistics schema.
Needs env DATABENTO_API_KEY. Usage: databento_refresh.py [--trade-date YYYY-MM-DD]"""
import os, sys, json, math, csv, argparse, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd, databento as db
from scipy.stats import norm
from scipy.optimize import brentq

DATA = Path(__file__).resolve().parent.parent / "data"
DS = "GLBX.MDP3"; R = 0.04; MAX_COST = 5.0
MON = "FGHJKMNQUVXZ"

def b76(F, K, T, s, cp):
    d1 = (math.log(F / K) + 0.5 * s * s * T) / (s * math.sqrt(T)); d2 = d1 - s * math.sqrt(T); df = math.exp(-R * T)
    if cp == "C": return df * (F * norm.cdf(d1) - K * norm.cdf(d2))
    return df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))

def greeks(F, K, T, s):
    d1 = (math.log(F / K) + 0.5 * s * s * T) / (s * math.sqrt(T)); df = math.exp(-R * T)
    g = df * norm.pdf(d1) / (F * s * math.sqrt(T))
    vega = df * F * norm.pdf(d1) * math.sqrt(T) / 100
    theta = -df * F * norm.pdf(d1) * s / (2 * math.sqrt(T)) / 365
    return df * norm.cdf(d1), df * (norm.cdf(d1) - 1), g, vega, theta

def iv(p, F, K, T, cp):
    intr = math.exp(-R * T) * max(0.0, (F - K) if cp == "C" else (K - F))
    if p is None or not np.isfinite(p) or p <= intr + 1e-6: return None
    try: return brentq(lambda s: b76(F, K, T, s, cp) - p, 1e-3, 10.0)
    except ValueError: return None

def get(c, schema, syms, start, end):
    cost = c.metadata.get_cost(dataset=DS, schema=schema, symbols=syms, stype_in="parent", start=start, end=end)
    print(f"cost {schema} {syms} {start}->{end}: ${cost:.4f}")
    if cost > MAX_COST: sys.exit(f"abort: cost {cost} > {MAX_COST}")
    # pull in <=8h chunks with retries: large LO.OPT statistics requests can hit the 60s gateway timeout (504)
    s0, e0 = pd.Timestamp(start), pd.Timestamp(end); parts = []
    while s0 < e0:
        s1 = min(s0 + pd.Timedelta(hours=8), e0)
        for k in range(3):
            try:
                parts.append(c.timeseries.get_range(dataset=DS, schema=schema, symbols=syms, stype_in="parent",
                             start=s0.strftime("%Y-%m-%dT%H:%M"), end=s1.strftime("%Y-%m-%dT%H:%M")).to_df()); break
            except db.BentoServerError as e:
                if k == 2: raise
                print(f"retry {schema} {s0}->{s1}: {e}")
        s0 = s1
    parts = [x for x in parts if len(x)]
    return (pd.concat(parts) if parts else pd.DataFrame()), cost

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--trade-date"); a = ap.parse_args()
    c = db.Historical(os.environ["DATABENTO_API_KEY"])
    end_avail = pd.Timestamp(c.metadata.get_dataset_range(dataset=DS)["end"])
    td = pd.Timestamp(a.trade_date) if a.trade_date else (end_avail.tz_convert("America/New_York").normalize().tz_localize(None))  # loop below walks back if settlements not yet published
    # walk back to find a trade date with final settlements
    costs = {}
    for _ in range(5):
        end_naive = end_avail.tz_convert("UTC").tz_localize(None) if end_avail.tzinfo else end_avail
        start = td.strftime("%Y-%m-%d")
        end = min(td + pd.Timedelta(days=4), end_naive).strftime("%Y-%m-%dT%H:%M")
        def_end = min(td + pd.Timedelta(days=1), end_naive).strftime("%Y-%m-%dT%H:%M")
        defs, costs["definition"] = get(c, "definition", ["LO.OPT", "CL.FUT"], start, def_end)
        st, costs["statistics"] = get(c, "statistics", ["LO.OPT", "CL.FUT"], (td - pd.offsets.BDay(1)).strftime("%Y-%m-%d"), end)
        st["ref_date"] = st["ts_ref"].dt.tz_convert("UTC").dt.date  # CME stats ts_ref = trade date 00:00 UTC
        settle = st[(st.stat_type == 3) & (st.ref_date == td.date())]
        if len(settle) > 100: break
        td -= pd.offsets.BDay(1)
    else: sys.exit("no settlement data found")
    defs = defs.sort_index().groupby("instrument_id").last()
    opts = defs[defs.instrument_class.isin(["C", "P"]) & (defs.asset == "LO")]
    trade_close = pd.Timestamp(td.date()).tz_localize("America/New_York") + pd.Timedelta(hours=14, minutes=30)
    exps = sorted(e for e in opts.expiration.unique() if e > trade_close)
    exp = exps[0]; o = opts[opts.expiration == exp].copy()
    und = o.underlying.iloc[0]; osym = o.raw_symbol.iloc[0].split(" ")[0]
    fut_id = defs[(defs.raw_symbol == und) & (defs.instrument_class == "F")].index[0]
    sp = settle.sort_values("ts_recv").groupby("instrument_id").price.last()
    F = float(sp.get(fut_id))
    prev = st[(st.stat_type == 3) & (st.instrument_id == fut_id) & (st.ref_date < td.date())]
    oi = st[st.stat_type == 9].sort_values("ts_recv").groupby("instrument_id").quantity.last()
    oi_dates = st[st.stat_type == 9].groupby("instrument_id").ref_date.max()
    vol = st[(st.stat_type == 6) & (st.ref_date == td.date())].sort_values("ts_recv").groupby("instrument_id").quantity.last()
    T = (exp - trade_close).total_seconds() / 86400 / 365; dte = round(T * 365, 2)
    o["settle"] = o.index.map(sp); o["oi"] = o.index.map(oi).fillna(0).astype(int); o["vol_q"] = o.index.map(vol)
    rows = []
    for K, g in o.groupby("strike_price"):
        cc = g[g.instrument_class == "C"]; pp = g[g.instrument_class == "P"]
        cs = float(cc.settle.iloc[0]) if len(cc) and pd.notna(cc.settle.iloc[0]) else None
        ps = float(pp.settle.iloc[0]) if len(pp) and pd.notna(pp.settle.iloc[0]) else None
        # OTM side IV
        side = ("C", cs) if K >= F else ("P", ps)
        s = iv(side[1], F, K, T, side[0]) or iv(cs if side[0] == "P" else ps, F, K, T, "C" if side[0] == "P" else "P")
        r = {"strike": float(K), "call": cs, "put": ps, "call_settle": cs, "put_settle": ps,
             "call_oi": int(cc.oi.sum()) if len(cc) else 0, "put_oi": int(pp.oi.sum()) if len(pp) else 0,
             "call_volume": (int(cc.vol_q.iloc[0]) if len(cc) and pd.notna(cc.vol_q.iloc[0]) else None),
             "put_volume": (int(pp.vol_q.iloc[0]) if len(pp) and pd.notna(pp.vol_q.iloc[0]) else None)}
        if s:
            cd, pd_, gm, vg, th = greeks(F, K, T, s)
            r.update(vol=round(s * 100, 2), call_delta=round(cd, 4), put_delta=round(pd_, 4), gamma=round(gm, 5), vega=round(vg, 5), theta=round(th, 4))
        else: r.update(vol=None, call_delta=None, put_delta=None, gamma=None, vega=None, theta=None)
        r["volatility"] = r["vol"]; r["straddle"] = round(cs + ps, 4) if cs is not None and ps is not None else None
        r.update(bp_per_day=None, bp_vol=None, bs_vol=None, row_class="", oi_join_strike=float(K))
        gm = r["gamma"] or 0
        r["dens_call"] = round(gm * r["call_oi"], 3); r["dens_put"] = round(gm * r["put_oi"], 3)
        # dealer GEX ($ per 1% move, short calls/long puts convention: calls +, puts -), 1000 bbl multiplier
        r["gex_usd_1pct"] = round(gm * (r["call_oi"] - r["put_oi"]) * 1000 * F * F * 0.01, 0)
        rows.append(r)
    good = [r for r in rows if r["vol"]]
    ks = np.array([r["strike"] for r in good]); vs = np.array([r["vol"] for r in good])
    atm = float(np.interp(F, ks, vs))
    def vol_at_delta(target, key):
        cand = [r for r in good if r[key] is not None]
        x = np.array([r[key] for r in cand]); y = np.array([r["vol"] for r in cand]); i = np.argsort(x)
        return float(np.interp(target, x[i], y[i]))
    v25c = vol_at_delta(0.25, "call_delta"); v25p = vol_at_delta(-0.25, "put_delta"); rr = round(v25c - v25p, 2)
    cw = max(rows, key=lambda r: r["dens_call"]); pw = max(rows, key=lambda r: r["dens_put"])
    gp = max(rows, key=lambda r: r["dens_call"] + r["dens_put"])
    atm_row = min(good, key=lambda r: abs(r["strike"] - F))
    cot = sum(r["call_oi"] for r in rows); pot = sum(r["put_oi"] for r in rows)
    yy = osym[-1]; label = exp.tz_convert("America/New_York").strftime("%-d %b %Y")
    asof = dt.date.today().isoformat(); tds = td.strftime("%Y-%m-%d")
    chg = round(F - float(prev.sort_values("ts_recv").price.iloc[-1]), 2) if len(prev) else None
    oi_td = str(max(oi_dates[o.index.intersection(oi_dates.index)])) if len(oi_dates) else None
    src = f"Databento {DS} (definition + statistics: settlement, open interest, cleared volume); IV/greeks Black-76 r={R}"
    blockers = []
    if chg is None: blockers.append("prior-day futures settlement not in pulled window; underlying_change null")
    blockers.append("range (session high-low) not sourced; null")
    extract = {"source": "databento", "source_detail": src, "asof": asof, "asof_page": asof, "trade_date": tds, "settlement_date": tds,
        "oi_trade_date": oi_td, "vol_curve_date": tds, "F": F, "underlying_F": F, "underlying_change": chg, "range": None,
        "ref_vol": round(atm, 2), "ref_vol_units": "percent", "expiry": osym, "expiry_label": label,
        "expiry_date": exp.tz_convert("America/New_York").strftime("%Y-%m-%d"), "dte": dte,
        "product": "WTI Crude Oil (LO|CL)", "option_symbol": osym, "underlying_symbol": und,
        "heading": f"WTI Crude Oil (LO|CL) {osym} ({dte} DTE) vs {F} at {atm:.2f}% Volatility (Databento settle {tds})",
        "skew": {"rr_25d": rr, "vol_25c": round(v25c, 2), "vol_25p": round(v25p, 2)}, "rows": rows}
    snap = {"source": "databento", "source_detail": src, "asof_page": asof, "trade_date": tds, "F": F, "ref_vol": round(atm, 2),
        "expiry": osym, "expiry_date": extract["expiry_date"], "dte": dte, "atm_vol": round(atm, 2),
        "vol_95": round(float(np.interp(0.95 * F, ks, vs)), 2), "vol_105": round(float(np.interp(1.05 * F, ks, vs)), 2),
        "rr_25d": rr, "rr_note": f"Black-76 IV interpolated at call delta 0.25 ({v25c:.2f}) minus put delta -0.25 ({v25p:.2f}) from settlements",
        "call_wall": cw["strike"], "call_wall_dens": cw["dens_call"], "put_wall": pw["strike"], "put_wall_dens": pw["dens_put"],
        "gamma_peak_strike": gp["strike"], "gamma_peak_dens": round(gp["dens_call"] + gp["dens_put"], 3),
        "atm_gamma": atm_row["gamma"], "atm_vega": atm_row["vega"], "atm_theta": atm_row["theta"],
        "oi_put_call": round(pot / cot, 2) if cot else None, "call_oi_total": cot, "put_oi_total": pot,
        "net_gex_usd_1pct": sum(r["gex_usd_1pct"] for r in rows),
        "oi_scope": f"{osym}_single_expiry", "futures_backwardation": [], "blockers": blockers, "source_url": "https://databento.com (GLBX.MDP3)",
        "databento_cost_usd": costs}
    n_oi = sum(1 for r in rows if r["call_oi"] + r["put_oi"] > 0)
    summ = {"source": "databento", "asof": asof, "trade_date": tds, "F": F, "ref_vol": round(atm, 2), "rr_25d": rr,
        "call_wall": cw["strike"], "put_wall": pw["strike"], "expiry": osym, "dte": dte, "n_rows": len(rows), "oi_matched": n_oi,
        "blockers": blockers, "databento_cost_usd": costs}
    for n, obj in [("quikstrike_extract.json", extract), ("quikstrike_snapshot.json", snap), ("quikstrike_refresh_summary.json", summ)]:
        (DATA / n).write_text(json.dumps(obj, indent=2))
    cols = ["strike","call","put","call_settle","put_settle","vol","call_delta","put_delta","gamma","vega","theta","straddle","call_oi","put_oi","call_volume","put_volume","dens_call","dens_put","dens_total","gex_usd_1pct"]
    with open(DATA / "quikstrike_gex.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in rows: w.writerow(["" if (v := (r["dens_call"] + r["dens_put"] if k == "dens_total" else r.get(k))) is None else v for k in cols])
    print(json.dumps(summ, indent=1)); print("n_strikes_with_oi", n_oi, "vol_25c/25p", v25c, v25p, "gex_peak", gp["strike"])

if __name__ == "__main__": main()
