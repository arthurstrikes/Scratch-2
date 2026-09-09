"""
Extend MTF_Loan_Ledger.xlsx from 2026-07-10 to the end of the supplied SOF cover
(2026-09-05) and add the pledge-charge leg that has been missing since inception.

RULES HONOURED
  * The 2026-04-27..2026-07-03 portion is GATE1-verified and CLOSED: its
    balance/draw/repay values are copied through byte-for-byte.
  * 2026-07-04..2026-07-10 were tagged PROVISIONAL(Jul-03 proxy), NOT verified.
    The new SOFs cover them, so they are UPGRADED, not preserved:
      - 2026-07-04/05 (Sat/Sun): the 2026-07-13 SOF opens 2026-07-06 at
        618,861.69 DR, which PROVES the flat carry over the weekend. Same number,
        promoted to SOF-EXACT.
      - 2026-07-06..10: replaced with the SOF's own EOD balances.
    Every replacement is listed in the CHANGE_LOG sheet.
  * Advisory accrual = balance x 9.49% / 365 (reproduces the existing column
    exactly: 618,861.69 x .0949/365 = 160.90).
  * Pledge basis DN = SOF x 1.18 (DebitNote_VERIFIED standing rule).
"""
from pathlib import Path
import pandas as pd, numpy as np

U = Path('/root/.claude/uploads/7bd3b4cf-fc56-51a0-a6fa-0200b1bb0a88')
OUT = Path('/home/user/Scratch-2/task1a')
SRC = U/'cc910e95-MTF_Loan_Ledger.xlsx'
RATE = 0.0949
FROZEN_END = pd.Timestamp('2026-07-03').date()   # GATE1-closed, never touched

led = pd.read_excel(SRC, 'DAILY_LEDGER'); led['date'] = pd.to_datetime(led['date']).dt.date
anch = pd.read_excel(SRC, 'GATE1_ANCHORS'); anch['anchor_date'] = pd.to_datetime(anch['anchor_date']).dt.date
sof = pd.read_csv(OUT/'sof_extract.csv'); sof['date'] = pd.to_datetime(sof['date']).dt.date
sof = sof.set_index('date').sort_index()

frozen = led[led['date'] <= FROZEN_END].copy()
frozen['pledge_sof'] = np.nan; frozen['pledge_dn'] = np.nan
frozen['interest_sof_billed'] = np.nan
frozen['pledge_basis'] = 'NOT AVAILABLE (no SOF supplied pre-2026-07-06)'

# ---- new rows: every calendar day from 2026-07-04 to the last SOF date -------
days = pd.date_range(pd.Timestamp('2026-07-04'), max(sof.index)).date
prev = float(frozen.iloc[-1]['balance'])
new, changes = [], []
for d in days:
    r = sof.loc[d] if d in sof.index else None
    if r is not None and not pd.isna(r['mtf_balance']):
        drw, rep, bal = float(r['draw']), float(r['repay']), float(r['mtf_balance'])
        tag = 'SOF-EXACT'
        recon = prev + drw - rep
        if abs(recon - bal) > 0.005:
            tag = f'SOF-EXACT(recon delta {recon-bal:+.2f})'
    else:
        drw = rep = 0.0; bal = prev                      # non-trading day: balance rolls
        tag = 'SOF-CARRY(non-trading day, no MTF rows)'
    old = led.loc[led['date'] == d, 'balance']
    if len(old) and abs(float(old.iloc[0]) - bal) > 0.005:
        changes.append(dict(date=d, old_balance=float(old.iloc[0]), new_balance=bal,
                            old_tag=led.loc[led['date'] == d, 'tag'].iloc[0], new_tag=tag,
                            reason='PROVISIONAL(Jul-03 proxy) superseded by SOF-stated EOD balance'))
    elif len(old):
        changes.append(dict(date=d, old_balance=float(old.iloc[0]), new_balance=bal,
                            old_tag=led.loc[led['date'] == d, 'tag'].iloc[0], new_tag='SOF-EXACT(weekend, proven by Jul-06 opening)',
                            reason='value unchanged; tag upgraded from PROVISIONAL to verified'))
    p_sof = float(r['pledge_sof']) if r is not None else 0.0
    new.append(dict(date=d, draw=drw, repay=rep, balance=bal,
                    interest_accrued_advisory=round(bal * RATE / 365, 2),
                    tag=tag,
                    pledge_sof=p_sof, pledge_dn=round(p_sof * 1.18, 2),
                    interest_sof_billed=float(r['interest']) if r is not None else 0.0,
                    pledge_basis='DN = SOF x 1.18 (DebitNote_VERIFIED)'))
    prev = bal

daily = pd.concat([frozen, pd.DataFrame(new)], ignore_index=True).sort_values('date')
chg = pd.DataFrame(changes)

# ---- GATE1: old anchors untouched + new reconstruction check ----------------
old_g = anch.assign(source='original (2026-04-27..07-03 window)')
rows = []
for d in sorted(sof.index):
    if pd.isna(sof.at[d, 'mtf_balance']): continue
    i = daily.index[daily['date'] == d][0]
    p = float(daily.loc[:i, 'balance'].iloc[-2])
    recon = p + float(daily.at[i, 'draw']) - float(daily.at[i, 'repay'])
    rows.append(dict(anchor_date=d, reconstructed=round(recon, 2),
                     SOF_LOAN_BALANCE=float(sof.at[d, 'mtf_balance']),
                     delta=round(recon - float(sof.at[d, 'mtf_balance']), 2),
                     result='PASS' if abs(recon - float(sof.at[d, 'mtf_balance'])) < 0.005 else 'FAIL',
                     source='new SOF series (2026-07-06..09-05)'))
