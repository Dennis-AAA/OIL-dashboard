# WTI 原油指标看板

静态单页看板：近三年 WTI、OVX、已实现波动与 QuikStrike 结构快照。

**在线地址：** https://dennis-aaa.github.io/OIL-dashboard/

直接打开根目录 `index.html`，或通过 GitHub Pages 访问。数据仅供参考，不构成投资建议。

## 页面内容

- 双轴主图：WTI 价格 + 可切换指标（OVX / RV10 / RV20 / IV−RV20 / SMA50 / SMA200）
- 区间按钮：近 3 月 / 近 1 年 / 近 3 年
- QuikStrike LOV6 快照卡片（2026-09-13 提取 / 2026-09-11 结算）
- 已知行权价波动率微笑、已知伽马密度峰值

## 数据文件

| 文件 | 说明 |
| --- | --- |
| `data/series.js` | `window.OIL_DASHBOARD_DATA`，页面直接加载 |
| `data/series_3y.json` | 同一份序列的 JSON |
| `data/quikstrike_snapshot.json` | QuikStrike 快照与已知链 |

时间序列由 Yahoo `CL=F` 日收盘与 CBOE `_OVX` 日收盘计算：

- `RV_n = 100 × √(252 × mean(r², n))`，`r = ln(P_t / P_{t-1})`
- `iv_rv20 = OVX − RV20`
- `ovx_pctile`：OVX 在近 252 个有效收盘中的分位
- `wti_vs_sma50 = 100 × (WTI / SMA50 − 1)`

QuikStrike 数字只使用已知快照，不补全未给出的微笑/密度点。

更新序列：

```bash
python3 scripts/build_series.py
```

## GitHub Pages

仓库为公开仓库。`master` 推送后由 `.github/workflows/pages.yml` 部署静态文件；仓库也已配置从 `master` 根目录发布（经典 Pages）。

原供求周报单页仍在 `archive/supply-dashboard.html`，周报 markdown 在 `reports/`。
