"""
Dispatch 2 - MTF trade efficacy for the MA book, including converted-to-delivery.
MTF era starts 2026-04-27 (closed ruling). MTF marker: DP Id = "-".
Financing CONSUMED, not recomputed: Rs31,593.01 to 2026-08-28.
R risk = 7% of buy cost (every lot here is post-2026-04-01).
MFE/MAE on daily closes (no intraday data supplied).
"""
import importlib.util, pandas as pd, numpy as np
U='/root/.claude/uploads/7bd3b4cf-fc56-51a0-a6fa-0200b1bb0a88/'
spec=importlib.util.spec_from_file_location('ca',U+'d71b60ee-ca_register.py')
ca=importlib.util.module_from_spec(spec); spec.loader.exec_module(ca)
EXCL={'ICIBAN','VARBEV','HERHON','MAHMAH','NATSEC','SKYAIR'}
ERA,END=pd.Timestamp('2026-04-27'),pd.Timestamp('2026-08-28')
FIN_TOTAL=31593.01
DPCOL='DP Id - Client DP Id'

t=pd.read_excel(U+'704b6639-ICICIdirect_Trades_05092026.xlsx'); t['Date']=pd.to_datetime(t['Date'])
t=t[(t.Date>=ERA)&(t.Date<=END)&(~t.Stock.isin(EXCL))&(t.Action.isin(['Buy','Sell']))].copy()
t['ordref']=t['Order Ref.'].astype(str)
t['mtf']=t[DPCOL].astype(str).str.strip()=='-'
t=t.sort_values(['Date','ordref'])
b=pd.read_csv(U+'1816540e-bhavcopy_export_MA_universe_20250921_to_202608281.csv')
b['Date']=pd.to_datetime(b['Date']); b=b.set_index('Date').sort_index()
conv=pd.read_excel(U+'aee8d1a8-MTF_converted_to_delivery.xlsx')
conv['D']=pd.to_datetime(conv['Date']).dt.normalize()
cw=conv[(conv.D>=ERA)&(conv.D<=END)]
camul={}
for dd,s,typ,v,*_ in ca.CA_REGISTER:
    if typ in ('SPLIT','BONUS_PROP'): camul.setdefault(s,[]).append((pd.Timestamp(dd),float(v)))

conv_q={}
for _,r in cw.iterrows(): conv_q.setdefault((r['Stock'],r['D']),0.0); conv_q[(r['Stock'],r['D'])]+=float(r['Converted Qty'])
done=set()
lots={}; closed=[]

def convert(s,d):
    for (cs,cd),q in list(conv_q.items()):
        if cs!=s or cd>d or (cs,cd) in done: continue
        rem=q; out=[]
        for L in lots.get(s,[]):
            if L['fund']=='MTF' and rem>1e-9:
                tk=min(rem,L['q'])
                if tk>=L['q']-1e-9:
                    L['fund']='CONV'; L['conv']=cd; rem-=L['q']; out.append(L)
                else:
                    nl=dict(L); nl['q']=tk; nl['fund']='CONV'; nl['conv']=cd
                    L['q']-=tk; out.append(nl); out.append(L); rem-=tk
            else: out.append(L)
        lots[s]=out; done.add((cs,cd))

