"""
Build the 3 volume-condition lists from fallers_raw.json, tagged with
index membership and F&O eligibility.

Buckets:
  1. volume < 20d avg
  2. volume < 70% of 20d avg  (also emitted separately for delivery volume)
  3. volume > 20d avg
Same three, second time, on DELIVERY volume.
"""
import json, csv
from pathlib import Path

NSE = Path('/tmp/nse')
OUT = Path('/home/user/Scratch-2/nse_screen')

def load_symbols(fp):
    with open(fp) as f:
        r = csv.DictReader(f)
        return {row['Symbol'].strip() for row in r}

idx_files = {
    'Nifty50': NSE / 'idx_nifty50.csv',
    'NiftyNext50': NSE / 'idx_niftynext50.csv',
    'Nifty200': NSE / 'idx_nifty200.csv',
    'Nifty500': NSE / 'idx_nifty500.csv',
    'Midcap150': NSE / 'idx_midcap150.csv',
    'Smallcap250': NSE / 'idx_smallcap250.csv',
}
idx_sets = {name: load_symbols(fp) for name, fp in idx_files.items() if fp.exists()}
print("Index files loaded:", {k: len(v) for k, v in idx_sets.items()})

fno_syms = set()
fno_fp = NSE / 'fo_secban.csv'
if fno_fp.exists():
    with open(fno_fp, encoding='latin-1') as f:
        lines = f.read().splitlines()
    # format: UNDERLYING, SYMBOL, <month columns...> ; skip header row
    for line in lines[1:]:
        parts = [p.strip().strip('"') for p in line.split(',')]
        if len(parts) >= 2 and parts[1] and parts[1].isupper() and parts[1].isalnum():
            fno_syms.add(parts[1])
    print(f"F&O list loaded: {len(fno_syms)} symbols")
else:
    print("F&O list: NOT AVAILABLE (NSE archive throttled this file) - F&O column left blank/Unknown")

def tag_index(sym):
    if sym in idx_sets.get('Nifty50', set()): return 'Nifty50'
    if sym in idx_sets.get('NiftyNext50', set()): return 'NiftyNext50'
    if sym in idx_sets.get('Midcap150', set()): return 'Midcap150'
    if sym in idx_sets.get('Smallcap250', set()): return 'Smallcap250'
    if sym in idx_sets.get('Nifty200', set()): return 'Nifty200(other)'
    if sym in idx_sets.get('Nifty500', set()): return 'Nifty500(other)'
    return 'Outside Nifty500'

data = json.loads((OUT / 'fallers_raw.json').read_text())
for d in data:
    d['index'] = tag_index(d['symbol'])
    d['fno'] = ('Yes' if d['symbol'] in fno_syms else ('Unknown' if not fno_syms else 'No'))

def write_csv(rows, fname, vol_key, avg_key, n_key):
    fields = ['symbol', 'index', 'fno', 'chg', 'close', 'prev_close',
              vol_key, avg_key, 'ratio_pct', n_key]
    rows = sorted(rows, key=lambda r: r['chg'])
    with open(OUT / fname, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            row = {k: r[k] for k in fields if k in r}
            row['ratio_pct'] = round(r[vol_key] / r[avg_key] * 100, 1) if r[avg_key] else None
            w.writerow(row)
    print(f"{fname}: {len(rows)} rows")

# --- Traded volume buckets ---
below_v  = [d for d in data if d['avg20v'] and d['volume'] < d['avg20v']]
below70_v = [d for d in data if d['avg20v'] and d['volume'] < 0.70 * d['avg20v']]
above_v  = [d for d in data if d['avg20v'] and d['volume'] > d['avg20v']]
write_csv(below_v,  'list1_volume_below_20d_avg.csv', 'volume', 'avg20v', 'n_days_v')
write_csv(below70_v,'list2_volume_below_70pct_20d_avg.csv', 'volume', 'avg20v', 'n_days_v')
write_csv(above_v,  'list3_volume_above_20d_avg.csv', 'volume', 'avg20v', 'n_days_v')

# --- Delivery volume buckets ---
below_d  = [d for d in data if d['avg20d'] and d['deliv'] < d['avg20d']]
below70_d = [d for d in data if d['avg20d'] and d['deliv'] < 0.70 * d['avg20d']]
above_d  = [d for d in data if d['avg20d'] and d['deliv'] > d['avg20d']]
write_csv(below_d,  'list1b_delivery_below_20d_avg.csv', 'deliv', 'avg20d', 'n_days_d')
write_csv(below70_d,'list2b_delivery_below_70pct_20d_avg.csv', 'deliv', 'avg20d', 'n_days_d')
write_csv(above_d,  'list3b_delivery_above_20d_avg.csv', 'deliv', 'avg20d', 'n_days_d')

print(f"\nTotal fallers >3%: {len(data)}")
print(f"Index distribution: ", {k: sum(1 for d in data if d['index']==k) for k in set(d['index'] for d in data)})
