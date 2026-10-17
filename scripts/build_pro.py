#!/usr/bin/env python3
"""Build /pro/ (方向波动看板 replica) static JSON.
Sources: Databento GLBX.MDP3 (futures ohlcv-1d continuous .v.0; options definition+statistics for listed 25Δ/15Δ RR, ATM IV, OI×Γ GEX),
Yahoo chart API (CBOE vol indices VIX/VIX3M/VIX9D/VVIX/SKEW/OVX/GVZ/EVZ), CFTC public reporting (COT disaggregated / TFF).
Needs env DATABENTO_API_KEY (never printed). Each Databento pull is cost-checked; abort if > $5.
Usage: build_pro.py [--no-cache]"""
import os, sys, json, math, time, argparse, datetime as dt, urllib.request, urllib.parse
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import norm
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pro" / "data"; CACHE = ROOT / ".cache_pro"
DS = "GLBX.MDP3"; MAX_COST = 5.0; R = 0.04
COSTS = {}
ASSETS = [  # id, name, ticker, quoteLabel, fut root, opt parent, multiplier, iv index, cftc code, cftc kind, desc
 dict(id="ES", name="美股", ticker="ES", ql="ES 期货", root="ES", opt="ES.OPT", mult=50, ivx="^VIX", cftc="13874A", kind="tff",
      desc="E-mini S&P 500。价格、Delta、Gamma 用 Databento ES 日线；Vega 用 CBOE VIX 日线；Skew 混合 CBOE SKEW 与 ES 期货期权挂牌 25Δ RR；体制看 VIX/VIX3M 与 VVIX。仓位用 CFTC TFF。GEX 用 ES 期货期权（季月，Databento）。"),
 dict(id="ZN", name="美债", ticker="ZN", ql="ZN 价", root="ZN", opt="OZN.OPT", mult=1000, ivx=None, cftc="043602", kind="tff",
      desc="10 年期国债期货价格（非收益率）。Vega/体制用 ZN 已实现分位。Skew 用 OZN 期货期权 25Δ RR（Databento）。仓位用 CFTC 10Y Note TFF。GEX 用 OZN 期货期权链。"),
 dict(id="EUR", name="EUR", ticker="6E", ql="EUR 期货", root="6E", opt="EUU.OPT", mult=125000, ivx="^EVZ", cftc="099741", kind="tff",
      desc="CME 欧元期货。价格用 6E 日线；IV 用 CBOE EVZ（若 Yahoo 无数据则用已实现分位）。Skew/GEX 用 EUU 期货期权（Databento）。仓位用 CFTC Euro FX TFF。"),
 dict(id="JPY", name="JPY", ticker="6J", ql="JPY 期货", root="6J", opt="JPU.OPT", mult=12500000, ivx=None, cftc="097741", kind="tff",
      desc="CME 日元期货（上涨 = 日元升值）。Skew/GEX 用 JPU 期货期权（Databento）。仓位用 CFTC Yen TFF。"),
 dict(id="GC", name="黄金", ticker="GC", ql="GC 期货", root="GC", opt="OG.OPT", mult=100, ivx="^GVZ", cftc="088691", kind="dis",
      desc="COMEX 黄金日线 + CBOE GVZ。Skew/GEX 用 OG 期货期权（Databento）。仓位用 CFTC 黄金分项。"),
 dict(id="HG", name="铜", ticker="HG", ql="HG 期货", root="HG", opt="HXE.OPT", mult=25000, ivx=None, cftc="085692", kind="dis",
      desc="COMEX 铜。Vega 用 HG 已实现分位。Skew/GEX 用 HXE 期货期权（Databento）。仓位用 CFTC 铜分项。"),
 dict(id="CL", name="WTI", ticker="CL", ql="CL 期货", root="CL", opt="LO.OPT", mult=1000, ivx="^OVX", cftc="067651", kind="dis",
      desc="WTI 原油日线 + CBOE OVX。Skew/GEX 用 LO 期货期权（Databento），墙即 CL 期货价位。仓位用 CFTC NYMEX WTI-Physical。"),
]
JPY = "JPY"

def client():
    import databento as db
    return db.Historical(os.environ["DATABENTO_API_KEY"])

def dbget(c, schema, syms, stype, start, end, tag):
    cost = c.metadata.get_cost(dataset=DS, schema=schema, symbols=syms, stype_in=stype, start=start, end=end)
    COSTS[tag] = round(float(cost), 4); print(f"cost {tag}: ${cost:.4f}", flush=True)
    if cost > MAX_COST: sys.exit(f"abort: {tag} cost {cost} > {MAX_COST}")
    if schema not in ("definition", "statistics"):
        return c.timeseries.get_range(dataset=DS, schema=schema, symbols=syms, stype_in=stype, start=start, end=end).to_df()
    # option definition/statistics: <=8h chunks + retries (large parents like LO.OPT/OG.OPT can hit the 60s gateway 504)
    import databento as db
    s0, e0 = pd.Timestamp(start), pd.Timestamp(end); parts = []
    while s0 < e0:
        s1 = min(s0 + pd.Timedelta(hours=4), e0)
        for k in range(5):
            try:
                parts.append(c.timeseries.get_range(dataset=DS, schema=schema, symbols=syms, stype_in=stype,
                             start=s0.strftime("%Y-%m-%dT%H:%M"), end=s1.strftime("%Y-%m-%dT%H:%M")).to_df()); break
            except db.BentoServerError as ex:
                if k == 4: raise
                print(f"retry {tag} {s0}->{s1}: {ex}", flush=True)
        s0 = s1
    parts = [x for x in parts if len(x)]
    return pd.concat(parts) if parts else pd.DataFrame()

def cached(name, fn, max_age_h, use_cache):
    p = CACHE / name
    if use_cache and p.exists() and time.time() - p.stat().st_mtime < max_age_h * 3600:
        return pd.read_parquet(p)
    df = fn(); CACHE.mkdir(exist_ok=True); df.to_parquet(p); return df

def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r: return json.load(r)

# ---------------- Black-76 ----------------
def b76(F, K, T, s, cp):
    d1 = (math.log(F / K) + 0.5 * s * s * T) / (s * math.sqrt(T)); d2 = d1 - s * math.sqrt(T); df = math.exp(-R * T)
    return df * (F * norm.cdf(d1) - K * norm.cdf(d2)) if cp == "C" else df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
