"""
Whole-account EQUITY v2 extension, 2026-07-10 -> 2026-08-30.
Replicates managed_account_colab.py Cell 4 (holdings replay) + Cell 6 (V_stocks)
+ Cell 8b (EQUITY v2 NAV) as closely as the inputs available in THIS session allow.

Engine logic quoted/mirrored:
  Cell 4:  q += trade qty ; SPLIT/BONUS_PROP q*=v ; BONUS_ABS q+=v ; FORCE_CLOSE q=0
           series reindexed to a DAILY calendar, ffill, .clip(lower=0)
  Cell 6:  V_stocks = sum over symbols of qty * ffilled close, skipping
           EXCLUDE_MANAGED {ICIBAN,VARBEV,HERHON,MAHMAH} and EXCLUDE_PRICE {EQUHOL}
  Cell 8b: ce += flow + dloan ; npre=(V+ce-ln-fn)/units ; u=amt/npre ; NAV=(V+ce-ln-fn)/units
"""
import importlib.util
from pathlib import Path
import pandas as pd, numpy as np

U = Path('/root/.claude/uploads/7bd3b4cf-fc56-51a0-a6fa-0200b1bb0a88')
spec = importlib.util.spec_from_file_location('ca', U/'d71b60ee-ca_register.py')
ca = importlib.util.module_from_spec(spec); spec.loader.exec_module(ca)

EXCLUDE_MANAGED = {"ICIBAN","VARBEV","HERHON","MAHMAH"}
EXCLUDE_PRICE   = {"EQUHOL"}

tb = pd.read_excel(U/'704b6639-ICICIdirect_Trades_05092026.xlsx', parse_dates=['Date'])
tb = tb[tb['Action'].isin(['Buy','Sell'])].copy(); tb['Date']=tb['Date'].dt.normalize()
tb['qd'] = np.where(tb['Action']=='Buy', tb['Qty'], -tb['Qty'])
tev = tb[['Date','Stock','qd']].rename(columns={'Date':'date','Stock':'sym','qd':'q'})
syn = [{'date':pd.Timestamp(d),'sym':s,'q':v} for d,s,t,v,*_ in ca.CA_REGISTER if t=='SYNTHETIC_BUY']
allev = pd.concat([tev, pd.DataFrame(syn)], ignore_index=True)
allev['date'] = pd.to_datetime(allev['date']).dt.normalize()
caby={}
for d,s,t,v,*_ in ca.CA_REGISTER:
    if t in ('SPLIT','BONUS_PROP','BONUS_ABS','FORCE_CLOSE'): caby.setdefault(s,[]).append((pd.Timestamp(d),t,v))

END = pd.Timestamp('2026-08-30')
FULL = pd.date_range(allev['date'].min(), END, freq='D')
hold={}
for s in allev['sym'].dropna().unique():
    se = allev[allev['sym']==s]
    tl = [(r['date'],0,'T',r['q']) for _,r in se.iterrows()] + [(d,1,t,v) for d,t,v in caby.get(s,[])]
    tl.sort(key=lambda x:(x[0],x[1])); q=0.0; cp={}
    for d,_,t,v in tl:
        if t in ('T','BONUS_ABS'): q+=float(v)
        elif t in ('SPLIT','BONUS_PROP'): q*=float(v)
        elif t=='FORCE_CLOSE': q=0.0
        cp[d]=round(q,6)
    ss=pd.Series(cp); ss.index=pd.to_datetime(ss.index)
    hold[s]=ss.reindex(FULL).ffill().fillna(0).clip(lower=0)
H = pd.DataFrame(hold)

b = pd.read_csv(U/'1816540e-bhavcopy_export_MA_universe_20250921_to_202608281.csv')
b['Date']=pd.to_datetime(b['Date']); b=b.set_index('Date').sort_index()
bf = b.reindex(FULL).ffill()          # engine ffills prices on a DAILY calendar

days = pd.date_range('2026-07-10', END, freq='D')
priced, unpriced = {}, []
for s in H.columns:
    if s in EXCLUDE_MANAGED or s in EXCLUDE_PRICE: continue
    if s in bf.columns: priced[s] = (H[s]*bf[s]).reindex(days).fillna(0.0)
    else:
        q = float(H[s].reindex(days).iloc[0])
        if q > 0: unpriced.append((s, q))
V = pd.DataFrame(priced).sum(axis=1)

