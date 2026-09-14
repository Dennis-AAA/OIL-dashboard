# WTI 原油指标看板

静态单页看板：近三年 WTI、OVX、已实现波动、QuikStrike CL 结构快照，以及 USO 股权期权原油代理（非 CME CL）。

**在线地址：** https://dennis-aaa.github.io/OIL-dashboard/

直接打开根目录 `index.html`，或通过 GitHub Pages 访问。数据仅供参考，不构成投资建议。

## 页面内容

- 双轴主图：WTI 价格 + 可切换指标（OVX / RV10 / RV20 / IV−RV20 / SMA50 / SMA200 / USO ATM IV / USO 25Δ RR）
- 区间按钮：近 3 月 / 近 1 年 / 近 3 年
- QuikStrike LOV6 快照卡片（2026-09-13 提取 / 2026-09-11 结算）—— CME CL / LO，保持不变
- 已知行权价波动率微笑、已知伽马密度峰值
- USO 股权期权卡片：ATM IV、25Δ RR、Call墙、Put墙（asof 2026-09-11）
- USO 微笑 `#uso-smile` 与伽马 `#uso-gex`（Alpha Vantage `HISTORICAL_OPTIONS`，不是 CME CL）

## 数据文件

| 文件 | 说明 |
| --- | --- |
| `data/series.js` | `window.OIL_DASHBOARD_DATA`，页面直接加载 |
| `data/series_3y.json` | 同一份序列的 JSON |
| `data/quikstrike_snapshot.json` | QuikStrike 快照与已知链（CME CL / LO） |
| `data/uso_options_snapshot.json` | USO 股权期权快照（微笑 / GEX / 墙） |
| `data/uso_options_series.json` | USO ATM IV 与 25Δ RR 约 60 个交易日 |
| `data/indicators.json` | 主图指标与仅快照字段清单 |

时间序列由 Yahoo `CL=F` 日收盘与 CBOE `_OVX` 日收盘计算：

- `RV_n = 100 × √(252 × mean(r², n))`，`r = ln(P_t / P_{t-1})`
- `iv_rv20 = OVX − RV20`
- `ovx_pctile`：OVX 在近 252 个有效收盘中的分位
- `wti_vs_sma50 = 100 × (WTI / SMA50 − 1)`

QuikStrike 数字只使用已知快照，不补全未给出的微笑/密度点。

USO 是上市原油 ETF 的股权期权，用作油价波动代理，**不是** CME CL 期货期权。QuikStrike 区块仍是 CL 侧。`uso_atm_iv` / `uso_rr25` 按交易日左连接到 WTI 序列；墙与微笑只在快照里。

## 每日更新

页面上的 **刷新数据** 会在浏览器里重新拉取 Yahoo `CL=F` 与 CBOE `_OVX`（直连失败时走 Jina CORS 代理），当场重算指标并更新卡片/主图。期权快照不随此按钮更新。

浏览器刷新只作用于当前标签页；重新打开页面仍用仓库里的静态 `data/series.js`。

要把最新序列写进仓库并发布到 Pages：打开
[Refresh market data](https://github.com/Dennis-AAA/OIL-dashboard/actions/workflows/refresh-data.yml)
后点 **Run workflow**（分支选 `master`）。该 workflow 运行 `scripts/build_series.py` 并提交。

工作日 USO 期权由
[Refresh USO options](https://github.com/Dennis-AAA/OIL-dashboard/actions/workflows/refresh-uso-options.yml)
更新（`1-5` 的 cron + 手动 Run workflow）。仓库需配置 secret `ALPHAVANTAGE_API_KEY`；密钥缺失时 workflow **直接跳过**，不改文件。

本地合并 USO 到 `series.js` / `series_3y.json`：

```bash
python3 scripts/merge_uso_into_series.py
```

`scripts/build_series.py` 在重写 WTI/OVX 后会再跑一次合并，以免冲掉 USO 列。

本地重建：

```bash
python3 scripts/build_series.py
```

## GitHub Pages

仓库为公开仓库。`master` 推送后由 `.github/workflows/pages.yml` 部署静态文件；仓库也已配置从 `master` 根目录发布（经典 Pages）。

原供求周报单页仍在 `archive/supply-dashboard.html`，周报 markdown 在 `reports/`。
