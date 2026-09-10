"""
Dispatch 1 - MA whole-book institutional performance suite.
CONSUMES the closed NAV (101.6600 / Rs18,08,493.53 / 17,789.627703u at 2026-08-30).
Nothing here recomputes NAV or unit counts.

Daily unified NAV path = (register Net_Assets_MTF_v3(t) + cumulative injected
cash(t)) / units(t) -- the same construction the closed terminal figure uses.
"""
import pandas as pd, numpy as np

def brentq(f, a, b, tol=1e-12, maxiter=300):   # bisection; scipy unavailable
    fa, fb = f(a), f(b)
    for _ in range(maxiter):
        m = (a+b)/2; fm = f(m)
        if abs(fm) < tol or (b-a)/2 < tol: return m
        if (fa < 0) != (fm < 0): b, fb = m, fm
        else: a, fa = m, fm
    return (a+b)/2

U = '/root/.claude/uploads/7bd3b4cf-fc56-51a0-a6fa-0200b1bb0a88/'
reg = pd.read_csv('ma_daily_register_Task1b_v3_final.csv'); reg['Date']=pd.to_datetime(reg['Date'])
reg = reg.set_index('Date').sort_index()
NA = reg['Net_Assets_MTF_v3']

EVENTS = [('2025-09-21','Manas',1_479_670.00,'cash'),('2025-09-21','Mukesh',110_000.00,'cash'),
          ('2025-09-26','Manas',8_712.2333,'cash'),('2025-10-09','Manas',17_684.8379,'cash'),
          ('2025-12-30','Mukesh',30_000.00,'cash'),('2025-12-30','Nilesh',30_000.00,'cash'),
          ('2026-01-21','Manas',71_991.2538,'cash'),('2026-04-08','Manas',6_313.3695,'cash'),
          ('2026-06-22','Manas',18_451.51,'mintonly'),('2026-07-05','PAIR',30_000.00,'transfer')]
UNITS_PATH = [('2025-09-21',15896.700000),('2025-09-26',15987.332695),('2025-10-09',16170.708397),
              ('2025-12-30',16786.429451),('2026-01-21',17551.061476),('2026-04-08',17618.764598),
              ('2026-06-22',17795.062005)]
# terminal closed figures (fixed inputs, not recomputed)
NAV_END, NA_END, UNITS_END = 101.6600, 1_808_493.53, 17_789.627703
WEEKEND_FIN = 31_976.29 - 31_593.01

units = pd.Series(np.nan, index=reg.index)
for d,u in UNITS_PATH: units.loc[units.index[units.index>=pd.Timestamp(d)][0]] = u
units = units.ffill()
cum = pd.Series(0.0, index=reg.index)
for d,_,a,k in EVENTS:
    if k=='cash': cum.loc[cum.index>=pd.Timestamp(d)] += a
cum -= 1_589_670.00   # Day-1 capital is already inside the register's Net Assets
nav = (NA + cum)/units
nav.iloc[0] = 100.0
print(f"daily NAV path: {len(nav)} days, {nav.index.min().date()} -> {nav.index.max().date()}")
print(f"terminal check: path end {nav.iloc[-1]:.4f} (08-28) | closed 08-30 figure {NAV_END} "
      f"(delta = weekend financing Rs{WEEKEND_FIN:,.2f} / {UNITS_END:,.2f}u = {WEEKEND_FIN/UNITS_END:.4f})")

# ---- TASK 1: TWRR (daily geometric linking) --------------------------------
r = nav.pct_change().dropna()
twrr_link = float(np.prod(1+r)-1)
twrr_end = NAV_END/100.0-1
print(f"\n[1] TWRR daily-linked to 08-28: {twrr_link*100:+.4f}%  | to closed 08-30 NAV: {twrr_end*100:+.4f}%")
print("    method: daily geometric linking of unit-NAV returns. Unit accounting mints at")
print("    same-day NAV, so every capital event is NAV-neutral by construction -> no")
print("    flow distortion to remove; linked product equals the NAV ratio.")

# ---- TASK 2: MWRR (XIRR) ---------------------------------------------------
flows = [(pd.Timestamp(d), -a) for d,_,a,k in EVENTS if k=='cash']
flows.append((pd.Timestamp('2026-08-30'), NA_END))
def xnpv(rate, fl):
    t0 = fl[0][0]
    return sum(cf/(1+rate)**((t-t0).days/365.0) for t,cf in fl)
mwrr = brentq(lambda x: xnpv(x, sorted(flows)), -0.99, 10.0)
yrs = (pd.Timestamp('2026-08-30')-pd.Timestamp('2025-09-21')).days/365.0
twrr_ann = (1+twrr_end)**(1/yrs)-1
print(f"\n[2] MWRR (XIRR, annualised): {mwrr*100:+.4f}%")
print(f"    TWRR annualised for comparison: {twrr_ann*100:+.4f}%  | gap {(mwrr-twrr_ann)*100:+.4f}pp")
print(f"    gap sign: {'flows timed favourably' if mwrr>twrr_ann else 'flows timed unfavourably'} "
      f"(capital added before weak stretches drags MWRR below TWRR)")

# ---- TASK 3 (MA leg only; benchmarks blocked) ------------------------------
def period(start):
    s = nav[nav.index>=pd.Timestamp(start)]
    base = nav[nav.index<pd.Timestamp(start)]
    b = float(base.iloc[-1]) if len(base) else 100.0
    return (NAV_END/b-1)*100
print(f"\n[3] period TWRR (MA leg): SI {period('2025-09-21'):+.2f}% | "
      f"CYTD {period('2026-01-01'):+.2f}% | FYTD {period('2026-04-01'):+.2f}%")

# ---- TASK 8: risk metrics --------------------------------------------------
ann_vol = float(r.std()*np.sqrt(252))
RF = 0.0650
sharpe = (twrr_ann-RF)/ann_vol
dd = nav/nav.cummax()-1; mdd = float(dd.min()); mdd_d = dd.idxmin()
calmar = twrr_ann/abs(mdd)
print(f"\n[8] ann. vol {ann_vol*100:.2f}% | Sharpe {sharpe:.3f} (Rf {RF*100:.2f}%, 364-day T-bill assumption)")
print(f"    max drawdown {mdd*100:.2f}% on {mdd_d.date()} | Calmar {calmar:.3f}")
nav.to_frame('NAV').to_csv('ma_daily_nav_unified.csv')