for _,r in t.iterrows():
    s,d,q=r['Stock'],r['Date'],float(r['Qty'])
    for cd,m in camul.get(s,[]):
        for L in lots.get(s,[]):
            if L['open']<cd<=d: L['q']*=m; L['px']/=m; L['open']=cd
    convert(s,d)
    if r['Action']=='Buy':
        cost=float(r['Trade Value'])+float(r['Brokerage incl. taxes'])
        lots.setdefault(s,[]).append({'q':q,'px':cost/q,'open':d,'fund':'MTF' if r['mtf'] else 'CNC','conv':None})
    else:
        pps=(float(r['Trade Value'])-float(r['Brokerage incl. taxes']))/q
        rem=q; L=lots.get(s,[])
        while rem>1e-9 and L:
            tk=min(rem,L[0]['q']); e=L[0]; en=e['px']
            px=b[s].loc[(b.index>=e['open'])&(b.index<=d)] if s in b.columns else pd.Series(dtype=float)
            mtfd=((e['conv'] if e['conv'] is not None else d)-e['open']).days if e['fund']!='CNC' else 0
            closed.append(dict(sym=s,fund=e['fund'],entry=e['open'],exit=d,
                conv=e['conv'],qty=tk,entry_px=en,exit_px=pps,cost=en*tk,
                pnl=(pps-en)*tk,ret_pct=(pps/en-1)*100,R=(pps-en)/(en*0.07),
                mfe_pct=float((px.max()/en-1)*100) if len(px) else np.nan,
                mae_pct=float((px.min()/en-1)*100) if len(px) else np.nan,
                hold=(d-e['open']).days,mtf_days=mtfd,state='closed'))
            e['q']-=tk; rem-=tk
            if e['q']<=1e-9: L.pop(0)
        lots[s]=L

openrows=[]
for s,L in lots.items():
    for e in L:
        if e['q']>1e-9 and s in b.columns:
            last=float(b[s].dropna().iloc[-1]); en=e['px']
            px=b[s].loc[b.index>=e['open']]
            mtfd=((e['conv'] if e['conv'] is not None else END)-e['open']).days if e['fund']!='CNC' else 0
            openrows.append(dict(sym=s,fund=e['fund'],entry=e['open'],exit=pd.NaT,conv=e['conv'],
                qty=e['q'],entry_px=en,exit_px=last,cost=en*e['q'],pnl=(last-en)*e['q'],
                ret_pct=(last/en-1)*100,R=(last-en)/(en*0.07),
                mfe_pct=float((px.max()/en-1)*100) if len(px) else np.nan,
                mae_pct=float((px.min()/en-1)*100) if len(px) else np.nan,
                hold=(END-e['open']).days,mtf_days=mtfd,state='open'))

a=pd.DataFrame(closed+openrows)
a['rd']=a['cost']*a['mtf_days']
a['fin']=a['rd']/a['rd'].sum()*FIN_TOTAL
a['pnl_net']=a['pnl']-a['fin']
a['R_net']=a['R']-a['fin']/(a['entry_px']*0.07*a['qty'])
a.to_csv('mtf_legs.csv',index=False)
c=a[a.state=='closed']; o=a[a.state=='open']
print(f"MTF era {ERA.date()}..{END.date()} | trades {len(t)} (MTF-marked {int(t.mtf.sum())}, CNC {int((~t.mtf).sum())})")
print(f"conversion events in window: {len(cw)} of {len(conv)} | applied {len(done)}")
print(f"legs: closed {len(c)}, open {len(o)}\n")
print("[2/3] CLOSED LEGS BY FUNDING (gross, before financing)")
print(f"{'basis':<32}{'n':>5}{'win%':>8}{'meanR':>9}{'medR':>9}{'P&L':>14}{'MFE%':>9}{'MAE%':>9}")
for lab,f in [('MTF, never converted','MTF'),('MTF -> converted to delivery','CONV'),('CNC (cash), same period','CNC')]:
    d=c[c.fund==f]
    if len(d): print(f"{lab:<32}{len(d):>5}{(d.pnl>0).mean()*100:>7.1f}%{d.R.mean():>9.3f}{d.R.median():>9.3f}{d.pnl.sum():>14,.2f}{d.mfe_pct.mean():>9.2f}{d.mae_pct.mean():>9.2f}")
    else: print(f"{lab:<32}{0:>5}")

print(f"\n[5] FINANCING DRAG (allocated by MTF rupee-days; total Rs{FIN_TOTAL:,.2f} consumed, not recomputed)")
print(f"{'basis':<32}{'n':>5}{'gross P&L':>14}{'financing':>12}{'net P&L':>14}{'drag % of gross':>17}")
for lab,f in [('MTF, never converted','MTF'),('MTF -> converted','CONV'),('CNC (cash)','CNC')]:
    d=c[c.fund==f]
    if not len(d): continue
    dg=d.fin.sum()/abs(d.pnl.sum())*100 if d.pnl.sum() else float('nan')
    print(f"{lab:<32}{len(d):>5}{d.pnl.sum():>14,.2f}{d.fin.sum():>12,.2f}{d.pnl_net.sum():>14,.2f}{dg:>16.1f}%")
