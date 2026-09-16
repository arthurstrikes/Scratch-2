"""
NSE >3% fall screen for 15-Sep-2026, with 20-trading-day average volume/delivery
volume comparison, index and F&O tagging.

Buckets (as specified):
  1. volume < 20d avg                (includes bucket 2)
  2. volume < 70% of 20d avg          (subset of 1)
  3. volume > 20d avg
Same three buckets computed a second time on DELIVERY volume.
"""
import glob, re, csv
from pathlib import Path
from datetime import datetime

NSE_DIR = Path('/tmp/nse')
TARGET_DATE = '15-Sep-2026'
FALL_THRESHOLD = -3.0

def load_day(fp):
    rows = {}
    with open(fp) as f:
        r = csv.reader(f)
        header = [h.strip() for h in next(r)]
        idx = {h: i for i, h in enumerate(header)}
        for row in r:
            if len(row) < len(header):
                continue
            row = [c.strip() for c in row]
            if row[idx['SERIES']] != 'EQ':
                continue
            sym = row[idx['SYMBOL']]
            rows[sym] = dict(
                prev_close=float(row[idx['PREV_CLOSE']]),
                close=float(row[idx['CLOSE_PRICE']]),
                volume=float(row[idx['TTL_TRD_QNTY']]),
                deliv=float(row[idx['DELIV_QTY']]) if row[idx['DELIV_QTY']] not in ('', '-') else 0.0,
            )
    return rows

files = sorted(glob.glob(str(NSE_DIR / 'bhav_*.csv')),
               key=lambda p: datetime.strptime(re.search(r'(\d{8})', p).group(1), '%d%m%Y'))
by_date = {}
for f in files:
    dt = datetime.strptime(re.search(r'(\d{8})', f).group(1), '%d%m%Y')
    by_date[dt] = load_day(f)

dates_sorted = sorted(by_date)
print(f"Loaded {len(dates_sorted)} trading days: {dates_sorted[0].date()} -> {dates_sorted[-1].date()}")
target_dt = max(d for d in dates_sorted if d.strftime('%d-%b-%Y').replace('-0','-') or True)
# find target date row set
target_key = [d for d in dates_sorted if d.strftime('%d%m%Y') == '15092026']
if not target_key:
    print("TARGET DATE NOT LOADED YET"); raise SystemExit(1)
target_dt = target_key[0]
prior_dates = [d for d in dates_sorted if d < target_dt]
print(f"prior trading days available for 20d avg: {len(prior_dates)} (need 20)")

today = by_date[target_dt]
results = []
for sym, d in today.items():
    if d['prev_close'] <= 0:
        continue
    chg = (d['close'] / d['prev_close'] - 1) * 100
    if chg > FALL_THRESHOLD:
        continue
    vols, delivs = [], []
    for pd_ in prior_dates[-20:]:
        r = by_date[pd_].get(sym)
        if r:
            vols.append(r['volume']); delivs.append(r['deliv'])
    if len(vols) < 5:   # too little history to trust an average
        continue
    avgv = sum(vols) / len(vols)
    avgd = sum(delivs) / len(delivs)
    results.append(dict(symbol=sym, chg=round(chg, 2), close=d['close'], prev_close=d['prev_close'],
                        volume=d['volume'], avg20v=round(avgv, 0), n_days_v=len(vols),
                        deliv=d['deliv'], avg20d=round(avgd, 0), n_days_d=len(delivs)))

print(f"\nstocks falling >{abs(FALL_THRESHOLD)}% on {TARGET_DATE}: {len(results)}")
import json
Path('/home/user/Scratch-2/nse_screen/fallers_raw.json').write_text(json.dumps(results, indent=2))
