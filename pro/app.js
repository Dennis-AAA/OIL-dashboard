"use strict";
const S={h:"daily",t:"board",asset:"ES",board:{},desk:null};
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fx=(v,d=2)=>v==null||!isFinite(v)?"—":Number(v).toFixed(d);
const sg=(v,d=2)=>v==null||!isFinite(v)?"—":(v>0?"+":"")+Number(v).toFixed(d);
function fp(v){if(v==null)return"—";const a=Math.abs(v);return a<0.1?v.toFixed(6):a<10?v.toFixed(4):a<1000?v.toFixed(2):v.toLocaleString("en-US",{maximumFractionDigits:1})}
function toast(m){const t=$("#toast");t.textContent=m;t.classList.remove("hidden");clearTimeout(toast.t);toast.t=setTimeout(()=>t.classList.add("hidden"),2600)}
async function load(force){
  const q=force?"?t="+Date.now():"";
  const get=u=>fetch(u+q).then(r=>{if(!r.ok)throw Error(u);return r.json()});
  const [d,w]=await Promise.all([get("data/board_daily.json"),get("data/board_weekly.json")]);
  S.board={daily:d,weekly:w};snapshot(d);
  get("data/desk.json").then(x=>{S.desk=x;if(S.t==="desk")render()}).catch(()=>{S.desk=false;if(S.t==="desk")render()});
}
function cell(c,score,extra=""){if(!c)return"";const cls=[c.tone,c.faded?"faded":"",c.warn?"warn":""].join(" ");
  return `<span class="cell ${cls}">${esc(c.label)}${c.faded?" →":""}${score!=null?` <span class="sc">${score>0?"+":""}${score}</span>`:""}</span>${extra}`}
function spark(a,w=70,h=20){a=a.filter(x=>x!=null);if(a.length<2)return"";const mn=Math.min(...a),mx=Math.max(...a),r=mx-mn||1;
  const p=a.map((v,i)=>`${(i/(a.length-1)*w).toFixed(1)},${(h-(v-mn)/r*h).toFixed(1)}`).join(" ");const up=a[a.length-1]>=a[0];
  return `<svg class="spark" width="${w}" height="${h}"><polyline fill="none" stroke="${up?"#127a4b":"#b42d2d"}" stroke-width="1.3" points="${p}"/></svg>`}
function board(){const B=S.board[S.h];if(!B)return"";const wk=S.h==="weekly";
  const hd=`<tr><th>大类</th><th>短线<small>${wk?"DELTA · 1–4 周  周度 · FM · Gamma":"DELTA · 1–4 周  Flash · FM · Gamma"}</small></th><th>长线<small>${wk?"DELTA · 季内  Confirmed · RM · FV":"DELTA · 1–3 月  Confirmed · RM · FV"}</small></th><th>VEGA<small>IV 分位 · VRP</small></th><th>SKEW<small>RR · 尾部分位</small></th><th>GAMMA<small>短窗 RV / 收 theta</small></th><th>VOL体制<small>分位 · 期限结构</small></th></tr>`;
  const rows=B.rows.map(r=>`<tr class="row" data-id="${r.id}"><td><b>${esc(r.name)}</b> <span class="mono muted">${r.ticker}</span>${r.diverge?'<span class="ne" title="短线与长线不一致">≠</span>':""}<br><span class="num">${fp(r.price)}</span> <span class="num ${r.changePct>=0?"pos":"negc"}">${sg(r.changePct)}%</span> ${spark(r.spark)}<br><span class="heat">热 ${fx(r.heat,1)}</span></td>
   <td title="${esc(r.short.note)}">${cell(r.short,r.short.score)}</td><td title="${esc(r.long.note)}">${cell(r.long,r.long.score)}</td>
   <td title="${esc(r.vega.note)}">${cell(r.vega)}</td><td title="${esc(r.skew.note)}">${cell(r.skew)}</td><td title="${esc(r.gamma.note)}">${cell(r.gamma)}</td><td title="${esc(r.regime.note)}">${cell(r.regime)}</td></tr>`).join("");
  return `<div class="card" style="overflow-x:auto"><table>${hd}${rows}</table></div><div class="notes card"><p>${esc(B.shortNote)}</p><p>${esc(B.longNote)}</p></div>`}
