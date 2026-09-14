#!/usr/bin/env python3
"""Write and embed the WTI proxy scorecard.

Rules (documented; this snapshot is as-of 2026-09-11 and is not a
third-party proprietary model replica):

  趋势  — WTI vs SMA50 / SMA200. Comfortable long if price is well above both
          SMAs. Pill value = % vs SMA50. Label 多头·舒适 when both slopes
          are supportive.
  季节性 — Calendar-month median return / hit rate over the displayed sample
          (here September, 3 years). Weak signal only; not a forecast.
  波动  — OVX level, OVX percentile, IV−RV20, distance to a 75th-pctile
          leverage line, and RR z. High percentile + inverted IV−RV = 高压·倒挂.
  Gamma — Storm-middle when RR z is elevated and USO/QS walls bracket spot.
          Uses USO call/put walls + dens and QuikStrike walls as structure,
          not CME dealer GEX from a vendor model.
  玩家 / 公允值 / 目标价 / 叙事 — placeholders. Do not invent COT, FV, bank
          targets, or news scores. Leave value null until a real source lands.

方向偏好 × 波动率偏好 (WTI CL only):
  短Δ     near-term return sign (≈20d)
  长Δ     intermediate / structure (≈60d)
  VEGA    sell-vol if IV−RV is rich; buy-vol if cheap
  SKEW    25Δ RR sign (call-rich = 偏多 RR)
  GAMMA   storm if |z| is high
  VOL体制 OVX percentile regime (混沌 when very high)

Fair-value and target pills stay null. USO is an equity-options oil proxy,
not CME CL. QuikStrike remains the CL snapshot.

Usage (repo root):
  python3 scripts/build_wti_scorecard.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCORECARD_PATH = DATA / "wti_scorecard.json"

# Exact committed snapshot. Rebuilds must not invent FV / targets / COT.
SCORECARD = {
    "asof": "2026-09-11",
    "source_note": (
        "Proxy scorecard from WTI/OVX/USO/QuikStrike — "
        "not a copy of third-party proprietary models"
    ),
    "pills": [
        {
            "id": "trend",
            "name": "趋势",
            "label": "多头 · 舒适",
            "tone": "bull",
            "value": 20.2,
            "unit": "%",
            "detail": "强度 0.2 · 现价 100.05 · 相对50日 20.2% · 相对200日 25.7%",
        },
        {
            "id": "season",
            "name": "季节性",
            "label": "偏空",
            "tone": "bear",
            "value": -2.6,
            "unit": "%",
            "detail": "09月中位收益 -2.6% · 正收益概率 33% · 样本 3 年 · 弱信号仅供参考",
        },
        {
            "id": "vol",
            "name": "波动",
            "label": "高压 · 倒挂",
            "tone": "hot",
            "value": 90,
            "unit": "%",
            "detail": "OVX 58.92 · 分位 90.34% · IV−RV 18.5835 · 距75分位杠杆线 -14.0 vol pts · RR z 1.04",
        },
        {
            "id": "gamma",
            "name": "Gamma",
            "label": "风暴中间",
            "tone": "storm",
            "value": 1.04,
            "unit": "z",
            "detail": "USO墙 Call 165.0 / Put 140.0 · dens 77.4/123.7 · ATM IV 58.0715 · RR25 8.78 · QS墙 100/90",
        },
        {
            "id": "players",
            "name": "玩家",
            "label": "待接入",
            "tone": "neutral",
            "value": None,
            "unit": None,
            "detail": "CFTC COT / CTA 下一阶段接入；当前占位",
        },
        {
            "id": "fv",
            "name": "公允值",
            "label": "待建模",
            "tone": "neutral",
            "value": None,
            "unit": None,
            "detail": "需自建库存/宏观回归；不做假数",
        },
        {
            "id": "target",
            "name": "目标价",
            "label": "待接入",
            "tone": "neutral",
            "value": None,
            "unit": None,
            "detail": "投行目标价/叙事下一阶段",
        },
        {
            "id": "narrative",
            "name": "叙事",
            "label": "待接入",
            "tone": "neutral",
            "value": None,
            "unit": None,
            "detail": "新闻情绪可用 Alpha Vantage NEWS_SENTIMENT 后续接",
        },
    ],
    "pref_row": {
        "asset": "WTI CL",
        "short_delta": {"label": "偏多", "score": 1, "hint": "近20日 23.1%"},
        "long_delta": {"label": "偏多 · 结构", "score": 1, "hint": "近60日/结构 31.6%"},
        "vega": {"label": "卖波", "hint": "IV−RV 18.5835"},
        "skew": {"label": "偏多 RR", "hint": "RR25 8.78"},
        "gamma": {"label": "风暴 · 偏多", "hint": "z≈1.04"},
        "vol_regime": {"label": "混沌", "hint": "OVX分位 90.34%"},
    },
    "inputs": {
        "wti": 100.05,
        "sma50": 83.2278,
        "sma200": 79.5861,
        "ovx": 58.92,
        "ovx_pctile": 90.34,
        "iv_rv20": 18.5835,
        "uso_atm_iv": 58.0715,
        "uso_rr25": 8.78,
    },
}


def load_scorecard() -> dict:
    if SCORECARD_PATH.is_file():
        return json.loads(SCORECARD_PATH.read_text(encoding="utf-8"))
    return SCORECARD


def write_scorecard(card: dict) -> None:
    DATA.mkdir(exist_ok=True)
    SCORECARD_PATH.write_text(
        json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def embed(card: dict) -> None:
    series_path = DATA / "series_3y.json"
    if not series_path.is_file():
        print("skip embed: missing data/series_3y.json")
        return
    payload = json.loads(series_path.read_text(encoding="utf-8"))
    payload["wti_scorecard"] = card
    series_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (DATA / "series.js").write_text(
        "window.OIL_DASHBOARD_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"embedded wti_scorecard asof {card.get('asof')} ({len(card.get('pills') or [])} pills)")


def main() -> None:
    card = SCORECARD
    write_scorecard(card)
    embed(card)


if __name__ == "__main__":
    main()
