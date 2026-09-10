"""
TASK 1b v3 (FINAL) - MTF-aware register on SOF-BILLED financing.
Only the financing input and the loan-balance source change; every formula and
convention from Task 1b v1 is carried through unaltered.

  Cash_MTF   = Cash_Task1a + LoanBalance          (v1 approach, unchanged)
  NetAssets  = MV + Cash_MTF - LoanBalance - FinancingCost
  NAV        = NetAssets / 15,89,670 x 100

FINANCING GRANULARITY: per-day, not spread. The extended ledger carries the
actual daily SOF-billed interest and the daily pledge charge (DN = SOF x 1.18),
so the cumulative column steps on the days the broker actually billed, and the
2026-08-28 total falls out at Rs 12,620.38 rather than being imposed on it.
"""
from pathlib import Path
import pandas as pd, numpy as np

OUT = Path('/home/user/Scratch-2/task1a')
DAY1_NA = 1_589_670.00
MTF_ERA_START = pd.Timestamp('2026-04-27').date()
V1_FIN = 9_725.92                    # superseded: interest-only, modelled
V2_FIN = 12_620.38                   # superseded: SOF-billed but 2026-07-06 onward only
# The Rs 4,321.62 formerly carried separately is now SUBSUMED in the daily rows
# (SOF-billed interest 2026-04-27..06-19 = Rs 4,149.50). It is NOT added again.
flags = []

reg = pd.read_csv(OUT/'ma_daily_register_task1a.csv')
reg['Date'] = pd.to_datetime(reg['Date']).dt.date
v1 = pd.read_csv(OUT/'ma_daily_register_task1b_mtf.csv')
v1['Date'] = pd.to_datetime(v1['Date']).dt.date
v2 = pd.read_csv(OUT/'ma_daily_register_Task1b_v2_SOF_billed.csv')
v2['Date'] = pd.to_datetime(v2['Date']).dt.date

led = pd.read_excel(OUT/'MTF_Loan_Ledger_extended.xlsx', 'DAILY_LEDGER')
led['date'] = pd.to_datetime(led['date']).dt.date
led = led.set_index('date').sort_index()
LED_MAX = led.index.max()

gap = [d for d in reg['Date'] if d >= MTF_ERA_START and d not in led.index]
if gap: flags.append(f"HARD STOP: {len(gap)} post-era register days still uncovered ({gap[0]}..{gap[-1]})")
flags.append("FINANCING NOW COMPLETE: interest and pledge are SOF-billed across the whole MTF era "
             "(2026-04-27..2026-08-28). No floor, no ceiling, nothing carried outside the daily rows. "
             "Only 2026-07-01/02/03 lack a SOF (quarterly ends 06-30, weeklies start 07-06); their "
             "unbilled charges are worth a few hundred rupees at most.")

loan, tag, fin, cum, prev_d = [], [], [], 0.0, None
for d in reg['Date']:
    if d < MTF_ERA_START or d not in led.index:
        loan.append(0.0); tag.append('PRE-MTF(no loan)')
    else:
        loan.append(float(led.at[d, 'balance'])); tag.append(str(led.at[d, 'tag']))
    # Accrue EVERY ledger day up to this register date, not only ledger days that
    # happen to be trading days. The broker bills interest and pledge on Saturdays
    # too; matching ledger rows 1:1 to register rows silently dropped those
    # charges (Rs 2,398.07 of them, which is why the cutoff total came to
    # Rs 10,222.31 instead of the ledger's own Rs 12,620.38).
    due = led.loc[(led.index > prev_d) & (led.index <= d)] if prev_d else led.loc[led.index <= d]
    cum += float(np.nan_to_num(due['interest_sof_billed']).sum()
                 + np.nan_to_num(due['pledge_dn']).sum())
    prev_d = d
    fin.append(cum)

reg['MTF_Loan_Balance'] = np.round(loan, 2)
reg['Loan_Balance_Source'] = tag
reg['Financing_Cost_Cum_SOF_Billed'] = np.round(fin, 2)
reg['Closing_Cash_Balance_MTF'] = np.round(reg['Closing_Cash_Balance'] + reg['MTF_Loan_Balance'], 2)
reg['Net_Assets_MTF_v3'] = np.round(reg['Market_Value_of_Holdings'] + reg['Closing_Cash_Balance_MTF']
                                    - reg['MTF_Loan_Balance'] - reg['Financing_Cost_Cum_SOF_Billed'], 2)