function drawer(id){const B=S.board[S.h];const r=B.rows.find(x=>x.id===id);if(!r)return;const m=r.metrics;
  const kv=[["1 日",sg(m.ret1)+"%"],["短窗",sg(m.ret5)+"%"],["20 日",sg(m.ret20)+"%"],["60 日",sg(m.ret60)+"%"],["距均线",sg(m.distMaAtr)+" ATR"],["RSI",fx(m.rsi,0)],["IV 指数",fx(m.iv,1)],["IV 分位",m.ivPct==null?"—":fx(m.ivPct,0)+"%"],["RV5 / RV20 / RV60",`${fx(m.rv5,1)} / ${fx(m.rv20,1)} / ${fx(m.rv60,1)}`],["RV 分位",fx(m.rvPct,0)+"%"],["VRP",sg(m.vrp,1)],["期限 VIX/VIX3M",fx(m.term,2)],["CBOE SKEW",fx(m.skewIdx,1)],["实现 RR",sg(m.realizedRr,1)],["挂牌 25Δ RR",sg(m.listedRr)],["挂牌 ATM",fx(m.listedAtmIv,1)]];
  $("#dbody").innerHTML=`<h3>${esc(r.name)} · ${esc(r.quoteLabel)}</h3><p class="num">${fp(r.price)} <span class="${r.changePct>=0?"pos":"negc"}">${sg(r.change1d,4)} (${sg(r.changePct)}%)</span></p>
  <p class="muted">${esc(r.desc)}</p>${["short","long","vega","skew","gamma","regime"].map(k=>`<p><b>${{short:"短线",long:"长线",vega:"VEGA",skew:"SKEW",gamma:"GAMMA",regime:"体制"}[k]}</b> ${cell(r[k],r[k].score)}<br><span class="muted">${esc(r[k].note)}</span></p>`).join("")}
  <div class="kv">${kv.map(([a,b])=>`<span>${a}</span><span class="num">${b}</span>`).join("")}</div>
  ${m.listedRr==null?'<p class="muted">该品种没有可用的挂牌 25Δ，Skew 只用实现半波动。</p>':`<p class="muted">${esc(m.listedRrNote)} · 截面 ${m.listedRrAsOf}</p>`}
  <p class="heat">综合热度 ${fx(r.heat,1)} · 由 |短Δ| + |长Δ| + Vega/Skew/Gamma/体制强度加权</p>`;$("#drawer").classList.remove("hidden")}
// ---- charts
function lineChart(pts,series,{h=220,bars=null,zero=false}={}){const W=720,H=h,L=46,Rr=8,T=8,Bm=20;
  const xs=i=>L+(i/(pts.length-1))*(W-L-Rr);let vals=[];series.forEach(s=>pts.forEach(p=>{const v=p[s.k];if(v!=null)vals.push(v)}));
  if(bars)pts.forEach(p=>{if(p[bars.k]!=null)vals.push(p[bars.k])});if(zero)vals.push(0);if(!vals.length)return"";
  let mn=Math.min(...vals),mx=Math.max(...vals);const pad=(mx-mn)*.05||1;mn-=pad;mx+=pad;const ys=v=>T+(1-(v-mn)/(mx-mn))*(H-T-Bm);
  let g="";for(let i=0;i<=4;i++){const v=mn+(mx-mn)*i/4;g+=`<line x1="${L}" x2="${W-Rr}" y1="${ys(v)}" y2="${ys(v)}" stroke="#eceef2"/><text x="2" y="${ys(v)+3}">${fp(v)}</text>`}
  [0,.25,.5,.75,1].forEach(f=>{const i=Math.round(f*(pts.length-1));g+=`<text x="${xs(i)-26}" y="${H-4}">${pts[i].date}</text>`});
  if(bars){const bw=Math.max(1,(W-L-Rr)/pts.length*.8);pts.forEach((p,i)=>{const v=p[bars.k];if(v==null)return;g+=`<rect x="${xs(i)-bw/2}" y="${Math.min(ys(v),ys(0))}" width="${bw}" height="${Math.abs(ys(v)-ys(0))}" fill="${v>=0?bars.c:bars.c2}" opacity=".55"/>`})}
  series.forEach(s=>{let d="";pts.forEach((p,i)=>{const v=p[s.k];if(v==null)return;d+=(d?"L":"M")+xs(i).toFixed(1)+","+ys(v).toFixed(1)});g+=`<path d="${d}" fill="none" stroke="${s.c}" stroke-width="${s.w||1.4}" ${s.dash?'stroke-dasharray="4 3"':""}/>`});
  const lg=series.map(s=>`<span style="color:${s.c}">━ ${s.n}</span>`).join(" ")+(bars?` <span style="color:${bars.c}">▮ ${bars.n}</span>`:"");
  return `<div class="heat">${lg}</div><svg viewBox="0 0 ${W} ${H}" width="100%">${g}</svg>`}