def ivol(p, F, K, T, cp):
    intr = math.exp(-R * T) * max(0.0, (F - K) if cp == "C" else (K - F))
    if p is None or not np.isfinite(p) or p <= intr + 1e-9 * F: return None
    try: return brentq(lambda s: b76(F, K, T, s, cp) - p, 1e-3, 8.0)
    except ValueError: return None
def gam(F, K, T, s):
    d1 = (math.log(F / K) + 0.5 * s * s * T) / (s * math.sqrt(T)); df = math.exp(-R * T)
    return df * norm.cdf(d1), df * (norm.cdf(d1) - 1), df * norm.pdf(d1) / (F * s * math.sqrt(T))

# ---------------- data pulls ----------------
def pull_futures(c, use_cache):
    syms = [f"{a['root']}.v.0" for a in ASSETS]
    rng = c.metadata.get_dataset_range(dataset=DS)
    end_ts = pd.Timestamp((rng.get("schema", {}).get("ohlcv-1d") or {}).get("end") or rng["end"])  # clip to ohlcv-1d availability
    end = end_ts.strftime("%Y-%m-%dT%H:%M")
    df = cached("ohlcv.parquet", lambda: dbget(c, "ohlcv-1d", syms, "continuous", "2016-01-01", end, "ohlcv-1d futures .v.0 2016→"), 6, use_cache)
    out = {}
    for a in ASSETS:
        d = df[df.symbol == f"{a['root']}.v.0"].copy()
        d.index = pd.to_datetime(d.index).tz_convert("UTC").tz_localize(None).normalize()
        d = d[d.index.dayofweek < 5][["open", "high", "low", "close", "volume"]]
        d = d[~d.index.duplicated(keep="last")].astype(float)
        out[a["id"]] = d
    return out

def pull_options(c, a, use_cache):
    """single-expiry listed chain from CME settlements + OI. returns dict or None."""
    try:
        end_avail = pd.Timestamp(c.metadata.get_dataset_range(dataset=DS)["end"]).tz_localize(None)
        td = (end_avail.normalize() - pd.offsets.BDay(1))
        fut_parent = f"{a['root']}.FUT"
        for _ in range(4):
            s0 = td.strftime("%Y-%m-%d")
            defs = cached(f"def_{a['id']}_{s0}.parquet", lambda: dbget(c, "definition", [a["opt"], fut_parent], "parent", s0, (td + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), f"definition {a['opt']} {s0}"), 48, use_cache)
            e = min(td + pd.Timedelta(days=4), end_avail).strftime("%Y-%m-%dT%H:%M")
            st = cached(f"stat_{a['id']}_{s0}.parquet", lambda: dbget(c, "statistics", [a["opt"], fut_parent], "parent", (td - pd.offsets.BDay(1)).strftime("%Y-%m-%d"), e, f"statistics {a['opt']} {s0}"), 6, use_cache)
            st = st.copy(); st["ref_date"] = pd.to_datetime(st["ts_ref"]).dt.tz_convert("UTC").dt.date
            settle = st[(st.stat_type == 3) & (st.ref_date == td.date())]
            if len(settle) > 50: break
            td -= pd.offsets.BDay(1)
        else: return None
        defs = defs.sort_index().groupby("instrument_id").last()
        opts = defs[defs.instrument_class.isin(["C", "P"])]
        close = pd.Timestamp(td.date()).tz_localize("UTC") + pd.Timedelta(hours=20)
        exps = sorted(x for x in opts.expiration.unique() if x > close + pd.Timedelta(days=5))
        sp = settle.sort_values("ts_recv").groupby("instrument_id").price.last()
        oi = st[st.stat_type == 9].sort_values("ts_recv").groupby("instrument_id").quantity.last()
        for exp in exps[:3]:
            o = opts[opts.expiration == exp].copy()
            und = o.underlying.mode().iloc[0]; o = o[o.underlying == und]
            fid = defs[(defs.raw_symbol == und) & (defs.instrument_class == "F")].index
            if not len(fid) or fid[0] not in sp.index: continue
            F = float(sp[fid[0]]); T = (exp - close).total_seconds() / 86400 / 365
            o["settle"] = o.index.map(sp); o["oi"] = o.index.map(oi).fillna(0)
            rows = []
            for K, g in o.groupby("strike_price"):
                K = float(K)
                cc = g[g.instrument_class == "C"]; pp = g[g.instrument_class == "P"]
                cs = float(cc.settle.iloc[0]) if len(cc) and pd.notna(cc.settle.iloc[0]) else None
                ps = float(pp.settle.iloc[0]) if len(pp) and pd.notna(pp.settle.iloc[0]) else None
                s = ivol(cs, F, K, T, "C") if K >= F else ivol(ps, F, K, T, "P")
                if s is None: s = ivol(ps, F, K, T, "P") if K >= F else ivol(cs, F, K, T, "C")
                coi = float(cc.oi.sum()); poi = float(pp.oi.sum())
                r = dict(k=K, iv=s, coi=coi, poi=poi)
                if s:
                    cd, pdl, g_ = gam(F, K, T, s); r.update(cd=cd, pd=pdl, g=g_)
                rows.append(r)
            good = [r for r in rows if r["iv"] and 0.5 * F < r["k"] < 1.5 * F]
            if len(good) < 8: continue
            ks = np.array([r["k"] for r in good]); vs = np.array([r["iv"] for r in good]) * 100
            atm = float(np.interp(F, ks, vs))
            def at_delta(t, key):
                c_ = sorted((r[key], r["iv"] * 100) for r in good)
                return float(np.interp(t, [x for x, _ in c_], [y for _, y in c_]))
            c25, p25 = at_delta(0.25, "cd"), at_delta(-0.25, "pd"); c15, p15 = at_delta(0.15, "cd"), at_delta(-0.15, "pd")
            mult = a["mult"]
            bars = []
            for r in good:
                cg = r["g"] * r["coi"] * mult * F * F * 0.01 / 1e6; pg = -r["g"] * r["poi"] * mult * F * F * 0.01 / 1e6
                if r["coi"] + r["poi"] > 0: bars.append(dict(k=r["k"], c=round(cg, 3), p=round(pg, 3), n=round(cg + pg, 3)))
            if not bars: continue
            cw = max(bars, key=lambda b: b["c"])["k"]; pw = min(bars, key=lambda b: b["p"])["k"]
            # flip: cumulative net GEX across strikes (low→high) crossing − → + nearest spot
            nb = [b for b in bars if abs(b["k"] / F - 1) < 0.10]  # near-dated strikes window
            ks_b = [b["k"] for b in nb]; cum = np.cumsum([b["n"] for b in nb])
            flips = [ (ks_b[i - 1] * abs(cum[i]) + ks_b[i] * abs(cum[i - 1])) / (abs(cum[i]) + abs(cum[i - 1]) or 1)
                      for i in range(1, len(cum)) if cum[i - 1] < 0 <= cum[i]]
            flip = min(flips, key=lambda x: abs(x - F)) if flips else None
            near = [b for b in bars if abs(b["k"] / F - 1) < 0.12]
            n_oi = sum(1 for r in rows if r["coi"] + r["poi"] > 0)
            disp = sorted(near, key=lambda b: abs(b["c"]) + abs(b["p"]), reverse=True)[:32]
            return dict(assetId=a["id"], underlier=f"{und} 期权 ({o.raw_symbol.iloc[0].split(' ')[0]})", fut=und, exp=exp.strftime("%Y-%m-%d"),
                        asOf=td.strftime("%Y-%m-%d"), spot=F, dte=round(T * 365, 1),
                        rr=round(p25 - c25, 3), atmIv=round(atm, 3), callIv=round(c25, 3), putIv=round(p25, 3),
                        listed15=round(c15 - p15, 3), n=len(good), nOi=n_oi, quality="ok" if n_oi >= 25 else "thin",
                        net=round(sum(b["n"] for b in bars), 3), call=round(sum(b["c"] for b in bars), 3), put=round(sum(b["p"] for b in bars), 3),
                        callWall=cw, putWall=pw, flip=None if flip is None else round(flip, 6), peak=max(bars, key=lambda b: abs(b["n"]))["k"],
                        oiCall=int(sum(r["coi"] for r in rows)), oiPut=int(sum(r["poi"] for r in rows)),
                        bars=sorted(disp, key=lambda b: b["k"]))
        return None
    except SystemExit: raise
    except Exception as ex:
        print("options fail", a["id"], repr(ex)[:200]); return None