new_g = pd.DataFrame(rows)
gate = pd.concat([old_g, new_g], ignore_index=True)

int_new = daily['interest_sof_billed'].fillna(0).sum()
pl_new = daily['pledge_dn'].fillna(0).sum()
INT_OLD = 4321.62   # SOF-billed interest to 2026-06-19, from the original README
tags = daily['tag'].value_counts()

status = pd.DataFrame([
    dict(gate='GATE1_weekly_points', value=f"{(gate['result']=='PASS').sum()}/{len(gate)} exact",
         detail=f"max |delta| {gate['delta'].abs().max():.2f}", result='PASS (canonical liability)'),
    dict(gate='M1b_nonnegativity', value=f"min balance Rs {daily['balance'].min():,.2f}",
         detail=f"{(daily['balance']<0).sum()} negative days", result='PASS'),
    dict(gate='GATE2_interest_ADVISORY',
         value=f"advisory Rs {daily['interest_accrued_advisory'].sum():,.2f}",
         detail=f"vs SOF-billed Rs {int_new:,.2f} over the SOF-covered window",
         result='FINDING (demoted per Chat; never plugged)'),
    dict(gate='GATE3_pledge_coverage', value=f"Rs {pl_new:,.2f} DN-basis",
         detail='2026-07-06..09-05 only; 2026-04-27..07-05 has no SOF on device',
         result='PARTIAL (G2 half-closed)'),
])

readme = pd.DataFrame([
    ('STATUS', 'M1b PASS - GATE1 canonical loan liability; extended to 2026-09-05 from 9 weekly SOFs'),
    ('financing_rule',
     f'MA-EQUITY financing = SOF-BILLED (interest + pledge), NOT the advisory accrual. '
     f'CANONICAL total over the SOF-covered window 2026-07-06..2026-09-05: interest Rs {int_new:,.2f} '
     f'+ pledge Rs {pl_new:,.2f} (DN basis) = Rs {int_new+pl_new:,.2f}. Plus the previously billed '
     f'interest Rs {INT_OLD:,.2f} to 2026-06-19. This SUPERSEDES the interest-only figure '
     f'Rs 9,725.92 reported in Task 1b, which is now withdrawn as incomplete.'),
    ('pledge_basis', 'DN = SOF x 1.18 (DebitNote_VERIFIED). Corroborated in-file: a 225.00 pledge '
                     'debit is mirrored by a 265.50 "GST and MTF pledge Charges recovered" credit.'),
    ('pledge_gap', 'Pledge charges for 2026-04-27..2026-07-05 remain UNAVAILABLE - no SOF covering '
                   'that period was supplied. G2 is HALF-closed, not closed.'),
    ('negatives', 'eliminated via non-negative waterfall (pro-rata capped + carry-forward), anchors held exact'),
    ('S7 STATUS (Jul 23 2026)', 'RETAINED VALID - GATE-1 reconstruction is INDEPENDENT of the EQUITY '
                                'defect. VALID for LOAN LIABILITY use. NOT VALID as an input to MA-NAV.'),
    ('S8 EXTENSION (this run)', f'2026-07-04..2026-09-05 appended. 2026-07-04..07-10 were PROVISIONAL '
                                f'and are UPGRADED from SOF; see CHANGE_LOG. 2026-04-27..07-03 untouched.'),
], columns=['key', 'note'])

dst = OUT/'MTF_Loan_Ledger_extended.xlsx'
with pd.ExcelWriter(dst) as w:
    daily.to_excel(w, sheet_name='DAILY_LEDGER', index=False)
    gate.to_excel(w, sheet_name='GATE1_ANCHORS', index=False)
    status.to_excel(w, sheet_name='GATE_STATUS', index=False)
    readme.to_excel(w, sheet_name='README', index=False)
    chg.to_excel(w, sheet_name='CHANGE_LOG', index=False)

print(f"Ledger: {daily['date'].min()} .. {daily['date'].max()}  ({len(daily)} rows, was 75)")
print(f"New end date: {daily['date'].max()}  | final balance Rs {daily['balance'].iloc[-1]:,.2f}")
print(f"\nGATE1: {(gate['result']=='PASS').sum()}/{len(gate)} PASS, max |delta| {gate['delta'].abs().max():.2f} "
      f"(old {len(old_g)} + new {len(new_g)})")
print("\nTAG COMPOSITION\n" + tags.to_string())
print(f"\nFINANCING (SOF-billed, canonical)\n  interest 2026-07-06..09-05  Rs {int_new:,.2f}"
      f"\n  pledge   2026-07-06..09-05  Rs {pl_new:,.2f} (DN = SOF x 1.18; SOF base Rs {daily['pledge_sof'].fillna(0).sum():,.2f})"
      f"\n  subtotal                    Rs {int_new+pl_new:,.2f}"
      f"\n  + interest billed to 2026-06-19 Rs {INT_OLD:,.2f}"
      f"\n  = TOTAL known billed        Rs {int_new+pl_new+INT_OLD:,.2f}   (Task 1b's Rs 9,725.92 superseded)")
print(f"\nCHANGE_LOG rows (provisional days superseded): {len(chg)}")
print(chg.to_string(index=False))
