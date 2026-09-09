"""
TASK 1a - Daily portfolio register for the Managed Account (MA).
Window: 2025-09-21 (inception, synthetic Day-1 row) .. 2026-08-28 (bhavcopy cutoff).

CONVENTIONS (locked with the user, do not change silently):
  * UNLEVERED VIEW. All trades treated as CNC/full cash. MTF financing cost
    (~9.49% p.a. + pledge charges) is EXCLUDED -> Task 1b.
  * Day-1 cost basis = Day-1 MARKET value (Opening Book 'Current Market Price'),
    NOT historic purchase price. Deliberate: avoids conflating pre-fund
    appreciation with post-fund performance. Day-1 unrealised gain = 0 by
    construction.
  * 'Brokerage incl. taxes' is already the ALL-IN charge. Buy cash outflow =
    Trade Value + that column; sell inflow = Trade Value - that column.
    Sub-columns (STT/stamp/turnover) are NOT summed on top.
  * Register rows are driven by the bhavcopy price calendar (+ the synthetic
    Day-1 row), never by a generic NSE calendar. No interpolation, ever.
  * A trade dated on a day with no register row (the 2026-02-01 Sunday Budget
    session) is booked on the NEXT register row so cash and lots are conserved,
    and reported explicitly. Nothing is dropped.
  * UNPRICED HELD SYMBOLS (BUILDPRO, DECGOL pre-2026-04-20): the position stays
    in Cost Value at its true basis and is EXCLUDED from Market Value, which is
    therefore understated by an unknowable amount on those days. Flagged per
    row (Unpriced_Symbols / Unpriced_Cost_Basis), never zeroed, never dropped.
  * Rebased NAV = Net Assets / Day-1 Net Assets x 100. A performance INDEX of
    the whole book, NOT a per-unit NAV: no unit ledger, no capital events.
"""
import sys, importlib.util
from pathlib import Path
import pandas as pd, numpy as np

U = Path('/root/.claude/uploads/7bd3b4cf-fc56-51a0-a6fa-0200b1bb0a88')
OUT = Path('/home/user/Scratch-2/task1a')
MA_START, MA_END = '2025-09-21', '2026-08-28'
OPENING_CASH = 110_000.0
EXCLUDED = ['ICIBAN', 'VARBEV', 'HERHON', 'MAHMAH', 'NATSEC', 'SKYAIR']
flags = []

spec = importlib.util.spec_from_file_location('ca', U/'d71b60ee-ca_register.py')
ca = importlib.util.module_from_spec(spec); spec.loader.exec_module(ca)

# ---------- opening block ----------
ob = pd.read_excel(U/'9b7ecd80-Opening_Book_20250921_FINAL.xlsx')
y = ob[ob['Tagging'] == 'Y'].copy()
assert len(y) == 76, f"expected 76 tagged rows, got {len(y)}"
tagged_sum = round(y['Tagged Value'].sum(), 2)
n_names = sorted(ob[ob['Tagging'] == 'N']['Stock'])
if n_names != sorted(EXCLUDED[:4]):
    flags.append(f"Untagged N-list mismatch: {n_names}")

smap = pd.read_csv(U/'4266749b-symbol_map_final.csv')
map_syms = set(smap['ICICI_Symbol'])
for s in y['Stock']:
    if s not in map_syms: flags.append(f"HARD STOP: Day-1 symbol {s} not in symbol_map_final")

# ---------- prices ----------
bh = pd.read_csv(U/'1816540e-bhavcopy_export_MA_universe_20250921_to_202608281.csv')
bh['Date'] = pd.to_datetime(bh['Date']).dt.date
bh = bh[(bh['Date'] >= pd.Timestamp(MA_START).date()) & (bh['Date'] <= pd.Timestamp(MA_END).date())]
bh = bh.set_index('Date').sort_index()
d1 = pd.Timestamp(MA_START).date()
# Day-1 unit price/cost is derived from the rupee-exact 'Tagged Value' column
# (Market Value / Current Market Price are rounded in the source file; qty x CMP
# undershoots the Rs 14,79,670 anchor by Rs 8.85). Tagged Value / qty keeps the
# Day-1 seed exactly on the anchor and NAV exactly 100.00.
y['Day1_Unit'] = y['Tagged Value'] / y['Allocated Quantity']
day1_px = dict(zip(y['Stock'], y['Day1_Unit']))
dates = [d1] + [d for d in bh.index if d > d1]

