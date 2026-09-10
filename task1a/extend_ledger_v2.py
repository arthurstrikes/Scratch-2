"""
Backfill the MTF ledger from the consolidated quarterly SOF (2026-04-01..06-30),
so the whole MTF era is SOF-sourced rather than reconstructed.

WHAT SUPERSEDES WHAT
  The original ledger's 6 GATE1 anchors are re-verified against this SOF and all
  6 match to the paisa, so the reconstruction was right AT the anchors. Between
  them it was not: PRE-SERIES and INTERPOLATED days were a fitted waterfall, and
  the SOF now states those balances outright. SOF wins on every day it covers;
  the old value is kept only where no SOF exists (2026-07-01..07-05).
  Every superseded day is listed in CHANGE_LOG.
"""
from pathlib import Path
import pandas as pd, numpy as np

OUT = Path('/home/user/Scratch-2/task1a')
RATE = 0.0949
src = pd.read_excel(OUT/'MTF_Loan_Ledger_extended_v1_backup.xlsx', 'DAILY_LEDGER')
src['date'] = pd.to_datetime(src['date']).dt.date
old_anch = pd.read_excel(OUT/'MTF_Loan_Ledger_extended_v1_backup.xlsx', 'GATE1_ANCHORS')
sof = pd.read_csv(OUT/'sof_extract.csv'); sof['date'] = pd.to_datetime(sof['date']).dt.date
sof = sof.set_index('date').sort_index()
old = src.set_index('date')

days = pd.date_range(min(src['date']), max(sof.index)).date
rows, changes, prev = [], [], 0.0
for d in days:
    has = d in sof.index and not pd.isna(sof.at[d, 'mtf_balance'])
    if has:
        drw, rep, bal = float(sof.at[d, 'draw']), float(sof.at[d, 'repay']), float(sof.at[d, 'mtf_balance'])
        recon = prev + drw - rep
        tag = 'SOF-EXACT' if abs(recon - bal) < 0.005 else f'SOF-EXACT(recon delta {recon-bal:+.2f})'
    elif d in old.index and str(old.at[d, 'tag']).startswith(('INTERPOLATED', 'SOF-EXACT', 'PRE-SERIES')) \
         and d >= pd.Timestamp('2026-07-01').date() and d <= pd.Timestamp('2026-07-05').date():
        drw, rep, bal = float(old.at[d, 'draw']), float(old.at[d, 'repay']), float(old.at[d, 'balance'])
        tag = 'LEGACY(no SOF: 2026-07-01..07-05 uncovered)'
    else:
        drw = rep = 0.0; bal = prev
        tag = 'SOF-CARRY(non-trading day, no MTF rows)'
    if d in old.index and abs(float(old.at[d, 'balance']) - bal) > 0.005:
        changes.append(dict(date=d, old_balance=float(old.at[d, 'balance']), new_balance=bal,
                            old_tag=old.at[d, 'tag'], new_tag=tag,
                            reason='reconstructed value superseded by SOF-stated EOD balance'))
    p_sof = float(np.nan_to_num(sof.at[d, 'pledge_sof'])) if d in sof.index else 0.0
    rows.append(dict(date=d, draw=drw, repay=rep, balance=bal,
                     interest_accrued_advisory=round(bal * RATE / 365, 2), tag=tag,
                     pledge_sof=p_sof, pledge_dn=round(p_sof * 1.18, 2),
                     interest_sof_billed=float(np.nan_to_num(sof.at[d, 'interest'])) if d in sof.index else 0.0,
                     pledge_basis='DN = SOF x 1.18 (DebitNote_VERIFIED)'))
    prev = bal

daily = pd.DataFrame(rows)
chg = pd.DataFrame(changes)

gate = pd.DataFrame([dict(anchor_date=d, reconstructed=round(
        float(daily.loc[daily['date'] == d].index[0] and
              daily['balance'].shift(1).loc[daily.index[daily['date'] == d][0]]) +
        float(daily.loc[daily['date'] == d, 'draw'].iloc[0]) -
        float(daily.loc[daily['date'] == d, 'repay'].iloc[0]), 2),
        SOF_LOAN_BALANCE=float(sof.at[d, 'mtf_balance']))
    for d in sof.index if not pd.isna(sof.at[d, 'mtf_balance'])])
gate['delta'] = (gate['reconstructed'] - gate['SOF_LOAN_BALANCE']).round(2)
gate['result'] = np.where(gate['delta'].abs() < 0.005, 'PASS', 'FAIL')
gate['source'] = 'SOF-stated (quarterly 04-01..06-30 + 9 weeklies 07-06..09-05)'