def pull_yahoo(sym):
    try:
        d = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=2y&interval=1d")["chart"]["result"][0]
        s = pd.Series(d["indicators"]["quote"][0]["close"], index=pd.to_datetime(d["timestamp"], unit="s").normalize()).dropna()
        return s[~s.index.duplicated(keep="last")]
    except Exception as ex:
        print("yahoo fail", sym, repr(ex)[:120]); return pd.Series(dtype=float)

def pull_cftc(a):
    ds = "gpe5-46if" if a["kind"] == "tff" else "72hh-3qpy"
    q = urllib.parse.urlencode({"$limit": 170, "$order": "report_date_as_yyyy_mm_dd DESC", "cftc_contract_market_code": a["cftc"]})
    try: rows = http_json(f"https://publicreporting.cftc.gov/resource/{ds}.json?{q}")
    except Exception as ex: print("cftc fail", a["id"], repr(ex)[:120]); return None
    if not rows: return None
    f = lambda r, k: float(r.get(k) or 0)
    if a["kind"] == "dis":
        groups = [("管理资金", "m_money_positions_long_all", "m_money_positions_short_all"),
                  ("生产/套保", "prod_merc_positions_long", "prod_merc_positions_short"),
                  ("掉期", "swap_positions_long_all", "swap__positions_short_all")]
    else:
        groups = [("杠杆基金", "lev_money_positions_long", "lev_money_positions_short"),
                  ("长期机构", "asset_mgr_positions_long", "asset_mgr_positions_short"),
                  ("做市商", "dealer_positions_long_all", "dealer_positions_short_all")]
    hist = {g: [f(r, l) - f(r, s) for r in rows] for g, l, s in groups}
    main = groups[0][0]; h = np.array(hist[main])
    pct = float((h[1:157] < h[0]).mean() * 100) if len(h) > 10 else None
    return dict(date=rows[0]["report_date_as_yyyy_mm_dd"][:10], market=rows[0]["market_and_exchange_names"], oi=f(rows[0], "open_interest_all"),
                groups=[dict(name=g, net=hist[g][0], chg=hist[g][0] - hist[g][1] if len(hist[g]) > 1 else None) for g, _, _ in groups],
                main=main, mainPct3y=pct, series=[dict(date=r["report_date_as_yyyy_mm_dd"][:10], net=hist[main][i]) for i, r in enumerate(rows[:104])][::-1])

# ---------------- indicators ----------------
def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
def atr(df, n=14):
    pc = df.close.shift(); tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()
def rv(lr, n, ann): return lr.rolling(n).std() * math.sqrt(ann) * 100
def pct_rank(s, v, n=252):
    s = s.dropna().iloc[-n:]
    return float((s < v).mean() * 100) if len(s) > 20 and v is not None and np.isfinite(v) else None
def semi(lr, n, ann):
    up = lr.where(lr > 0, 0.0); dn = lr.where(lr < 0, 0.0)
    return (np.sqrt((up ** 2).rolling(n).mean() * ann) - np.sqrt((dn ** 2).rolling(n).mean() * ann)) * 100  # + = upside heavier
def disc(raw):
    a = abs(raw); s = 0 if a < 0.35 else (1 if a < 1.0 else 2); return int(math.copysign(s, raw)) if s else 0
def fnum(x, d=2):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), d)
LBL = {2: "偏多", 1: "偏多", 0: "中性", -1: "偏空", -2: "偏空"}

