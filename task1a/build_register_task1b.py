"""
TASK 1b - MTF-aware daily register. ADDITIVE to Task 1a; writes new files only.

WHAT 1b ADDS
  * MTF Loan Balance, taken DIRECTLY from MTF_Loan_Ledger.xlsx DAILY_LEDGER
    'balance' (GATE1: 6/6 exact SOF anchors). Never derived from a margin %.
  * Financing Cost (cumulative), on the SOF-BILLED basis per the ledger README
    ("MA-EQUITY financing = SOF-BILLED, NOT this advisory accrual").
  * Net Assets redefined to net out the loan and charge financing.

CLOSING-CASH APPROACH (choice named, per spec #4)
  Approach B-corrected. Task 1a booked every MTF buy as a full-value cash
  outflow, which is why its cash went negative from exactly 2026-04-27 (the MTF
  era start). The true cash never went negative - the shortfall WAS the loan.
  Since LoanBalance = cumulative draws - repayments,
        Cash_MTF_aware(t) = Cash_Task1a(t) + LoanBalance(t)
  recovers the real cash without needing a per-trade margin/loan split. The
  identity is directionally confirmed - Task 1a's cash turns negative on exactly
  2026-04-27, the MTF era start, and not one day earlier - but the daily residual
  is volatile (see flag on settlement-basis mismatch), so it is a reconstruction,
  not a bank statement. This is
  the cleaner of the two options offered: it removes the negative-cash display
  artifact AND keeps Net Assets identical to the "leave cash, subtract loan"
  formulation, because the loan cancels:
        NetAssets = MV + Cash_MTF_aware - Loan - FinancingCost
                  = MV + Cash_Task1a - FinancingCost
  i.e. leverage by itself moves neither Net Assets nor NAV - only the financing
  cost does. That identity is the whole economic content of Task 1b.
"""
import importlib.util
from pathlib import Path
import pandas as pd, numpy as np

U = Path('/root/.claude/uploads/7bd3b4cf-fc56-51a0-a6fa-0200b1bb0a88')
OUT = Path('/home/user/Scratch-2/task1a')
MTF_ERA_START = pd.Timestamp('2026-04-27').date()
DAY1_NA = 1_589_670.00
flags = []

reg = pd.read_csv(OUT/'ma_daily_register_task1a.csv')
reg['Date'] = pd.to_datetime(reg['Date']).dt.date

led = pd.read_excel(U/'cc910e95-MTF_Loan_Ledger.xlsx', 'DAILY_LEDGER')
led['date'] = pd.to_datetime(led['date']).dt.date
anch = pd.read_excel(U/'cc910e95-MTF_Loan_Ledger.xlsx', 'GATE1_ANCHORS')
anch['anchor_date'] = pd.to_datetime(anch['anchor_date']).dt.date
conv = pd.read_excel(U/'aee8d1a8-MTF_converted_to_delivery.xlsx')
conv['D'] = pd.to_datetime(conv['Date']).dt.date

led_bal = dict(zip(led['date'], led['balance']))
led_adv = dict(zip(led['date'], led['interest_accrued_advisory']))
LED_MIN, LED_MAX = min(led_bal), max(led_bal)

# ---- coverage audit --------------------------------------------------------
post_era = [d for d in reg['Date'] if d >= MTF_ERA_START]
gap = sorted(d for d in post_era if d not in led_bal)
if gap:
    flags.append(f"HARD STOP: {len(gap)} register days on/after the MTF era start have NO loan-ledger "
                 f"row ({gap[0]}..{gap[-1]}); ledger ends {LED_MAX} with a non-zero balance of "
                 f"Rs {led_bal[LED_MAX]:,.2f}. Zero-filling would assert the loan was repaid, which the "
                 f"ledger does not say. Primary series CARRIES FORWARD the last known balance, flagged "
                 f"CARRY-FORWARD(unverified); the zero-fill variant is quantified in the summary.")