function gexChart(g){const b=g.bars;if(!b||!b.length)return"";const W=720,H=240,L=50,T=10,Bm=22;const ks=b.map(x=>x.k);
  const vals=b.flatMap(x=>[x.c,x.p,x.n,0]);const mn=Math.min(...vals),mx=Math.max(...vals);const ys=v=>T+(1-(v-mn)/(mx-mn||1))*(H-T-Bm);
  const k0=Math.min(...ks,g.spot),k1=Math.max(...ks,g.spot);const xs=k=>L+(k-k0)/(k1-k0||1)*(W-L-10);const bw=Math.max(2,(W-L)/b.length*.35);
  let s=`<line x1="${L}" x2="${W}" y1="${ys(0)}" y2="${ys(0)}" stroke="#ccd"/>`;
  b.forEach(x=>{s+=`<rect x="${xs(x.k)-bw}" y="${ys(Math.max(0,x.c))}" width="${bw}" height="${Math.abs(ys(x.c)-ys(0))}" fill="#127a4b" opacity=".7"/><rect x="${xs(x.k)}" y="${ys(0)}" width="${bw}" height="${Math.abs(ys(x.p)-ys(0))}" fill="#b42d2d" opacity=".7"/>`});
  s+=`<path d="${b.map((x,i)=>(i?"L":"M")+xs(x.k)+","+ys(x.n)).join("")}" fill="none" stroke="#243044" stroke-width="1.5"/>`;
  const vl=(k,c,t)=>k==null?"":`<line x1="${xs(k)}" x2="${xs(k)}" y1="${T}" y2="${H-Bm}" stroke="${c}" stroke-dasharray="4 3"/><text x="${xs(k)+3}" y="${T+10}" style="fill:${c}">${t} ${fp(k)}</text>`;
  s+=vl(g.putWall,"#b42d2d","Put墙")+vl(g.callWall,"#127a4b","Call墙")+vl(g.spot,"#243044","现价")+(g.flip!=null?vl(g.flip,"#a66b00","Flip"):"");
  [0,.5,1].forEach(f=>{const k=k0+(k1-k0)*f;s+=`<text x="${xs(k)-14}" y="${H-5}">${fp(k)}</text>`});
  for(let i=0;i<=3;i++){const v=mn+(mx-mn)*i/3;s+=`<text x="2" y="${ys(v)+3}">${fx(v,1)}M</text>`}
  return `<svg viewBox="0 0 ${W} ${H}" width="100%">${s}</svg><p class="heat">绿柱 Call GEX · 红柱 Put GEX · 折线净暴露。刻度是期货行权价（CME 期货期权，墙即期货点）。</p>`}