def delta_cells(a, df, horizon):
    c = df.close; lr = np.log(c).diff()
    A = atr(df); atrp = (A / c * 100)
    if horizon == "daily": ks, kl, ma_s, ma_l, ann = (5, 10, 20), (60, 90), 20, 100, 252
    else: ks, kl, ma_s, ma_l, ann = (2, 3, 4), (8, 13), 4, 20, 52
    px = float(c.iloc[-1]); ap = float(atrp.iloc[-1])
    rets = {k: (px / float(c.iloc[-1 - k]) - 1) * 100 for k in set(ks + kl + (1,))}
    mom = np.mean([rets[k] / (ap * math.sqrt(k)) for k in ks])
    ma = c.rolling(ma_s).mean(); dist = (px - float(ma.iloc[-1])) / float(A.iloc[-1])
    rs = float(rsi(c).iloc[-1])
    raw_s = 0.45 * mom + 0.35 * float(np.clip(dist, -3, 3)) / 1.5 + 0.20 * (rs - 50) / 15
    flash_v = max((rets_k := [(px / float(c.iloc[-1 - k]) - 1) * 100 / (ap * math.sqrt(k)) for k in (1, 2, 3)]), key=abs)
    flash = "up" if flash_v > 1.2 else "down" if flash_v < -1.2 else "flat"
    ss = disc(raw_s); faded = flash != "flat" and ss == 0
    mal = c.rolling(ma_l).mean(); slope = (float(mal.iloc[-1]) - float(mal.iloc[-21 if horizon == 'daily' else -5])) / float(A.iloc[-1])
    above = 1 if px > float(mal.iloc[-1]) else -1
    momL = np.mean([rets[k] / (ap * math.sqrt(k)) for k in kl])
    raw_l = 0.45 * momL + 0.30 * float(np.clip(slope, -3, 3)) / 1.5 + 0.25 * above
    sl = disc(raw_l)
    def lab(s, long):
        if a["id"] == JPY and long and s != 0: base = "多JPY" if s > 0 else "空JPY"
        else: base = LBL[s]
        return base
    diverge = (ss != 0 and sl != 0 and np.sign(ss) != np.sign(sl)) or (ss == 0) != (sl == 0)
    l_lab = lab(sl, True)
    if sl != 0 and a["id"] != JPY: l_lab += "·确认" if np.sign(ss) == np.sign(sl) else "·结构观察"
    tone = lambda s: "bull" if s > 0 else "bear" if s < 0 else "neutral"
    short = dict(score=ss, raw=raw_s, label=lab(ss, False), tone=tone(ss), faded=faded, flash=flash, diverge=bool(diverge),
                 note=f"短窗 {rets[ks[0]]:+.2f}%，RSI {rs:.0f}，距均线 {dist:+.2f} ATR" + (f" · Flash {flash_v:+.1f}" if flash != "flat" else ""))
    long = dict(score=sl, raw=raw_l, label=l_lab, tone=tone(sl), faded=False, flash="flat", diverge=bool(diverge),
                note=f"{kl[0]} 窗 {rets[kl[0]]:+.2f}%，相对长均线 {'之上' if above > 0 else '之下'}")
    m = dict(ret1=rets[1], ret5=rets[ks[0]], ret20=rets.get(20, rets[ks[-1]]), ret60=rets[kl[0]], ret90=rets[kl[1]], rsi=rs, distMaAtr=dist)
    return short, long, m

def vol_cells(a, df, ivs, listed, extra):
    c = df.close; lr = np.log(c).diff()
    r5, r20, r60 = rv(lr, 5, 252), rv(lr, 20, 252), rv(lr, 60, 252)
    v5, v20, v60 = float(r5.iloc[-1]), float(r20.iloc[-1]), float(r60.iloc[-1])
    rvPct = pct_rank(r20, v20)
    iv = float(ivs.iloc[-1]) if ivs is not None and len(ivs) > 60 else None
    ivPct = pct_rank(ivs, iv) if iv is not None else None
    usePct = ivPct if ivPct is not None else rvPct
    vrp = (iv - v20) if iv is not None else None
    rising = v5 > v20
    # VEGA
    if usePct is None: vl, vt, vi = "中性", "neutral", 0.0
    elif usePct < 10 and rising: vl, vt, vi = "强买波", "bull", 0.9
    elif usePct < 25 and (rising or usePct < 12): vl, vt, vi = "买波", "bull", 0.55
    elif usePct > 90 and not rising: vl, vt, vi = "强卖波", "bear", 0.9
    elif usePct > 75 and not rising: vl, vt, vi = "卖波", "bear", 0.55
    else: vl, vt, vi = "中性", "neutral", 0.15
    vnote = (f"IV {iv:.1f} · 分位 {ivPct:.0f}% · RV20 {v20:.1f}" if iv is not None else f"RV20 {v20:.1f} · 1年分位 {rvPct:.0f}%（无上市 IV 指数）")
    if listed: vnote += f" · 挂牌 ATM {listed['atmIv']:.1f}"
    vega = dict(key="vega", label=vl, tone=vt, warn=False, intensity=vi, note=vnote)
    # SKEW (+ = put tail premium)
    srr = semi(lr, 20, 252); real = -float(srr.iloc[-1])  # + = downside heavier
    parts = []; skewIdx = extra.get("skew")
    if a["id"] == "ES" and skewIdx is not None:
        mix = 0.45 * (skewIdx - 140) / 12 + (0.40 * listed["rr"] / 3 if listed else 0) + 0.15 * real / 6
        parts.append(f"SKEW {skewIdx:.1f}")
    elif listed: mix = 0.85 * listed["rr"] / 3 + 0.15 * real / 6
    else: mix = real / 6
    if listed: parts.append(f"25Δ {listed['rr']:+.2f}")
    parts.append(f"实现 RR {real:+.1f}")
    warn = bool(listed and abs(listed["rr"]) > 0.5 and abs(real) > 1 and np.sign(listed["rr"]) != np.sign(real))
    sl = "偏空 RR" if mix >= 0.55 else "偏多 RR" if mix <= -0.55 else "中性"
    skew = dict(key="skew", label=sl, tone="bear" if mix >= 0.55 else "bull" if mix <= -0.55 else "neutral", warn=warn,
                intensity=min(1.0, abs(mix)), note=" · ".join(parts), mix=mix)
    # GAMMA
    ratio = v5 / v20 if v20 else 1
    mv = abs(float(lr.iloc[-5:].sum())) / (v20 / 100 * math.sqrt(5 / 252)) if v20 else 0
    if ratio > 1.6 or mv > 2.0:
        d = "上" if lr.iloc[-5:].sum() > 0 else "下"; gl, gt, gi = f"风暴·向{d}", "bear" if d == "下" else "bull", 0.9
    elif ratio > 1.15: gl, gt, gi = "初起·" + ("偏多" if lr.iloc[-5:].sum() > 0 else "偏空" if mv > 0.8 else "中性"), "watch", 0.5
    elif ratio < 0.85 and mv < 1.0: gl, gt, gi = "平静·收 theta", "watch", 0.25
    else: gl, gt, gi = "中性", "neutral", 0.1
    gamma = dict(key="gamma", label=gl, tone=gt, warn=False, intensity=gi, note=f"RV5/RV20={ratio:.2f} · 短窗位移 {mv:.2f}σ")
    # REGIME
    term = extra.get("term"); vvix = extra.get("vvix")
    if (usePct is not None and usePct > 80) or (vvix and vvix > 110) or (term and term > 1.0):
        if usePct is not None and usePct > 70 and ratio < 0.9 and not (term and term > 1.0): rl, rt, ri = "高Vol缓和", "watch", 0.5
        else: rl, rt, ri = "混乱", "bear", 0.7
    elif usePct is not None and usePct < 40: rl, rt, ri = "平静", "neutral", 0.15
    else: rl, rt, ri = "中性", "neutral", 0.1
    rnote = (f"期限 {term:.2f} · " if term else "") + (f"IV/RV 分位 {usePct:.0f}%" if usePct is not None else "")
    regime = dict(key="regime", label=rl, tone=rt, warn=False, intensity=ri, note=rnote)
    m = dict(rv5=v5, rv20=v20, rv60=v60, rvPct=rvPct, iv=iv, ivPct=ivPct, vrp=vrp, term=term, skewIdx=skewIdx, realizedRr=real,
             gammaRatio=ratio, listedRr=listed["rr"] if listed else None, listedAtmIv=listed["atmIv"] if listed else None,
             listedRrAsOf=listed["asOf"] if listed else None,
             listedRrNote=(f"{listed['underlier']} 25Δ RR {listed['rr']:+.2f}（{listed['exp']}）" if listed else "无挂牌链"))
    return vega, skew, gamma, regime, m