# ---- SOF-billed financing --------------------------------------------------
# GATE_STATUS: advisory Rs 5,035.95 vs SOF-billed Rs 4,321.62 to 2026-06-19 = +16.53%.
SOF_BILLED_TO = pd.Timestamp('2026-06-19').date()
SOF_BILLED_AMT = 4_321.62
ADV_TO_SOF_DATE = 5_035.95
DEFLATOR = SOF_BILLED_AMT / ADV_TO_SOF_DATE          # 0.8582 -> advisory is 16.53% high
flags.append("PLEDGE CHARGES NOT SUPPLIED: the README's financing rule is 'SOF-billed interest + "
             "pledge'. Only the interest leg (Rs 4,321.62 to 2026-06-19) is in the supplied files. "
             "Financing cost below is interest-only and is therefore a FLOOR, not the full charge.")

def loan_and_tag(d):
    if d < MTF_ERA_START or d < LED_MIN:
        return 0.0, 'PRE-MTF(no loan)'
    if d in led_bal:
        return float(led_bal[d]), str(led.loc[led['date'] == d, 'tag'].iloc[0])
    return float(led_bal[LED_MAX]), 'CARRY-FORWARD(unverified)'

loan, tag, adv_cum, sof_cum, cum_a, cum_s = [], [], [], [], 0.0, 0.0
last_adv = float(led.loc[led['date'] == LED_MAX, 'interest_accrued_advisory'].iloc[0])
for d in reg['Date']:
    b, t = loan_and_tag(d)
    loan.append(b); tag.append(t)
    day_adv = led_adv.get(d, last_adv if d > LED_MAX else 0.0)
    if d < MTF_ERA_START: day_adv = 0.0
    cum_a += day_adv
    cum_s += day_adv * DEFLATOR
    adv_cum.append(cum_a); sof_cum.append(cum_s)

reg['MTF_Loan_Balance'] = np.round(loan, 2)
reg['Loan_Balance_Source'] = tag
reg['Financing_Cost_Cum_Advisory'] = np.round(adv_cum, 2)
reg['Financing_Cost_Cum_SOF'] = np.round(sof_cum, 2)          # SOF-billed basis (canonical)
reg['Closing_Cash_Balance_MTF'] = np.round(reg['Closing_Cash_Balance'] + reg['MTF_Loan_Balance'], 2)
reg['Net_Assets_MTF'] = np.round(reg['Market_Value_of_Holdings'] + reg['Closing_Cash_Balance_MTF']
                                 - reg['MTF_Loan_Balance'] - reg['Financing_Cost_Cum_SOF'], 2)
reg['Rebased_NAV_MTF'] = np.round(reg['Net_Assets_MTF'] / DAY1_NA * 100, 2)
reg.to_csv(OUT/'ma_daily_register_task1b_mtf.csv', index=False)

# ---- checks ----------------------------------------------------------------
rec = anch.copy()
rec['register_loan'] = [reg.loc[reg['Date'] == d, 'MTF_Loan_Balance'].iloc[0] if (reg['Date'] == d).any()
                        else np.nan for d in rec['anchor_date']]
rec['delta_vs_SOF'] = rec['register_loan'] - rec['SOF_LOAN_BALANCE']
rec.to_csv(OUT/'task1b_gate1_recheck.csv', index=False)
gate_pass = bool((rec['delta_vs_SOF'].abs() < 0.005).all())

TOL = 3  # calendar days
crows = []
for _, c in conv.sort_values('D').iterrows():
    if c['D'] < LED_MIN:
        st = 'PRE-LEDGER (before 2026-04-27 era start; no repay row can exist)'
    else:
        near = led[(led['date'] >= c['D'] - pd.Timedelta(days=TOL).to_pytimedelta()) &
                   (led['date'] <= c['D'] + pd.Timedelta(days=TOL).to_pytimedelta()) & (led['repay'] > 0)]
        st = (f"MATCHED repay Rs {near['repay'].sum():,.2f} within +/-{TOL}d" if len(near)
              else 'NO REPAY WITHIN TOLERANCE')
        if not len(near): flags.append(f"HARD STOP: conversion {c['Stock']} {c['D']} Rs {c['Amount']:,.2f} "
                                       f"has no ledger repay entry within +/-{TOL} days")
    crows.append(dict(Date=c['D'], Stock=c['Stock'], Qty=c['Converted Qty'], Amount=c['Amount'], Check=st))
cchk = pd.DataFrame(crows); cchk.to_csv(OUT/'task1b_conversion_check.csv', index=False)