function desk(){if(S.desk===null)return'<p class="muted">结构页加载中…</p>';if(S.desk===false)return'<p class="muted">结构页暂时拉不到数据。稍后刷新。</p>';
  const D=S.desk.desks.find(d=>d.id===S.asset)||S.desk.desks[0];const g=D.gamma,x=D.gex;
  const sel=`<div class="assets">${S.desk.desks.map(d=>`<button data-a="${d.id}" class="${d.id===D.id?"on":""}">${esc(d.name)} ${d.ticker}</button>`).join("")}</div>`;
  const chips=`<div class="chips">${D.chips.map(c=>`<div class="chip ${c.tone}"><div class="k">${esc(c.kicker)}</div><div class="h">${esc(c.headline)}</div><div class="d">${esc(c.detail)}</div></div>`).join("")}</div>`;
  const pts=D.chart;
  const px=lineChart(pts,[{k:"px",n:"现价",c:"#243044"},{k:"dn",n:"翻转价 200d",c:"#a66b00",dash:1},{k:"gUp",n:"带上",c:"#9fb3c8",w:1},{k:"gDown",n:"带下",c:"#9fb3c8",w:1}]);
  const gs=lineChart(pts,[{k:"volRr",n:"Vol(15C−15P) 60d 实现",c:"#2c6db5"}],{bars:{k:"gSkew",n:"Gamma-Skew 20d 实现",c:"#b42d2d",c2:"#b42d2d"},zero:1,h:180});
  const im=lineChart(pts,[{k:"impulse",n:"Impulse RV5/RV20−1",c:"#a66b00"},{k:"volAtm",n:"RV20",c:"#2c6db5"}],{zero:1,h:150});
  const da=lineChart(pts,[{k:"deltaAdj",n:"Delta调整后（现价−200d）",c:"#127a4b"}],{zero:1,h:150});
  const gcard=`<div class="card"><h3>Gamma-Skew</h3><div class="kv"><span>z 值（约 1 年）</span><span class="num">${sg(g.z)}</span><span>|G-S| 分位</span><span class="num">P${fx(g.absPctl,0)}</span><span>翼</span><span>偏 ${g.side} Gamma</span><span>体制</span><span>${esc(g.regime)}</span><span>Impulse</span><span class="num">${sg(g.impulse)}</span><span>挂牌 15C−15P</span><span class="num">${g.listed15==null?"无链":sg(g.listed15)}${g.listedAsOf?" · 期权 "+g.listedAsOf.slice(5):""}</span><span>实现 20d</span><span class="num">${sg(g.realized20)}</span><span>实现 60d</span><span class="num">${sg(g.realized60)}</span><span>混合</span><span class="num">${sg(g.mix)}</span></div><p class="muted">${esc(g.playbook)}</p><p class="heat">${esc(g.read)}</p></div>`;
  const xcard=x?`<div class="card"><h3>GEX · ${esc(x.underlier)} · 到期 ${x.exp}${x.quality==="thin"?" · 薄链":""}</h3><p class="heat">挂牌 OI×Γ · 不是 dealer 库存 · 截面 ${x.asOf}</p>
   <div class="kv"><span>净 GEX / 1%</span><span class="num">${sg(x.net)}M</span><span>Call墙</span><span class="num">${fp(x.callWall)}</span><span>Put墙</span><span class="num">${fp(x.putWall)}</span><span>Gamma Flip</span><span class="num">${x.flip==null?"无交叉":fp(x.flip)}</span><span>现价</span><span class="num">${fp(x.spot)}</span><span>夹持带</span><span class="num">${fp(x.pinLo)}–${fp(x.pinHi)} · ${x.inPin?"带内":"带外"}</span><span>Flip 下净 / 上净</span><span class="num">${sg(x.gexBelow,1)}M / ${sg(x.gexAbove,1)}M</span><span>距 Flip</span><span class="num">${x.flipDistFx==null?"—":sg(x.flipDistFx,4)}</span></div>
   ${gexChart(x)}<p class="muted">${esc(x.playbook)}</p><p class="muted"><b>${esc(x.flipRegime)}</b> · ${esc(x.flipPlaybook)}</p><p class="heat">${esc(x.read)}</p><p class="heat">${esc(x.flipRead)}</p><p class="heat">${esc(x.squeezeRead)}</p></div>`:`<div class="card"><h3>GEX</h3><p class="muted">这一品种还没有挂牌 OI×Γ 截面。</p></div>`;
  const cf=D.cftc;const pc=cf?lineChart(cf.series,[{k:"net",n:cf.main+" 净头寸（CFTC 周报）",c:"#243044"}],{zero:1,h:150}):"";
  return sel+`<div class="card"><h3>${esc(D.name)} · ${esc(D.quoteLabel)} <span class="num">${fp(D.price)}</span> <span class="heat">截至 ${D.asOf}</span></h3>${chips}</div>
  <div class="grid2"><div class="card"><h3>价格 · 翻转价</h3>${px}</div><div class="card"><h3>Gamma-Skew / Vol(15C−15P)</h3>${gs}</div><div class="card"><h3>Impulse · 实现波动</h3>${im}</div><div class="card"><h3>Delta调整后市场价格</h3>${da}</div></div>
  <div class="grid2">${gcard}${xcard}</div><div class="card"><dl class="rows">${D.rows.map(r=>`<dt>${esc(r.title)}</dt><dd>${esc(r.body)}</dd>`).join("")}</dl>${pc?"<h3 style='margin-top:12px'>玩家</h3>"+pc:""}</div>
  <div class="card heat">${D.footnotes.map(esc).join("<br>")}</div>`}