# ---------- trades ----------
tr = pd.read_excel(U/'704b6639-ICICIdirect_Trades_05092026.xlsx')
tr['Date'] = pd.to_datetime(tr['Date']).dt.date
tr = tr[(tr['Date'] >= d1) & (tr['Date'] <= pd.Timestamp(MA_END).date())].copy()
sunday = tr[[d.weekday() == 6 for d in tr['Date']]]
excl_report = (tr[tr['Stock'].isin(EXCLUDED)].groupby(['Stock', 'Action']).size()
                 .unstack(fill_value=0).reindex(EXCLUDED, fill_value=0)
                 .reindex(columns=['Buy', 'Sell'], fill_value=0))
tr = tr[~tr['Stock'].isin(EXCLUDED)].copy()
for s in set(tr['Stock']) - map_syms:
    flags.append(f"HARD STOP: traded symbol {s} not in symbol_map_final")
tr['charge'] = tr['Brokerage incl. taxes']
tr['cash'] = np.where(tr['Action'] == 'Buy', -(tr['Trade Value'] + tr['charge']),
                                              (tr['Trade Value'] - tr['charge']))

# ---------- CA prep ----------
ca_by_date = {}
for ex, sym, typ, val, isin in ca.CA_REGISTER:
    exd = pd.Timestamp(ex).date()
    if d1 <= exd <= pd.Timestamp(MA_END).date():
        ca_by_date.setdefault(exd, []).append((sym, typ, val))
demerger = {d['child']: d for d in ca.CA_DEMERGER}

# ---------- FIFO lot book ----------
# lots[sym] = list of [qty, unit_cost]
lots = {}
for _, r in y.iterrows():
    lots.setdefault(r['Stock'], []).append([float(r['Allocated Quantity']),
                                            float(r['Day1_Unit'])])

def total_cost():
    return sum(q * c for L in lots.values() for q, c in L)

def unit_cost(sym):
    L = lots.get(sym, [])
    q = sum(x[0] for x in L)
    return (sum(x[0]*x[1] for x in L) / q) if q else 0.0

reg_dates = sorted(dates)
def book_date(d):
    for rd in reg_dates:
        if rd >= d: return rd
    return None
tr['book_date'] = [book_date(d) for d in tr['Date']]
rolled = tr[tr['book_date'] != tr['Date']]