resid = reg.loc[reg['Date'] >= MTF_ERA_START, 'Closing_Cash_Balance_MTF']
inled = reg[(reg['Date'] >= MTF_ERA_START) & (reg['Loan_Balance_Source'] != 'CARRY-FORWARD(unverified)')]
flags.append(f"SETTLEMENT-BASIS MISMATCH (finding, not a stop): residual cash (Task-1a cash + ledger "
             f"loan) over the {len(inled)} ledger-covered days runs min Rs {inled['Closing_Cash_Balance_MTF'].min():,.0f} / "
             f"median Rs {inled['Closing_Cash_Balance_MTF'].median():,.0f} / max Rs {inled['Closing_Cash_Balance_MTF'].max():,.0f}, "
             f"negative on {(inled['Closing_Cash_Balance_MTF']<0).sum()} of them. The register books trades on TRADE date; "
             f"the ledger draws/repays on SETTLEMENT (T+1) basis, and 30 of 75 ledger days are INTERPOLATED "
             f"between weekly SOF anchors. Net Assets is unaffected (the loan cancels), but the Closing "
             f"Cash / Loan Balance split on any single day is approximate.")
last = reg.iloc[-1]
zero_fill_na = last['Market_Value_of_Holdings'] + last['Closing_Cash_Balance'] - last['Financing_Cost_Cum_SOF']

print(f"Ledger: {LED_MIN} .. {LED_MAX}, {len(led)} rows, final balance Rs {led_bal[LED_MAX]:,.2f}")
print(f"Register days on/after era start with no ledger row: {len(gap)}"
      + (f" ({gap[0]} .. {gap[-1]})" if gap else ""))
print(f"GATE1 anchor re-check: {'PASS' if gate_pass else 'FAIL'} (max |delta| {rec['delta_vs_SOF'].abs().max():.4f})")
print(f"\nCONVERSION CROSS-CHECK ({len(cchk)} events)\n{cchk.to_string(index=False)}")
print(f"\nResidual cash after adding loan back, from era start: min Rs {resid.min():,.2f}, "
      f"max Rs {resid.max():,.2f}  (near-zero/positive = the negative-cash artifact was exactly the loan)")
print(f"""
================ SUMMARY (TASK 1b - MTF-AWARE) ================
Financing basis: SOF-BILLED (advisory accrual deflated by {DEFLATOR:.4f}; advisory runs +16.53% high,
demoted per the ledger's own README). INTEREST ONLY - pledge charges were not supplied.
Day-1 Net Assets 2025-09-21 ............ Rs {DAY1_NA:,.2f}  (index 100.00)
Latest {last['Date']} Net Assets (MTF) .. Rs {last['Net_Assets_MTF']:,.2f}
Latest NAV index (MTF) ................. {last['Rebased_NAV_MTF']:.2f}
Financing cost, cumulative (SOF basis) . Rs {last['Financing_Cost_Cum_SOF']:,.2f}
Financing cost, advisory basis ......... Rs {last['Financing_Cost_Cum_Advisory']:,.2f}
MTF Loan Balance at cutoff ............. Rs {last['MTF_Loan_Balance']:,.2f} [{last['Loan_Balance_Source']}]
Closing cash, MTF-aware ................ Rs {last['Closing_Cash_Balance_MTF']:,.2f}
--- vs TASK 1a (unlevered benchmark) ---
Task 1a Net Assets ..................... Rs {last['Net_Assets']:,.2f}  (NAV {last['Rebased_NAV']:.2f}, +5.42%)
Task 1b Net Assets ..................... Rs {last['Net_Assets_MTF']:,.2f}  (NAV {last['Rebased_NAV_MTF']:.2f})
Difference ............................. Rs {last['Net_Assets_MTF']-last['Net_Assets']:,.2f} (= financing cost)
Zero-fill variant (post-ledger loan=0) . Net Assets Rs {zero_fill_na:,.2f} - IDENTICAL, because the loan
  cancels out of Net Assets under this formulation; the gap affects only the Loan Balance and Closing
  Cash columns as displayed, not the NAV.
===============================================================""")
print("\nFLAGS:")
for f in flags: print(" -", f)