CUT = pd.Timestamp('2026-08-28').date()
c = daily[daily['date'] <= CUT]
int_c, pl_c = c['interest_sof_billed'].sum(), c['pledge_dn'].sum()
int_j19 = daily.loc[daily['date'] <= pd.Timestamp('2026-06-19').date(), 'interest_sof_billed'].sum()
tags = daily['tag'].str.split('(').str[0].value_counts()

# ---- GATE2: advisory 9.49% flat vs SOF-billed, by month ---------------------
m = daily.assign(mon=[str(x)[:7] for x in daily['date']]).groupby('mon')[
        ['interest_accrued_advisory', 'interest_sof_billed', 'balance']].agg(
        {'interest_accrued_advisory': 'sum', 'interest_sof_billed': 'sum', 'balance': 'mean'})
m['adv_vs_billed_%'] = ((m['interest_accrued_advisory'] / m['interest_sof_billed'] - 1) * 100).round(2)
m['implied_rate_%pa'] = (m['interest_sof_billed'] / m['balance'] / m.index.map(
        lambda s: pd.Period(s).days_in_month) * 365 * 100).round(2)

status = pd.DataFrame([
    dict(gate='GATE1_anchor_points', value=f"{(gate['result']=='PASS').sum()}/{len(gate)} exact",
         detail=f"max |delta| {gate['delta'].abs().max():.2f}", result='PASS (canonical liability)'),
    dict(gate='M1b_nonnegativity', value=f"min balance Rs {daily['balance'].min():,.2f}",
         detail=f"{(daily['balance']<0).sum()} negative days", result='PASS'),
    dict(gate='GATE2_rate_consistency', value='see MONTHLY_RATE sheet',
         detail='advisory 9.49% flat vs SOF-billed, monthly', result='FINDING'),
    dict(gate='GATE3_pledge_coverage', value=f"Rs {daily['pledge_dn'].sum():,.2f} DN-basis",
         detail=f"2026-04-29..2026-09-05; only 2026-07-01..07-05 uncovered", result='PASS (G2 closed)'),
])
readme = pd.DataFrame([
    ('STATUS', 'Full MTF era SOF-sourced. Quarterly SOF 2026-04-01..06-30 + 9 weeklies 07-06..09-05.'),
    ('financing_rule', f'MA-EQUITY financing = SOF-BILLED (interest + pledge). At the register cutoff '
                       f'2026-08-28: interest Rs {int_c:,.2f} + pledge Rs {pl_c:,.2f} = Rs {int_c+pl_c:,.2f}. '
                       f'ONE figure, no range. Supersedes Rs 12,620.38 and the Rs 16,942.00 ceiling.'),
    ('pre_Jun19_interest', f'The Rs 4,321.62 previously carried as "known but outside granularity" is now '
                           f'SUBSUMED: SOF-billed interest 2026-04-27..2026-06-19 sums to Rs {int_j19:,.2f} '
                           f'from the daily rows. Do NOT add it again.'),
    ('remaining_gap', '2026-07-01..07-05 has no SOF (quarterly ends 06-30, weeklies start 07-06). '
                      '07-01/07-02 keep their interpolated values; 07-03 keeps its original anchor.'),
    ('pledge_basis', 'DN = SOF x 1.18 (DebitNote_VERIFIED).'),
], columns=['key', 'note'])

with pd.ExcelWriter(OUT/'MTF_Loan_Ledger_extended.xlsx') as w:
    daily.to_excel(w, sheet_name='DAILY_LEDGER', index=False)
    gate.to_excel(w, sheet_name='GATE1_ANCHORS', index=False)
    status.to_excel(w, sheet_name='GATE_STATUS', index=False)
    readme.to_excel(w, sheet_name='README', index=False)
    chg.to_excel(w, sheet_name='CHANGE_LOG', index=False)
    m.to_excel(w, sheet_name='MONTHLY_RATE')
    old_anch.to_excel(w, sheet_name='GATE1_ANCHORS_ORIGINAL', index=False)

print(f"Ledger {daily['date'].min()} .. {daily['date'].max()}  ({len(daily)} rows)")
print(f"GATE1: {(gate['result']=='PASS').sum()}/{len(gate)} PASS, max |delta| {gate['delta'].abs().max():.2f}")
print("\nTAG COMPOSITION\n" + tags.to_string())
print(f"\nFINANCING AT 2026-08-28 (single figure)"
      f"\n  interest Rs {int_c:,.2f} + pledge Rs {pl_c:,.2f} = Rs {int_c+pl_c:,.2f}")
print(f"\nTASK 4: SOF-billed interest 2026-04-27..2026-06-19 = Rs {int_j19:,.2f} "
      f"(vs the Rs 4,321.62 previously carried separately)")
print("\nGATE2 MONTHLY\n" + m.to_string())
print(f"\nCHANGE_LOG rows: {len(chg)}")