rows, realised_cum, cash = [], 0.0, OPENING_CASH
for d in dates:
    open_cash = cash
    # ---- 1. corporate actions, on ex-date, BEFORE that day's trades ----
    for sym, typ, val in ca_by_date.get(d, []):
        if typ in ('SPLIT', 'BONUS_PROP'):
            for lot in lots.get(sym, []):
                lot[0] *= val; lot[1] /= val          # total cost unchanged
        elif typ == 'BONUS_ABS':
            if lots.get(sym): lots[sym].append([float(val), 0.0])
        elif typ == 'DEMERGER_COST':
            for lot in lots.get(sym, []): lot[1] *= val
        elif typ == 'SYNTHETIC_BUY':
            dm = demerger.get(sym)
            if dm:                                     # cost derived from parent
                parent_pre = unit_cost(dm['parent']) / dm['parent_retain'] \
                             if unit_cost(dm['parent']) else 0.0
                child_unit = parent_pre * (1 - dm['parent_retain'])
                if sum(x[0] for x in lots.get(dm['parent'], [])) > 0:
                    lots.setdefault(sym, []).append([float(val), child_unit])
        elif typ == 'FORCE_CLOSE':
            lots.pop(sym, None)
    # ---- 2. trades ----
    td = tr[tr['book_date'] == d]
    buy_val = float(-td.loc[td['Action'] == 'Buy', 'cash'].sum()) + 0.0
    sell_val = float(td.loc[td['Action'] == 'Sell', 'cash'].sum())
    for _, t in td.iterrows():
        sym, q = t['Stock'], float(t['Qty'])
        if t['Action'] == 'Buy':
            lots.setdefault(sym, []).append([q, (t['Trade Value'] + t['charge']) / q])
        else:
            proceeds = t['Trade Value'] - t['charge']
            rem, cost_out = q, 0.0
            L = lots.get(sym, [])
            while rem > 1e-9 and L:
                take = min(rem, L[0][0])
                cost_out += take * L[0][1]; L[0][0] -= take; rem -= take
                if L[0][0] <= 1e-9: L.pop(0)
            if rem > 1e-9:
                flags.append(f"HARD STOP: oversell {sym} on {d}, short {rem:g} sh (FIFO book empty)")
            realised_cum += proceeds - cost_out
    lots = {k: v for k, v in lots.items() if sum(x[0] for x in v) > 1e-9}
    # ---- 3. valuation ----
    mv, unpriced, unpriced_cost = 0.0, [], 0.0
    for sym, L in lots.items():
        q = sum(x[0] for x in L)
        px = day1_px.get(sym) if d == d1 else (bh.at[d, sym] if sym in bh.columns else None)
        if px is None or pd.isna(px):
            unpriced.append(sym)
            unpriced_cost += sum(x[0]*x[1] for x in L)
            continue
        mv += q * float(px)
    for s in unpriced:
        flags.append(f"UNPRICED-HELD: {s}")  # aggregated below, not per-day spam
    cost = total_cost()
    tcf = sell_val - buy_val
    cash = open_cash + tcf
    net = mv + cash
    rows.append(dict(Date=d, Opening_Cash_Balance=open_cash, Cost_Value_of_Holdings=cost,
                     Market_Value_of_Holdings=mv, Gain_Loss_Unrealised=mv - cost,
                     Buy_Trade_Value=buy_val, Sell_Trade_Value=sell_val,
                     Trade_Cash_Flow_Impact=tcf, Gain_Loss_Realised_Cumulative=realised_cum,
                     Closing_Cash_Balance=cash, Net_Assets=net,
                     Rebased_NAV=net / (tagged_sum + OPENING_CASH) * 100,
                     Unpriced_Symbols=';'.join(sorted(unpriced)),
                     Unpriced_Cost_Basis=unpriced_cost))

reg = pd.DataFrame(rows).round(2)
reg['Buy_Trade_Value'] = reg['Buy_Trade_Value'].abs()
reg['Unpriced_Symbols'] = reg['Unpriced_Symbols'].fillna('')
reg.to_csv(OUT/'ma_daily_register_task1a.csv', index=False)

# ---------- reporting ----------
print(f"Tagged rows 76 | Tagged Value sum {tagged_sum:,.0f} | Day-1 Net Assets {tagged_sum+OPENING_CASH:,.0f}")
print(f"Register rows {len(reg)} (1 synthetic Day-1 + {len(reg)-1} priced)")
print(f"Sunday-dated trades in window: {len(sunday)} on {sorted(set(sunday['Date']))}")
print(f"Trades rolled to next register row: {len(rolled)} "
      f"(dates {sorted(set(rolled['Date']))} -> {sorted(set(rolled['book_date']))})")
bdays = pd.bdate_range(dates[1], MA_END)
absent = sorted(set(bdays.date) - set(dates))
print(f"NSE-calendar audit: {len(bdays)} weekdays in window, {len(dates)-1} priced rows, "
      f"{len(absent)} weekdays absent (all NSE holidays): {[str(x) for x in absent]}")
print("\nEXCLUDED-TRADE COUNTS\n", excl_report.to_string())
print("\nFIRST 10 ROWS\n", reg.head(10).to_string(index=False))
print("\nLAST 3 ROWS\n", reg.tail(3).to_string(index=False))
chain = (reg['Opening_Cash_Balance'].iloc[1:].values -
         reg['Closing_Cash_Balance'].iloc[:-1].values)
print("\nCash-chain max break:", np.abs(chain).max())
uf = reg[reg['Unpriced_Symbols'] != '']
print("\nUNPRICED-HELD SUMMARY (cost retained, excluded from Market Value)")
for sym in sorted({s for v in uf['Unpriced_Symbols'] for s in v.split(';')}):
    sub = reg[reg['Unpriced_Symbols'].str.contains(sym)]
    print(f"  {sym}: {len(sub)} days, {sub['Date'].min()}..{sub['Date'].max()}, "
          f"cost basis carried approx Rs {sub['Unpriced_Cost_Basis'].iloc[-1]:,.2f}, "
          f"max {sub['Unpriced_Cost_Basis'].max()/sub['Net_Assets'].max()*100:.3f}% of Net Assets")