dm=c[c.fund.isin(['MTF','CONV'])]
print(f"{'ALL MTF-funded closed':<32}{len(dm):>5}{dm.pnl.sum():>14,.2f}{dm.fin.sum():>12,.2f}{dm.pnl_net.sum():>14,.2f}"
      f"{dm.fin.sum()/abs(dm.pnl.sum())*100:>16.1f}%")
om=o[o.fund.isin(['MTF','CONV'])]
print(f"open MTF-funded legs carry a further Rs{om.fin.sum():,.2f} financing on Rs{om.pnl.sum():,.2f} unrealised")
print(f"financing allocated to closed legs Rs{c.fin.sum():,.2f} + open Rs{o.fin.sum():,.2f} = Rs{a.fin.sum():,.2f} (ties to total)")

print(f"\n[4] MTF vs CNC - THE EFFICACY QUESTION (closed legs, net of financing)")
print(f"{'basis':<32}{'n':>5}{'win%':>8}{'meanR gross':>13}{'meanR net':>12}{'net P&L':>14}{'net P&L/leg':>13}")
for lab,d in [('MTF-funded (incl. converted)',dm),('CNC (cash)',c[c.fund=='CNC'])]:
    print(f"{lab:<32}{len(d):>5}{(d.pnl>0).mean()*100:>7.1f}%{d.R.mean():>13.3f}{d.R_net.mean():>12.3f}"
          f"{d.pnl_net.sum():>14,.2f}{d.pnl_net.mean():>13.2f}")

print(f"\n[3] CONVERSION BEHAVIOUR - split-phase (n={len(cw)} in-window events, {len(conv)-len(cw)} pre-date the MTF era)")
cv=a[a.fund=='CONV'].copy()
if len(cv):
    cv['mtf_ret']=np.nan
    for i,r in cv.iterrows():
        if r['sym'] in b.columns and r['conv'] is not None:
            p=b[r['sym']].loc[(b.index>=r['entry'])&(b.index<=r['conv'])]
            if len(p): cv.at[i,'mtf_ret']=(float(p.iloc[-1])/r['entry_px']-1)*100
    cv['cnc_ret']=cv['ret_pct']-cv['mtf_ret']
    print(f"  legs touched by conversion: {len(cv)} (closed {len(cv[cv.state=='closed'])}, open {len(cv[cv.state=='open'])})")
    print(f"  MTF phase (entry->conversion) mean return {cv.mtf_ret.mean():+.2f}%, median {cv.mtf_ret.median():+.2f}%, "
          f"{(cv.mtf_ret>0).sum()}/{cv.mtf_ret.notna().sum()} in profit at conversion")
    print(f"  CNC phase (conversion->exit/mark) mean {cv.cnc_ret.mean():+.2f}%, median {cv.cnc_ret.median():+.2f}%")
    print(f"  blended whole-trade mean R {cv.R.mean():+.3f} | net of financing {cv.R_net.mean():+.3f}")
    print("\n  per conversion leg:")
    print(f"  {'sym':<12}{'entry':<12}{'conv':<12}{'exit':<12}{'MTF%':>8}{'CNC%':>8}{'R':>8}{'R_net':>8}")
    for _,r in cv.sort_values('entry').iterrows():
        ex=str(r['exit'])[:10] if pd.notna(r['exit']) else 'open'
        print(f"  {r['sym']:<12}{str(r['entry'])[:10]:<12}{str(r['conv'])[:10]:<12}{ex:<12}"
              f"{r['mtf_ret']:>8.2f}{r['cnc_ret']:>8.2f}{r['R']:>8.3f}{r['R_net']:>8.3f}")