function data(){const B=S.board.daily;if(!B)return'<p class="muted">先拉取看板后再看数据覆盖。</p>';
  const map=[["短线 / 长线 Delta","七个期货的日收盘、ATR、均线、RSI。Databento GLBX.MDP3 ohlcv-1d 成交量连续合约（.v.0）。"],["Vega","美股 VIX、黄金 GVZ、原油 OVX、欧元 EVZ（CBOE 指数，Yahoo 日线）。美债 / 日元 / 铜没有波动率指数，用自身已实现分位。"],["Skew","美股：CBOE SKEW + ES 期货期权 25Δ RR。其余：CME 期货期权挂牌 25Δ（Databento 结算价 → Black-76 IV）+ 实现 RR。"],["结构页","趋势 / 季节性 / 公允值用 Databento 10 年期货日线；玩家用 CFTC 周报；Gamma 曲线用实现半波动代理，挂牌 15Δ 只标最新点。GEX / Gamma Flip 用同一条 CME 期货期权链的 OI×Γ。"]];
  const t=(h,rows)=>`<div class="card" style="overflow-x:auto"><table><tr>${h.map(x=>`<th>${x}</th>`).join("")}</tr>${rows.join("")}</table></div>`;
  return t(["列","→ 数据来源"],map.map(([a,b])=>`<tr><td><b>${a}</b></td><td class="muted">${b}</td></tr>`))+
  t(["代码","用途","来源","日线根数","最新日","状态","说明"],B.feeds.map(f=>`<tr><td class="mono">${esc(f.symbol)}</td><td>${esc(f.role)}</td><td>${f.source}</td><td class="num">${f.bars}</td><td class="num">${f.lastBar||"—"}</td><td>${f.daily?"日线可用":(f.source==="cftc"&&f.bars?"周报":"无数据")}</td><td class="muted">${esc(f.note)}</td></tr>`))+
  `<h3>挂牌 25Δ 风险逆转</h3><p class="heat">正数 = put IV 高于 call IV = 偏空 RR。CME 期货期权，单到期。</p>`+t(["品种","标的","到期","截面","RR","ATM","25C / 25P","15C−15P","n"],B.listedRr.map(o=>`<tr><td>${o.assetId}</td><td>${esc(o.underlier)}</td><td class="num">${o.exp} (${o.dte}d)</td><td class="num">${o.asOf}</td><td class="num">${sg(o.rr)}</td><td class="num">${fx(o.atmIv,1)}</td><td class="num">${fx(o.callIv,1)} / ${fx(o.putIv,1)}</td><td class="num">${sg(o.listed15)}</td><td class="num">${o.n}${o.quality==="thin"?" · 稀":""}</td></tr>`))+
  `<h3>挂牌 Gamma Exposure</h3><p class="heat">OI × Γ × 合约乘数 × F² × 1%，百万美元。Call 为正、Put 为负。相对 Flip = 期货价相对累计净 Γ 翻转点的距离。不是 dealer 库存。</p>`+t(["品种","净 / 1%","Call 墙","Put 墙","Flip","相对 Flip","OI C/P"],B.gex.map(o=>`<tr><td>${o.assetId}</td><td class="num">${sg(o.net)}M</td><td class="num">${fp(o.callWall)}</td><td class="num">${fp(o.putWall)}</td><td class="num">${o.flip==null?"无交叉":fp(o.flip)}</td><td class="num">${o.flip==null?"—":sg((o.spot/o.flip-1)*100)+"%"}</td><td class="num">${o.oiCall.toLocaleString()} / ${o.oiPut.toLocaleString()}${o.quality==="thin"?" · 薄":""}</td></tr>`))+
  `<div class="card"><h3>日度能不能更新</h3><p class="muted">期货日线来自 Databento（随 CME 交易日更新）。CBOE 指数来自 Yahoo 日线。挂牌 25Δ RR 与 GEX 都是上一交易日 CME 结算价 + OI 截面，不是盘中实时。仓位来自 CFTC 周报。静态页由 scripts/build_pro.py 生成，价格最新 ${B.lastBarDate} · 期权截面 ${B.optAsOf} · 生成 ${new Date(B.generatedAt).toLocaleString("zh-CN",{timeZone:"Asia/Shanghai"})} (UTC+8) · Databento 本轮费用 $${Object.values(B.costs||{}).reduce((a,b)=>a+b,0).toFixed(2)}</p></div>`}