def weekly(df):
    w = df.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return w

def build_board(fut, opts, vix, horizon):
    rows = []
    for a in ASSETS:
        df = fut[a["id"]]; dfx = df if horizon == "daily" else weekly(df)
        short, long, m1 = delta_cells(a, dfx, horizon)
        ivs = vix.get(a["ivx"]) if a["ivx"] else None
        if ivs is not None and len(ivs) < 60: ivs = None
        extra = {}
        if a["id"] == "ES":
            v, v3, vv, sk = vix.get("^VIX"), vix.get("^VIX3M"), vix.get("^VVIX"), vix.get("^SKEW")
            if len(v) and len(v3): extra["term"] = float(v.iloc[-1] / v3.iloc[-1])
            if len(vv): extra["vvix"] = float(vv.iloc[-1])
            if len(sk): extra["skew"] = float(sk.iloc[-1])
        vega, skew, gamma, regime, m2 = vol_cells(a, df, ivs, opts.get(a["id"]), extra)
        heat = abs(short["score"]) + abs(long["score"]) + vega["intensity"] + skew["intensity"] + gamma["intensity"] + regime["intensity"]
        px = float(df.close.iloc[-1]); prev = float(df.close.iloc[-2])
        rows.append(dict(id=a["id"], name=a["name"], ticker=a["ticker"], quoteLabel=a["ql"], price=px, change1d=px - prev,
                         changePct=(px / prev - 1) * 100, spark=[fnum(x, 6) for x in dfx.close.iloc[-28:]],
                         short=short, long=long, vega=vega, skew=skew, gamma=gamma, regime=regime, heat=round(heat, 1),
                         diverge=short["diverge"], metrics={**m1, **m2}, desc=a["desc"]))
    fl = [f"{r['name']}{r['short']['label']}{r['short']['score']:+d}" for r in rows if r["short"]["score"] != 0]
    shortNote = "短线：仍存方向的是 " + "、".join(fl) + "，其余中性" if fl else "短线：全部中性"
    ll = [f"{r['name']}{r['long']['label'].split('·')[0]}{r['long']['score']:+d}" for r in sorted(rows, key=lambda r: -abs(r['long']['score'])) if r["long"]["score"] != 0]
    longNote = "长线：" + ("/".join(ll) if ll else "全部中性") + "（暂定结构偏向，非正式配置）"
    return rows, shortNote, longNote

