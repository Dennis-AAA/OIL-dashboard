#!/usr/bin/env python3
"""Merge USO options series into series_3y.json and rebuild series.js. Run from repo root."""
import json
from pathlib import Path
root = Path('data')
s3 = json.loads((root/'series_3y.json').read_text())
uso_ser = json.loads((root/'uso_options_series.json').read_text())
snap = json.loads((root/'uso_options_snapshot.json').read_text())
rows = uso_ser['series'] if isinstance(uso_ser, dict) else uso_ser
by_date = {r['date']: r for r in rows}
for row in s3['series']:
    u = by_date.get(row['date'])
    if u:
        row['uso_atm_iv'] = u.get('uso_atm_iv')
        row['uso_rr25'] = u.get('uso_rr25')
    else:
        row.setdefault('uso_atm_iv', None)
        row.setdefault('uso_rr25', None)
ls = s3.setdefault('latest_snapshot', {})
ls['uso_options'] = {
    'asof': snap.get('asof'),
    'spot': snap.get('spot'),
    'expiry': snap.get('expiry'),
    'dte': snap.get('dte'),
    'monthly_expiry': (snap.get('monthly') or {}).get('expiry'),
    'atm_iv': snap.get('atm_iv'),
    'rr25': snap.get('rr25'),
    'call_wall': snap.get('call_wall'),
    'put_wall': snap.get('put_wall'),
    'call_oi': snap.get('call_oi'),
    'put_oi': snap.get('put_oi'),
    'put_call_oi_ratio': snap.get('put_call_oi_ratio'),
    'atm_gamma': snap.get('atm_gamma'),
    'atm_vega': snap.get('atm_vega'),
    'atm_theta': snap.get('atm_theta'),
    'source': 'AlphaVantage HISTORICAL_OPTIONS',
}
s3['uso_options'] = snap
notes = s3.get('notes') or ''
extra = ' USO equity options (Alpha Vantage HISTORICAL_OPTIONS) are an oil-price proxy — not CME CL futures options; QuikStrike remains the CL side.'
if 'USO equity options' not in notes:
    s3['notes'] = (notes + extra).strip()
sc_path = root / 'wti_scorecard.json'
if sc_path.is_file():
    s3['wti_scorecard'] = json.loads(sc_path.read_text())
mx_path = root / 'multi_pref_matrix.json'
if mx_path.is_file():
    s3['multi_pref_matrix'] = json.loads(mx_path.read_text())
(root/'series_3y.json').write_text(json.dumps(s3, ensure_ascii=False, indent=2) + '\n')
(root/'series.js').write_text('window.OIL_DASHBOARD_DATA = ' + json.dumps(s3, ensure_ascii=False) + ';\n')
print('merged', sum(1 for r in s3['series'] if r.get('uso_atm_iv') is not None), 'uso points')