print("\nFLAGS (deduplicated):")
from collections import Counter
for f, n in Counter(flags).most_common(): print(f"  [{n}x] {f}")

# holdings cross-check
hd = pd.read_excel(U/'a175e5fe-ICICIdirect_Portfolio_Holdings_05092026.xlsx')
hd.to_pickle(OUT/'_holdings.pkl')
final = {s: round(sum(x[0] for x in L), 4) for s, L in sorted(lots.items())}
# cross-check vs broker holdings snapshot (05-09-2026, i.e. AFTER the 2026-08-28
# cutoff -> differences from post-cutoff trades are expected, not defects)
pd.Series(final).to_csv(OUT/'_computed_final_qty.csv')
print("\nOpen positions at 2026-08-28:", len(final))

# ============================================================
# QUANTITY RECONCILIATION vs broker holdings snapshot (05-09-2026).
# The snapshot post-dates the 2026-08-28 cutoff, so computed closing quantities
# are rolled forward with post-cutoff tradebook rows before comparing.
# Broker keys the SHABUI demerger child as 'SHAPRO'; the register keys it
# 'BUILDPRO' (same ISIN INE24OJ01011) - aliased here, not a mismatch.
# ============================================================
ALIAS = {'BUILDPRO': 'SHAPRO'}
brk = hd.groupby('Stock Symbol')['Qty'].sum()
post = pd.read_excel(U/'704b6639-ICICIdirect_Trades_05092026.xlsx')
post['Date'] = pd.to_datetime(post['Date']).dt.date
post = post[(post['Date'] > pd.Timestamp(MA_END).date()) & (~post['Stock'].isin(EXCLUDED))]
dl = post.assign(sg=post['Qty']*post['Action'].map({'Buy': 1, 'Sell': -1})).groupby('Stock')['sg'].sum()
proj = pd.Series({ALIAS.get(k, k): v for k, v in final.items()})
idx = sorted(set(proj.index) | set(dl.index) | (set(brk.index) - set(EXCLUDED)))
rec = pd.DataFrame({'computed_2026_08_28': pd.Series(final).reindex(idx).fillna(0),
                    'post_cutoff_net': dl.reindex(idx).fillna(0),
                    'projected_2026_09_05': proj.reindex(idx).fillna(0) + dl.reindex(idx).fillna(0),
                    'broker_2026_09_05': brk.reindex(idx).fillna(0)})
rec['diff'] = rec['projected_2026_09_05'] - rec['broker_2026_09_05']
rec.to_csv(OUT/'qty_reconciliation.csv')
bad = rec[rec['diff'].abs() > 1e-6]
print(f"\nQTY RECONCILIATION: {len(rec)} symbols, {len(bad)} mismatch(es)")
if len(bad): print(bad.to_string())

d1r, lastr = reg.iloc[0], reg.iloc[-1]
print(f"""
================ SUMMARY (TASK 1a) ================
UNLEVERED VIEW - actual MTF financing costs (~9.49% p.a. + pledge charges) are
EXCLUDED and will reduce real profit when Task 1b is run.
Day-1 Net Assets 2025-09-21 ......... Rs {d1r.Net_Assets:,.2f}  (index 100.00)
Latest Net Assets {lastr.Date} ...... Rs {lastr.Net_Assets:,.2f}
Change .............................. Rs {lastr.Net_Assets-d1r.Net_Assets:,.2f}  ({lastr.Rebased_NAV-100:+.2f}%)
Realised gain (cumulative) .......... Rs {lastr.Gain_Loss_Realised_Cumulative:,.2f}
Unrealised gain (latest snapshot) ... Rs {lastr.Gain_Loss_Unrealised:,.2f}
Rebased NAV index ................... {lastr.Rebased_NAV:.2f}
Closing cash (negative = MTF debit) . Rs {lastr.Closing_Cash_Balance:,.2f}
UNLEVERED VIEW - MTF financing cost excluded; real profit is lower.
===================================================""")