print(f"Engine's own V_stocks at 2026-07-10 : 2,166,470.15")
print(f"This reconstruction at 2026-07-10   : {V.loc['2026-07-10']:,.2f}")
print(f"delta                               : {V.loc['2026-07-10']-2166470.15:,.2f}\n")
print(f"Held-but-unpriceable symbols at 07-10 ({len(unpriced)}): "
      f"{', '.join(f'{s}x{q:g}' for s,q in sorted(unpriced))}")

# ============================================================
# EXTENSION 2026-07-10 -> 2026-08-30, continuity basis
# Baseline held exactly at the engine's own published 2026-07-10 state.
# ============================================================
BASE = pd.Timestamp('2026-07-10')
base_V, base_cash, base_loan_engine, base_fin_engine = 2166470.15, 253494.60, 618861.69, 15266.62
base_units = 17803.574958
# Jul-05 Nilesh/Manas pair (net-zero: secondary transfer, fund cash unchanged, units reallocated)
u_pair = 30000.0/100.349567
MANAS, MUKESH, NILESH = 16087.37-u_pair, 1408.10, 308.1+u_pair

# trade flows (engine Cell 7 convention), excluding the 4 managed names
ta = tb[(tb['Date']>BASE)&(tb['Date']<=END)&(~tb['Stock'].isin(EXCLUDE_MANAGED))].copy()
ta['nb'] = (ta['Trade Value']+ta['Brokerage incl. taxes']).where(ta['Action']=='Buy',0.0)
ta['ns'] = (ta['Trade Value']-ta['Brokerage incl. taxes']).where(ta['Action']=='Sell',0.0)
flow = (ta.groupby('Date')['ns'].sum()-ta.groupby('Date')['nb'].sum()).reindex(days).fillna(0.0)
four_win = tb[(tb['Date']>BASE)&(tb['Date']<=END)&(tb['Stock'].isin(EXCLUDE_MANAGED))&(tb['Action']=='Sell')]
print(f"\n4-name (Manas-injection) sales in window: {len(four_win)}  -> no new injections")

led = pd.read_excel('MTF_Loan_Ledger_extended.xlsx','DAILY_LEDGER')
led['date']=pd.to_datetime(led['date']); led=led.set_index('date').sort_index()
def loan_new(dt):
    s = led['balance'][led.index<=dt]; return float(s.iloc[-1]) if len(s) else 0.0
def fin_new(dt):
    s = led[led.index<=dt]
    return float(np.nan_to_num(s['interest_sof_billed']).sum()+np.nan_to_num(s['pledge_dn']).sum())

dloan_total = loan_new(END)-loan_new(BASE)
dfin_total  = fin_new(END)-fin_new(BASE)
flow_total  = float(flow.sum())
print(f"\nwindow deltas: flow {flow_total:,.2f} | dloan {dloan_total:,.2f} | dfin {dfin_total:,.2f}")

cash_end = base_cash + flow_total + dloan_total
loan_end = base_loan_engine + dloan_total
fin_end  = base_fin_engine + dfin_total
V_end    = float(V.loc[END])
NA_end   = V_end + cash_end - loan_end - fin_end
NAV_end  = NA_end/base_units
print(f"\n--- 2026-08-30, continuity basis ---")
print(f"V_stocks {V_end:,.2f} | cash {cash_end:,.2f} | loan {loan_end:,.2f} | fin {fin_end:,.2f}")
print(f"Net Assets {NA_end:,.2f} | units {base_units:,.6f} | NAV {NAV_end:.4f}")

# restated alternative: use the corrected SOF-exact loan level outright
loan_end_r = loan_new(END); fin_end_r = fin_new(END)
NA_r = V_end + cash_end - loan_end_r - fin_end_r; NAV_r = NA_r/base_units
print(f"\n--- alternative: corrected loan level ({loan_new(BASE):,.2f} at 07-10 vs engine's {base_loan_engine:,.2f}) ---")
print(f"Net Assets {NA_r:,.2f} | NAV {NAV_r:.4f}  (restatement effect {NAV_r-NAV_end:+.4f})")

print(f"\n--- per-contributor at 2026-08-30 (continuity basis) ---")
tot = MANAS+MUKESH+NILESH
for nm,u,entry in [('Manas',MANAS,99.7181),('Mukesh',MUKESH,99.4246),('Nilesh',NILESH,97.3701)]:
    print(f"{nm:7s} units {u:12.6f} | own% {u/tot*100:6.3f} | value {u*NAV_end:13,.2f} "
          f"| entryNAV {entry:8.4f} | return {(NAV_end/entry-1)*100:+6.2f}%")
print(f"{'TOTAL':7s} units {tot:12.6f} | own% 100.000 | value {tot*NAV_end:13,.2f}")
