"""
Dispatch 1 Task 3/4 - period returns vs Nifty 50 and NSE MidSmall 400.
Law 12: MidSmall 400 appears in every table alongside Nifty 50, never alone.
Benchmarks sourced ONLY from nse_indices.csv (NSE ind_close_all). yfinance retired.
"""
import pandas as pd, numpy as np
U='/root/.claude/uploads/7bd3b4cf-fc56-51a0-a6fa-0200b1bb0a88/'
bm=pd.read_csv(U+'1e8d5b61-nse_indices.csv'); bm['Date']=pd.to_datetime(bm['Date'])
bm=bm.set_index('Date').sort_index()
nav=pd.read_csv('ma_daily_nav_unified.csv'); nav['Date']=pd.to_datetime(nav['Date'])
nav=nav.set_index('Date')['NAV'].sort_index()
NAV_END=101.6600                      # closed 2026-08-30 figure (fixed input)
SI,END=pd.Timestamp('2025-09-21'),pd.Timestamp('2026-08-28')
win=bm.loc[(bm.index>=SI)&(bm.index<=END)]
print(f"benchmark rows in MA window: {len(win)} | {win.index.min().date()} -> {win.index.max().date()} | nulls {win.isna().sum().sum()}")

def base(series, start):
    prior=series[series.index<pd.Timestamp(start)]
    return float(prior.iloc[-1]) if len(prior) else float(series[series.index>=pd.Timestamp(start)].iloc[0])

PER=[('Since Inception','2025-09-21'),('CYTD','2026-01-01'),('FYTD','2026-04-01')]
rows=[]
for lab,st in PER:
    ma = (NAV_END/(100.0 if st=='2025-09-21' else base(nav,st))-1)*100
    n5 = (float(win['N50'].iloc[-1])/base(win['N50'],st)-1)*100
    ms = (float(win['MS400'].iloc[-1])/base(win['MS400'],st)-1)*100
    rows.append(dict(Period=lab, MA_TWRR=ma, Nifty50=n5, MidSmall400=ms,
                     Alpha_N50=ma-n5, Alpha_MS400=ma-ms))
df=pd.DataFrame(rows)
print("\n" + df.round(2).to_string(index=False))

yrs=(pd.Timestamp('2026-08-30')-SI).days/365.0
ma_ann=((1+ (NAV_END/100-1))**(1/yrs)-1)*100
n5_ann=((1+(df.Nifty50.iloc[0]/100))**(1/yrs)-1)*100
ms_ann=((1+(df.MidSmall400.iloc[0]/100))**(1/yrs)-1)*100
print(f"\nannualised (SI, {yrs:.3f}y): MA {ma_ann:+.2f}% | N50 {n5_ann:+.2f}% | MS400 {ms_ann:+.2f}%")
print(f"annualised alpha: vs N50 {ma_ann-n5_ann:+.2f}pp | vs MS400 {ma_ann-ms_ann:+.2f}pp")
df.to_csv('benchmark_periods.csv',index=False)