def build_desk(a, df, listed, cftc, board_row, all_rows, vix):
    c = df.close; lr = np.log(c).diff(); px = float(c.iloc[-1])
    ma200 = c.rolling(200).mean(); ma100 = c.rolling(100).mean(); A = atr(df)
    dn = float(ma200.iloc[-1]); dpct = (px / dn - 1) * 100
    side = "多头" if px > dn else "空头"
    strength = float(np.clip(abs(px - dn) / float(A.iloc[-1]) / 8, 0, 1))
    status = "贴近翻转" if abs(dpct) < 2 else "持有"
    # seasonality: same calendar month, past 8 years
    mo = c.resample("ME").last(); mret = mo.pct_change() * 100
    cur_m = c.index[-1].month; samp = mret[(mret.index.month == cur_m) & (mret.index.year < c.index[-1].year)].dropna().iloc[-8:]
    smed = float(samp.median()) if len(samp) else 0; swin = float((samp > 0).mean() * 100) if len(samp) else 0
    stone = "bull" if smed > 0.5 and swin >= 55 else "bear" if smed < -0.5 and swin <= 45 else "neutral"
    # vol
    r5, r20, r60 = rv(lr, 5, 252), rv(lr, 20, 252), rv(lr, 60, 252)
    v20 = float(r20.iloc[-1]); vp60 = pct_rank(r20, v20, 60); m = board_row["metrics"]
    ivp = m.get("ivPct"); usep = ivp if ivp is not None else m.get("rvPct")
    vh = "高压" if (usep or 0) > 75 else "平静" if (usep or 50) < 25 else "中性"
    if a["id"] == "ES" and m.get("term") and m["term"] > 1: vh += " · 倒挂"
    # gamma-skew (realized proxy, + = call wing)
    g20 = semi(lr, 20, 252); g60 = semi(lr, 60, 252)
    real20 = float(g20.iloc[-1]); real60 = float(g60.iloc[-1])
    l15 = listed["listed15"] if listed else None
    mix = 0.85 * l15 + 0.15 * real20 if l15 is not None else real20
    hist = g20.dropna().iloc[-252:]; z = float((mix - hist.mean()) / hist.std()) if hist.std() > 0 else 0
    absP = float((hist.abs() < abs(mix)).mean() * 100)
    imp = r5 / r20 - 1; impv = float(imp.iloc[-1])
    greg = "风暴中间" if impv > 0.5 else "初起" if impv > 0.15 or abs(z) > 1 and impv > 0 else "平静" if impv < -0.15 and abs(z) < 1 else "初起" if abs(z) >= 0.4 else "平静"
    gside = "Call" if mix > 0 else "Put"
    playbook = {"平静": f"平静带 · 收 theta / 卖 gamma（{gside} Γ），避免追 Impulse", "初起": f"初起 · 小仓位跟 {gside} 翼，等 Impulse 确认",
                "风暴中间": "风暴中间 · 降杠杆，别逆着 Impulse 卖 gamma"}[greg]
    gamma = dict(z=z, absPctl=absP, side=gside, regime=greg, impulse=impv, rv5=float(r5.iloc[-1]), rv20=v20, realized20=real20,
                 realized60=real60, listed15=l15, listedAsOf=listed["asOf"] if listed else None, mix=mix, playbook=playbook,
                 read="正值 = 15Δ Call 比 15Δ Put 更贵 = 偏 Call Gamma。挂牌用 Databento 期货期权 15Δ call IV − 15Δ put IV；历史红柱用 20 日上涨日半波动 − 下跌日半波动，蓝线用 60 日同口径。没有逐日链，画不出 GEX 历史。")
    # GEX / flip (futures options → walls already in futures points, scale=1)
    gex = None
    if listed:
        g = dict(listed); g["scale"] = 1.0
        g["callWallFx"], g["putWallFx"], g["flipFx"] = g["callWall"], g["putWall"], g["flip"]
        S = g["spot"]; g["regime"] = ("正Γ钉住带" if g["net"] > 0 and g["putWall"] <= S <= g["callWall"] else "正Γ" if g["net"] > 0 else "负Γ带")
        if g["quality"] == "thin": g["regime"] = "薄链"
        g["playbook"] = (f"净 GEX {g['net']:+.2f}M（{'Call' if g['net'] > 0 else 'Put'} 主导） · Call 墙 {g['callWall']:g} / Put 墙 {g['putWall']:g}。" +
                         ("若做市商长 gamma，对冲会逆势、价格易被钉住。" if g["net"] > 0 else "若做市商短 gamma，下跌时对冲会顺势加空，波动易被放大。") + "墙不是硬支撑。")
        g["read"] = "GEX = OI × Γ × 合约乘数 × F² × 1%（百万美元/涨跌 1%）。Call 为正、Put 为负。CME 期货期权单到期 OI 加权 Γ 截面（Databento 结算价 + OI，Black-76），不是 dealer 多空。墙即期货价位。"
        lo, hi = sorted([g["putWall"], g["callWall"]]); g["pinLo"], g["pinHi"] = lo, hi; g["pinLoFx"], g["pinHiFx"] = lo, hi
        g["inPin"] = bool(lo <= S <= hi)
        g["gexBelow"] = round(sum(b["n"] for b in g["bars"] if b["k"] < S), 3); g["gexAbove"] = round(sum(b["n"] for b in g["bars"] if b["k"] >= S), 3)
        if g["flip"] is not None:
            dfp = (S / g["flip"] - 1); g["distFlipPct"] = dfp; g["flipDistEtf"] = S - g["flip"]; g["flipDistFx"] = S - g["flip"]
            g["flipSide"] = "贴着" if abs(dfp) < 0.003 else ("上" if dfp > 0 else "下")
            fr = "贴着 Flip" if g["flipSide"] == "贴着" else f"Flip {g['flipSide']}"
            if g["inPin"]: fr += " · 夹持中"
            elif S < lo or S > hi: fr += " · 墙已破"
            g["flipRegime"] = fr
            g["flipPlaybook"] = f"期货 {S:g} 相对 Flip {g['flip']:.4g}（{dfp * 100:+.2f}%）。Flip 下 = 本地 Put Γ 主导；Flip 上 = 本地 Call Γ 主导。夹持带 {lo:g}–{hi:g}。"
        else:
            g.update(distFlipPct=None, flipDistEtf=None, flipDistFx=None, flipSide="无", flipRegime="无交叉", flipPlaybook="近端行权价上净 GEX 没有由负转正的交叉。")
        g["flipRead"] = "Gamma Flip = 行权价由低到高累计净 GEX 由负转正的点（离现价最近）。不是趋势页的 200 日翻转价。没有逐日链，画不出 Flip 历史。"
        g["squeezeRead"] = ("净 GEX 为负、上方仍有 Call 墙，上涨时对冲可能追买，形态接近 squeeze 的一半。" if g["net"] < 0 and g["callWall"] > S else "净 GEX 为正，对冲偏逆势，不像 squeeze 形态。") + "但这是 OI 截面，不知道谁在短这些 call。不是警报。"
        gex = g
    # fair / target / story
    fair = float(ma100.iloc[-1]); fp = (px / fair - 1) * 100
    ftone = "bear" if fp > 8 else "bull" if fp < -8 else "neutral"; fh = "偏贵" if fp > 8 else "偏便宜" if fp < -8 else "中性"
    hi52, lo52 = float(c.iloc[-252:].max()), float(c.iloc[-252:].min())
    spath = px * (1 + smed / 100)
    me = board_row; others = [r for r in all_rows if r["id"] != a["id"]]
    om = "，".join(f"{r['name']}{'涨' if r['changePct'] > 0 else '跌'}" for r in sorted(others, key=lambda r: -abs(r["changePct"]))[:3])
    trend_sign = 1 if px > dn else -1; story = "顺势" if np.sign(me["changePct"]) == trend_sign else "逆势"
    # players
    if cftc:
        gs = cftc["groups"]; mg = gs[0]
        prow = f"{cftc['market']} · {cftc['date']}（周二仓位）· " + " · ".join(f"{x['name']}净 {x['net']:+,.0f}（周变 {x['chg']:+,.0f}）" for x in gs) + (f" · {mg['name']}净头寸 3 年分位 {cftc['mainPct3y']:.0f}%" if cftc["mainPct3y"] is not None else "")
        ptone = "bull" if (cftc["mainPct3y"] or 50) < 15 else "bear" if (cftc["mainPct3y"] or 50) > 85 else "neutral"
        pchip = dict(key="player", kicker="玩家", headline=f"{mg['name']} {'净多' if mg['net'] > 0 else '净空'}", detail=f"P{cftc['mainPct3y']:.0f}" if cftc["mainPct3y"] is not None else "", tone=ptone)
    else: prow = "CFTC 仓位暂未取到。"; pchip = dict(key="player", kicker="玩家", headline="无", detail="", tone="neutral")
    fmt = lambda x: f"{x:,.4g}" if abs(x) < 10 else f"{x:,.2f}"
    chips = [dict(key="trend", kicker="趋势", headline=f"{side} {status}", detail=f"{dpct:+.1f}%", tone="bull" if px > dn else "bear"),
             dict(key="season", kicker="季节性", headline={"bull": "偏多", "bear": "偏空", "neutral": "中性"}[stone], detail=f"{smed:+.1f}%", tone=stone),
             dict(key="vol", kicker="波动", headline=vh, detail=f"{(usep or 0):.0f}%", tone="bear" if "高压" in vh else "neutral"),
             dict(key="gamma", kicker="Gamma", headline=greg, detail=f"z{z:+.2f}", tone="bull" if mix > 0 else "bear"),
             dict(key="gex", kicker="GEX", headline=gex["regime"] if gex else "无链", detail=f"{gex['net']:+.2f}M" if gex else "", tone=("bull" if gex["net"] > 0 else "bear") if gex else "neutral"),
             dict(key="flip", kicker="Γ翻转", headline=gex["flipRegime"] if gex else "无链", detail=(f"{gex['distFlipPct'] * 100:+.1f}%" if gex and gex.get("distFlipPct") is not None else ""), tone="watch"),
             pchip,
             dict(key="fair", kicker="公允值", headline=fh, detail=f"{fp:+.1f}%", tone=ftone),
             dict(key="target", kicker="目标价", headline="技术", detail=f"200d {fmt(dn)}", tone="neutral"),
             dict(key="story", kicker="叙事", headline=story, detail="隔夜", tone="neutral")]
    rows = [dict(key="trend", title="趋势", body=f"{side} · 强度 {strength:.2f} · 现价 {fmt(px)} 距翻转价 {fmt(dn)}，还差 {dpct:+.1f}% · {status}"),
            dict(key="season", title="季节性", body=f"{cur_m}月中位回报 {smed:+.1f}% · 正收益概率 {swin:.0f}% · 样本 {len(samp)} 年" + (" · 弱信号，仅作边际参考" if stone == "neutral" or len(samp) < 8 else "")),
            dict(key="vol", title="波动", body=f"{vh} · RV20 60日分位 {vp60:.0f}% · " + (f"IV分位 {ivp:.0f}% · " if ivp is not None else "") + f"距减杠杆线 (75分位) 还差 {75 - (usep or 0):.0f}pp" + (f" · VRP {'偏贵' if m['vrp'] > 0 else '偏便宜'}" if m.get("vrp") is not None else "") + (f" · Vol(15C−15P) {l15:+.2f}（挂牌，call IV − put IV） · 期权截至 {listed['asOf']}" if listed else "")),
            dict(key="gamma", title="Gamma", body=f"Gamma-Skew z{z:+.2f}（相对该品种约1年） · 偏 {gside} Gamma · 体制 {greg} · |G-S| 历史分位 P{absP:.0f} · Impulse {impv:+.2f}（{'正向' if impv > 0 else '负向'}冲量）"),
            dict(key="gex", title="GEX", body=(f"净 {gex['net']:+.2f}M / 1% · Call {gex['call']:+.1f}M / Put {gex['put']:+.1f}M · Call墙 {gex['callWall']:g} / Put墙 {gex['putWall']:g} · Flip {gex['flip'] if gex['flip'] is not None else '无'} · {gex['underlier']} 到期 {gex['exp']} 截面 {gex['asOf']}" + (" · 薄链" if gex["quality"] == "thin" else "")) if gex else "没有可用的挂牌期权截面。"),
            dict(key="flip", title="Γ翻转", body=(gex["flipPlaybook"] + f" · Flip下净 {gex['gexBelow']:+.1f}M / 上净 {gex['gexAbove']:+.1f}M · 不是 200 日翻转价") if gex else "没有挂牌截面，算不出 Gamma Flip。"),
            dict(key="player", title="玩家", body=prow),
            dict(key="fair", title="公允值", body=f"{a['name']} 实际 {fmt(px)} / 模型 {fmt(fair)}（100 日均线） · {'高于' if fp > 0 else '低于'}模型 {fp:+.1f}% · {fh}"),
            dict(key="target", title="目标价", body=f"200d {fmt(dn)} · 52周高 {fmt(hi52)} / 低 {fmt(lo52)} · 季节性路径 {fmt(spath)}。券商 12M 目标价没有稳定的公开日更源，不编造数字。"),
            dict(key="story", title="叙事", body=f"{a['name']}{'上涨' if me['changePct'] > 0 else '下跌'} {me['changePct']:+.1f}% · {om} · 由期货日涨跌生成，不是研报共识引擎")]
    n = 420; idx = c.index[-n:]
    gu = c.rolling(20).mean() * (1 + r20 / 100 * math.sqrt(20 / 252)); gd = c.rolling(20).mean() * (1 - r20 / 100 * math.sqrt(20 / 252))
    chart = [dict(date=d.strftime("%Y-%m-%d"), px=fnum(c[d], 6), dn=fnum(ma200[d], 6), impulse=fnum(imp[d], 4), gUp=fnum(gu[d], 6), gDown=fnum(gd[d], 6),
                  gSkew=fnum(g20[d], 3), volAtm=fnum(r20[d] / 100, 4), volRr=fnum(g60[d], 3), deltaAdj=fnum(c[d] - ma200[d], 6)) for d in idx]
    return dict(id=a["id"], name=a["name"], ticker=a["ticker"], quoteLabel=a["ql"], price=px, asOf=c.index[-1].strftime("%Y-%m-%d"),
                chips=chips, rows=rows, chart=chart, gamma=gamma, gex=gex, cftc=cftc,
                footnotes=["翻转价 = 200 日均线；Gamma Flip 是挂牌净 Γ 累计由负转正的行权价，两套不要混。公允值 = 100 日均线。",
                           "Gamma-Skew 正 = Call 翼；最新点 85% 挂牌 15Δ（Databento 期货期权）+ 15% 实现 20d；历史柱/线是实现半波动代理。",
                           "GEX 是 CME 期货期权 OI×Γ 单到期截面（Call + / Put −），不是 dealer 库存。墙即期货价位。",
                           "玩家来自 CFTC 周报（商品分项 / 金融 TFF），不是盘中 CTA。"])