const METHOD=[["这张表在看什么","「方向偏好 × 波动率偏好」矩阵：左侧两列是 delta（短线 1–4 周、长线 1–3 月），右侧四列是波动率的拆解（Vega / Skew / Gamma / 体制）。行底热度 = |短Δ| + |长Δ| + 四个波动率因子的强度。短≠长会打 ≠。美债用 ZN 价格而非收益率；外汇用 EUR、JPY 期货；铜用 COMEX HG。"],
["短线 DELTA","窗口约 1–4 周（日度用 5/10/20 日，周度用 2/3/4 周）。收益换成 ATR 单位（ret_k / (ATR% × √k)），raw = 0.45 × 动量均值 + 0.35 × 距 20 日均线 ATR/1.5 + 0.20 × (RSI−50)/15。Flash = 最近 1–3 根相对 ATR 的脉冲 > 1.2；若脉冲大但分数为 0，格子显示 中性→（虚线框）。|raw| < 0.35 → 0，< 1.0 → ±1，否则 ±2。"],
["长线 DELTA","窗口 60/90 日（周度 8/13 周）动量 + 100 日（周度 20 周）均线 20 根斜率 + 价格在长均线上下。与短线同号标「确认」，否则「结构观察」（暂定结构、非正式配置）。JPY 上涨 = 日元升值，故「多JPY」= 做多日元期货。"],
["VEGA（买波 / 卖波）","有上市波动率指数就用其一年分位：美股 VIX、黄金 GVZ、原油 OVX、欧元 EVZ。美债、日元、铜（及缺 EVZ 时的欧元）用自身 20 日已实现波动的一年分位。分位 <10 且 RV5>RV20 → 强买波；<25 且抬头 → 买波；>75 且回落 → 卖波；>90 → 强卖波。挂牌 ATM IV（Databento 期货期权）只在抽屉对照，不改打分。"],
["SKEW（风险逆转）","正数 = 看跌尾溢价 = 偏空 RR。美股：0.45 × (SKEW−140)/12 + 0.40 × ES 期货期权 25Δ RR/3 + 0.15 × 实现 RR/6。其余：0.85 × 挂牌 25Δ RR/3 + 0.15 × 实现 RR/6（实现 RR = 20 日下行半波动 − 上行半波动）。|mix| ≥ 0.55 才打偏空/偏多。挂牌与实现方向打架时格子打警告。挂牌链是上一交易日 CME 结算截面。"],
["GAMMA","比较 RV5 与 RV20 及 5 日位移（σ 单位）。RV5/RV20 < 0.85 且位移 < 1σ → 平静·收 theta；> 1.15 → 初起；> 1.6 或位移 > 2σ → 风暴（带方向）。"],
["Gamma-Skew（结构页）","约定正值 = 15Δ Call 比 15Δ Put 更贵 = 偏 Call Gamma。挂牌用 call15 IV − put15 IV（Databento 期货期权）。最新读数 85% 挂牌 + 15% 20 日实现翼差（上行半波动 − 下行半波动），再对过去一年实现翼差做 z。历史曲线没有逐日期权：红柱 = 20 日实现翼差，蓝线 = 60 日同口径。Impulse = RV5/RV20 − 1。"],
["GEX","OI × Γ × 合约乘数 × F² × 1%，单位百万美元/涨跌 1%。Call 为正、Put 为负。Call 墙 = Call GEX 最大行权价，Put 墙 = Put GEX 最负行权价。原版用 ETF 期权（SPY/TLT/FXY/GLD/CPER/USO）再映射到期货；本版直接用 CME 期货期权（ES/OZN/EUU/JPU/OG/HXE/LO），墙就是期货点，欧元也有链。单到期（首个 >5 天到期；ES 为季月），不是全期限加总，也不是 dealer 多空。"],
["Gamma Flip","行权价由低到高累计净 GEX 由负转正的点（离现价最近）。现价在 Flip 下 = 本地 Put Γ 主导；在 Flip 上 = Call Γ 主导。夹持带 = Put 墙到 Call 墙。这不是趋势页的「翻转价」（200 日均线）。只给当日截面。"],
["Gamma squeeze","客买大量 call → 做市商短 gamma → 上涨时必须追买标的 → 再推价。短到期、ATM 附近 Γ 最大。结构页只有 OI×Γ 截面，不知道 dealer 多空，所以只判断「形不形似」，没有 squeeze 分数。"],
["VOL 体制","IV/RV 一年分位、VIX/VIX3M 期限结构、VVIX 共同判定：平静（分位 < 40）、混乱（分位 > 80 或 VVIX > 110 或期限倒挂）、高Vol缓和（分位仍高但 RV5/RV20 < 0.9）、其余中性。"],
["结构页","趋势 / 季节性 / 波动 / Gamma / GEX / Γ翻转 / 玩家 / 公允值 / 目标价 / 叙事。翻转价 = 200 日均线；公允值 = 100 日均线（±8% 外为偏贵/偏便宜）。季节性用过去 8 个同月收益中位数与胜率。玩家来自 CFTC 周报：商品分项（管理资金 / 生产套保 / 掉期）与金融 TFF（杠杆基金 / 长期机构 / 做市商），主类净头寸 3 年分位。券商 12M 目标价没有公开日更源，只给技术位。叙事用隔夜横截面。"],
["日度 / 周度如何更新","scripts/build_pro.py 每次运行：Databento 期货日线 + 期货期权定义/统计（结算价、OI），Yahoo CBOE 指数，CFTC Socrata。周度把日线收成周五周线再套矩阵公式。原版的「复盘日期」与 LLM「纪要」需要服务器，本静态版不提供。"]];
function method(){return `<div class="card method">${METHOD.map(([a,b])=>`<h4>${a}</h4><p>${b}</p>`).join("")}</div>`}
const KEY="volbias.snapshots.v1";
function snapshot(B){try{const a=JSON.parse(localStorage.getItem(KEY)||"[]");const heat=Math.round(B.rows.reduce((s,r)=>s+r.heat,0)/B.rows.length*10)/10;
  const k=B.asOf+"|"+B.horizon;const n=a.filter(x=>x.k!==k);n.unshift({k,date:B.asOf,h:B.horizon,heat,at:new Date().toISOString(),rows:B.rows.map(r=>({id:r.id,s:r.short.score,l:r.long.score,v:r.vega.label,sk:r.skew.label,g:r.gamma.label,re:r.regime.label}))});
  localStorage.setItem(KEY,JSON.stringify(n.slice(0,90)))}catch(e){}}
