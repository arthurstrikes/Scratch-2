"""
UNIFIED unit ledger — rebuilds unit segregation onto Task 1a/1b's anchor
(Rs15,89,670, NATSEC excluded, 76 tagged Day-1 names), collapsing the two
previously separate NAV figures into one.

Mint formula (managed_account_colab.py Cell 8b, unchanged):
    npre = (V + cash - loan - fin) / units      # pre-injection, same-day
    u    = amt / npre
Here (V + cash - loan - fin) is supplied directly by Task 1b-v3's
Net_Assets_MTF_v3 column, PLUS cumulative injected cash, which that register
excludes by construction (the 4 untagged names' sale proceeds and the Dec-30
externals never entered its flows).

EQUITY v2 event set (true-cash mints only — the GROSS model's 12 shortfall
mints are NOT part of this model):
    Day-1, the three 4-name sale dates, Dec-30 externals,
    2026-06-22 mint-only (units, no cash), 2026-07-05 Nilesh/Manas pair.
"""
import pandas as pd, numpy as np

DAY1_NA = 1_589_670.00
reg = pd.read_csv('ma_daily_register_Task1b_v3_final.csv')
reg['Date'] = pd.to_datetime(reg['Date'])
NA = reg.set_index('Date')['Net_Assets_MTF_v3'].sort_index()

def na_on(d):                       # ffill: event dates may be non-trading days
    s = NA[NA.index <= pd.Timestamp(d)]
    return float(s.iloc[-1]), s.index[-1]

# Day-1 seeding on the Rs15,89,670 anchor
MANAS_D1, MUKESH_D1 = 1_479_670.00, 110_000.00
um, uk, un = MANAS_D1/100.0, MUKESH_D1/100.0, 0.0
cum_cash = 0.0
manas_cost, mukesh_cost, nilesh_cost = MANAS_D1, MUKESH_D1, 0.0

EVENTS = [
    ('2025-09-26', 'Manas',   8_712.2333, 'cash'),
    ('2025-12-30', 'Mukesh', 30_000.00,   'cash'),
    ('2025-12-30', 'Nilesh', 30_000.00,   'cash'),
    ('2026-01-21', 'Manas',  71_991.2538, 'cash'),
    ('2026-04-08', 'Manas',   6_313.3695, 'cash'),
    ('2026-06-22', 'Manas',  18_451.51,   'mintonly'),
    ('2026-07-05', 'PAIR',   30_000.00,   'transfer'),
]
print(f"Day-1 2025-09-21: units {um+uk:,.6f} (Manas {um:,.2f} + Mukesh {uk:,.2f}) | NAV 100.0000")
print(f"\n{'date':<12}{'who':<8}{'amount':>13}{'kind':<11}{'npre':>10}{'units minted':>14}{'total units':>14}")
for d, who, amt, kind in EVENTS:
    na, src = na_on(d)
    units = um + uk + un
    npre = (na + cum_cash) / units
    u = amt / npre
    if kind == 'transfer':                      # net-zero: Nilesh in, Manas out
        un += u; um -= u
        nilesh_cost += amt; manas_cost -= amt
        note = f"+{u:.6f} Nilesh / -{u:.6f} Manas"
    else:
        if who == 'Manas':  um += u; manas_cost += amt
        elif who == 'Mukesh': uk += u; mukesh_cost += amt
        else: un += u; nilesh_cost += amt
        if kind == 'cash': cum_cash += amt
        note = f"{u:.6f}"
    tag = '' if pd.Timestamp(d) == src else f" (NAV ffill from {src.date()})"
    print(f"{d:<12}{who:<8}{amt:>13,.2f}{kind:<11}{npre:>10.4f}{note:>14}{um+uk+un:>14.6f}{tag}")

END = pd.Timestamp('2026-08-30')
na_end, src_end = na_on(END)
# 2026-08-29/30 are Sat/Sun: no trading, no price move, no trades, loan flat.
# The only movement is weekend financing accrual (SOF-billed, from the ledger):
# financing to 08-30 Rs31,976.29 vs Rs31,593.01 at 08-28.
WEEKEND_FIN = 31_976.29 - 31_593.01
na_end -= WEEKEND_FIN
NA_final = na_end + cum_cash
units_final = um + uk + un
NAV_final = NA_final / units_final
print(f"\n=== 2026-08-30 (register NA from {src_end.date()}; 08-29/30 are Sat/Sun, no trading) ===")
print(f"register Net Assets {na_end:,.2f} (08-28 less weekend financing {WEEKEND_FIN:,.2f}) "
      f"+ injected cash {cum_cash:,.2f} = {NA_final:,.2f}")
print(f"units {units_final:,.6f} | NAV {NAV_final:.4f}")

print(f"\n{'Contributor':<12}{'units':>15}{'own%':>9}{'value':>16}{'blended entry':>15}{'return':>9}")
rows = [('Manas', um, manas_cost), ('Mukesh', uk, mukesh_cost), ('Nilesh', un, nilesh_cost)]
for nm, u, cost in rows:
    bnav = cost/u
    print(f"{nm:<12}{u:>15.6f}{u/units_final*100:>9.3f}{u*NAV_final:>16,.2f}{bnav:>15.4f}{(NAV_final/bnav-1)*100:>+8.2f}%")
print(f"{'TOTAL':<12}{units_final:>15.6f}{100.0:>9.3f}{units_final*NAV_final:>16,.2f}")
print(f"\nVALIDATION units x NAV = {units_final*NAV_final:,.2f} vs Net Assets {NA_final:,.2f} "
      f"| delta {units_final*NAV_final-NA_final:+.6f}")
print(f"contributed capital: Manas {manas_cost:,.2f} + Mukesh {mukesh_cost:,.2f} + Nilesh {nilesh_cost:,.2f} "
      f"= {manas_cost+mukesh_cost+nilesh_cost:,.2f}")