def clean(o):
    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list): return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)): return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, np.bool_): return bool(o)
    return o

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--no-cache", action="store_true"); a_ = ap.parse_args(); uc = not a_.no_cache
    OUT.mkdir(parents=True, exist_ok=True)
    c = client()
    fut = pull_futures(c, uc)
    opts = {}
    for a in ASSETS:
        o = pull_options(c, a, uc)
        if o: opts[a["id"]] = o; print(a["id"], "opt", o["exp"], "F", o["spot"], "RR", o["rr"], "ATM", o["atmIv"], "net", o["net"], "nOi", o["nOi"])
    vix = {s: pull_yahoo(s) for s in ["^VIX", "^VIX3M", "^VIX9D", "^VVIX", "^SKEW", "^OVX", "^GVZ", "^EVZ"]}
    cftc = {a["id"]: pull_cftc(a) for a in ASSETS}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    last = max(d.index[-1] for d in fut.values()).strftime("%Y-%m-%d")
    feeds = []
    for a in ASSETS:
        d = fut[a["id"]]
        feeds.append(dict(symbol=f"{a['root']}.v.0", role=f"{a['name']} {a['ticker']} 价格", last=float(d.close.iloc[-1]), bars=len(d), lastBar=d.index[-1].strftime("%Y-%m-%d"), daily=True, note="Databento GLBX.MDP3 ohlcv-1d（成交量连续合约，未回调）；最新一根可能是盘中未完成", source="databento"))
    for s, v in vix.items():
        feeds.append(dict(symbol=s, role={"^VIX": "美股 IV（VIX）", "^VIX3M": "美股 3M 波动", "^VIX9D": "美股 9 日波动", "^VVIX": "波动率的波动", "^SKEW": "CBOE SKEW", "^OVX": "原油 IV（OVX）", "^GVZ": "黄金 IV（GVZ）", "^EVZ": "欧元 IV（EVZ）"}[s],
                          last=float(v.iloc[-1]) if len(v) else None, bars=len(v), lastBar=v.index[-1].strftime("%Y-%m-%d") if len(v) else None, daily=bool(len(v)), note="CBOE 指数日线（Yahoo）" if len(v) else "无数据", source="yahoo"))
    for k, o in opts.items():
        feeds.append(dict(symbol=o["underlier"], role=f"{k} 挂牌 25Δ RR / GEX", last=o["rr"], bars=o["n"], lastBar=o["asOf"], daily=True, note=f"put25 − call25 = {o['rr']:+.2f} vol · 到期 {o['exp']} · 净 GEX {o['net']:+.2f}M" + (" · 薄链" if o["quality"] == "thin" else ""), source="databento"))
    for k, cf in cftc.items():
        feeds.append(dict(symbol=f"CFTC {next(a['cftc'] for a in ASSETS if a['id'] == k)}", role=f"{k} 仓位", last=cf["groups"][0]["net"] if cf else None, bars=len(cf["series"]) if cf else 0, lastBar=cf["date"] if cf else None, daily=False, note="CFTC 周报（周二仓位、周五公布）" if cf else "无数据", source="cftc"))
    src = ["Databento GLBX.MDP3 期货日线 ES/ZN/6E/6J/GC/HG/CL", "CBOE 指数（Yahoo）VIX/VIX3M/VIX9D/VVIX/SKEW/OVX/GVZ", f"CME 期货期权 25Δ RR / GEX × {len(opts)}（Databento 结算 + OI · Black-76）", "CFTC COT 周报"]
    if not len(vix["^EVZ"]): src.append("EUR Vega 用实现分位（EVZ 无数据）")
    boards = {}
    for h in ("daily", "weekly"):
        rows, sn, ln = build_board(fut, opts, vix, h)
        boards[h] = dict(asOf=last, horizon=h, generatedAt=now, lastBarDate=last, rows=rows, shortNote=sn, longNote=ln, sources=src, feeds=feeds,
                         listedRr=[{k: o[k] for k in ("assetId", "underlier", "exp", "asOf", "rr", "atmIv", "callIv", "putIv", "listed15", "n", "nOi", "quality", "dte")} for o in opts.values()],
                         gex=[{k: v for k, v in o.items() if k not in ("rr", "callIv", "putIv")} for o in opts.values()], optAsOf=max([o["asOf"] for o in opts.values()] or [None]),
                         costs=COSTS)
        (OUT / f"board_{h}.json").write_text(json.dumps(clean(boards[h]), ensure_ascii=False, separators=(",", ":")))
    drows = boards["daily"]["rows"]
    desks = [build_desk(a, fut[a["id"]], opts.get(a["id"]), cftc[a["id"]], next(r for r in drows if r["id"] == a["id"]), drows, vix) for a in ASSETS]
    (OUT / "desk.json").write_text(json.dumps(clean(dict(asOf=last, generatedAt=now, desks=desks, sources=src)), ensure_ascii=False, separators=(",", ":")))
    (OUT / "meta.json").write_text(json.dumps(dict(generatedAt=now, asOf=last, databento_cost_usd=COSTS, total_cost=round(sum(COSTS.values()), 4)), indent=1))
    print("done", last, "total cost $", round(sum(COSTS.values()), 4))

if __name__ == "__main__": main()