function archive(){let a=[];try{a=JSON.parse(localStorage.getItem(KEY)||"[]")}catch(e){}
  if(!a.length)return'<p class="muted">还没有存档。刷新看板后会按交易日自动留下快照。</p>';
  return `<div class="card"><table><tr><th>日期</th><th>频率</th><th>热度</th><th>写入</th><th class="hide-sm">短/长</th></tr>${a.map(x=>`<tr><td class="num">${x.date}</td><td>${x.h==="daily"?"日度":"周度"}</td><td class="num">${x.heat}</td><td class="num">${new Date(x.at).toLocaleString("zh-CN",{timeZone:"Asia/Shanghai"})}</td><td class="hide-sm mono">${x.rows.map(r=>`${r.id} ${r.s>0?"+":""}${r.s}/${r.l>0?"+":""}${r.l}`).join(" · ")}</td></tr>`).join("")}</table></div>`}
function render(){const v=$("#view");v.innerHTML={board,desk,data,method,archive}[S.t]();const B=S.board[S.h];
  if(B)$("#foot").textContent=`数据截至 ${B.asOf} · 最新 · ${S.h==="daily"?"日度":"周度"} · ${B.sources.join(" · ")}`}
document.addEventListener("click",e=>{const t=e.target.closest("button,tr.row");if(!t)return;
  if(t.dataset.h){S.h=t.dataset.h;document.querySelectorAll("#hz button").forEach(b=>b.classList.toggle("on",b===t));render()}
  else if(t.dataset.t){S.t=t.dataset.t;document.querySelectorAll("#tabs button").forEach(b=>b.classList.toggle("on",b===t));render()}
  else if(t.dataset.a){S.asset=t.dataset.a;render()}
  else if(t.matches("tr.row")){drawer(t.dataset.id)}
  else if(t.id==="dclose"){$("#drawer").classList.add("hidden")}
  else if(t.id==="refresh"){load(true).then(()=>{render();toast("已按最新生成的数据重算")}).catch(()=>toast("行情源暂时不可用，显示上次存档"))}
  else if(t.id==="memo"){toast("纪要需要服务器端生成，本静态版不可用")}});
$("#drawer").addEventListener("click",e=>{if(e.target.id==="drawer")$("#drawer").classList.add("hidden")});
load().then(render).catch(()=>{$("#view").innerHTML='<p class="muted">行情源暂时连不上。稍后再刷新，或打开「存档」查看上次计算结果。</p>'});