reg['Rebased_NAV_MTF_v3'] = np.round(reg['Net_Assets_MTF_v3'] / DAY1_NA * 100, 2)
reg.to_csv(OUT/'ma_daily_register_Task1b_v3_final.csv', index=False)

# ---- loan-balance movement vs v1 (the 2026-07-04..10 correction) ------------
cmp_ = reg[['Date', 'MTF_Loan_Balance']].merge(
        v2[['Date', 'MTF_Loan_Balance']], on='Date', suffixes=('_v3', '_v2'))
cmp_['delta'] = cmp_['MTF_Loan_Balance_v3'] - cmp_['MTF_Loan_Balance_v2']
moved = cmp_[cmp_['delta'].abs() > 0.005]
moved.to_csv(OUT/'task1b_v3_loan_balance_diff.csv', index=False)

last = reg.iloc[-1]; last1 = v1.iloc[-1]
_c = led.loc[led.index <= reg['Date'].max()]
c_int = float(np.nan_to_num(_c['interest_sof_billed']).sum())
c_pl = float(np.nan_to_num(_c['pledge_dn']).sum())
chk = [('2025-09-21', 'Day-1'), ('2026-04-27', 'MTF era start'), ('2026-07-03', 'last old anchor'),
       ('2026-07-10', 'end of old ledger'), ('2026-08-28', 'cutoff')]
print("CHECKPOINTS")
print(f"{'Date':<12}{'label':<20}{'Loan':>13}{'Financing':>12}{'NetAssets_v3':>15}{'NAV_v3':>9}{'NAV_v2':>9}")
for ds, lab in chk:
    d = pd.Timestamp(ds).date()
    if not (reg['Date'] == d).any(): continue
    r = reg[reg['Date'] == d].iloc[0]; q = v2[v2['Date'] == d].iloc[0]
    print(f"{ds:<12}{lab:<20}{r['MTF_Loan_Balance']:>13,.2f}{r['Financing_Cost_Cum_SOF_Billed']:>12,.2f}"
          f"{r['Net_Assets_MTF_v3']:>15,.2f}{r['Rebased_NAV_MTF_v3']:>9.2f}{q['Rebased_NAV_MTF_v2']:>9.2f}")

print(f"\nLoan-balance rows changed vs v2: {len(moved)}")
print(moved.to_string(index=False))

lastv2 = v2.iloc[-1]
print(f"""
========== 4-WAY COMPARISON AT 2026-08-28 ==========
{'Version':<42}{'Net Assets':>15}{'NAV':>9}{'Gain vs Day-1':>16}
{'Task 1a  (unlevered, no financing)':<42}{last['Net_Assets']:>15,.2f}{last['Rebased_NAV']:>9.2f}{last['Net_Assets']-DAY1_NA:>16,.2f}
{'Task 1b v1 (modelled financing, SUPERSEDED)':<42}{last1['Net_Assets_MTF']:>15,.2f}{last1['Rebased_NAV_MTF']:>9.2f}{last1['Net_Assets_MTF']-DAY1_NA:>16,.2f}
{'Task 1b v2 (partial SOF, SUPERSEDED)':<42}{lastv2['Net_Assets_MTF_v2']:>15,.2f}{lastv2['Rebased_NAV_MTF_v2']:>9.2f}{lastv2['Net_Assets_MTF_v2']-DAY1_NA:>16,.2f}
{'Task 1b v3 (full SOF interest+pledge, FINAL)':<42}{last['Net_Assets_MTF_v3']:>15,.2f}{last['Rebased_NAV_MTF_v3']:>9.2f}{last['Net_Assets_MTF_v3']-DAY1_NA:>16,.2f}
----------------------------------------------------
Financing applied: v1 Rs {V1_FIN:,.2f} (modelled) -> v2 Rs {V2_FIN:,.2f} (partial SOF) -> v3 Rs {last['Financing_Cost_Cum_SOF_Billed']:,.2f} (billed)
Real financing erases Rs {last['Net_Assets']-last['Net_Assets_MTF_v3']:,.2f} of the Rs {last['Net_Assets']-DAY1_NA:,.2f}
unlevered gain = {(last['Net_Assets']-last['Net_Assets_MTF_v3'])/(last['Net_Assets']-DAY1_NA)*100:.1f}% of it, NAV 105.42 -> {last['Rebased_NAV_MTF_v3']:.2f}.
Split: interest Rs {c_int:,.2f} + pledge Rs {c_pl:,.2f}. Pledge is {c_pl/(c_int+c_pl)*100:.0f}% of financing.
====================================================""")
print("\nFLAGS:")
for f in flags: print(" -", f)
