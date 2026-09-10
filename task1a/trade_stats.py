"""
Dispatch 1 Tasks 5/6/7 - closed-trade statistics for the MA book.
FIFO cost basis, intraday sequencing by Order Ref. (never buys-before-sells).
R risk rate applied per the BUY lot's own date: 10% of buy cost before
2026-04-01, 7% from 2026-04-01 onward.
MFE/MAE measured on daily CLOSES (bhavcopy) between entry and exit - intraday
highs/lows are not in the supplied data, so these are close-basis excursions.
"""
import importlib.util, pandas as pd, numpy as np
U='/root/.claude/uploads/7bd3b4cf-fc56-51a0-a6fa-0200b1bb0a88/'
spec=importlib.util.spec_from_file_location('ca',U+'d71b60ee-ca_register.py')
ca=importlib.util.module_from_spec(spec); spec.loader.exec_module(ca)
EXCL={'ICIBAN','VARBEV','HERHON','MAHMAH','NATSEC','SKYAIR'}
START,END=pd.Timestamp('2025-09-21'),pd.Timestamp('2026-08-28')

t=pd.read_excel(U+'704b6639-ICICIdirect_Trades_05092026.xlsx'); t['Date']=pd.to_datetime(t['Date'])
t=t[(t.Date>=START)&(t.Date<=END)&(~t.Stock.isin(EXCL))&(t.Action.isin(['Buy','Sell']))].copy()
t['ordref']=t['Order Ref.'].astype(str)
t=t.sort_values(['Date','ordref']).reset_index(drop=True)     # Order Ref. sequencing
b=pd.read_csv(U+'1816540e-bhavcopy_export_MA_universe_20250921_to_202608281.csv')
b['Date']=pd.to_datetime(b['Date']); b=b.set_index('Date').sort_index()

camul={}
for d,s,typ,v,*_ in ca.CA_REGISTER:
    if typ in ('SPLIT','BONUS_PROP'): camul.setdefault(s,[]).append((pd.Timestamp(d),float(v)))

rate=lambda d: 0.10 if d < pd.Timestamp('2026-04-01') else 0.07
lots, closed = {}, []
for _,r in t.iterrows():
    s,d,q = r.Stock, r.Date, float(r.Qty)
    for cd,m in camul.get(s,[]):                       # CA on open lots
        for L in lots.get(s,[]):
            if L['open']<cd<=d: L['q']*=m; L['px']/=m; L['open']=cd
    if r.Action=='Buy':
        cost=float(r['Trade Value'])+float(r['Brokerage incl. taxes'])
        lots.setdefault(s,[]).append({'q':q,'px':cost/q,'open':d,'cost_ps':cost/q})
    else:
        proceeds_ps=(float(r['Trade Value'])-float(r['Brokerage incl. taxes']))/q
        rem=q; L=lots.get(s,[])
        while rem>1e-9 and L:
            take=min(rem,L[0]['q']); e=L[0]
            px=b[s].loc[(b.index>=e['open'])&(b.index<=d)] if s in b.columns else pd.Series(dtype=float)
            entry=e['cost_ps']
            mfe=float((px.max()/entry-1)*100) if len(px) else np.nan
            mae=float((px.min()/entry-1)*100) if len(px) else np.nan
            risk_ps=entry*rate(e['open'])
            closed.append(dict(sym=s,entry=e['open'],exit=d,qty=take,entry_px=entry,
                               exit_px=proceeds_ps,pnl=(proceeds_ps-entry)*take,
                               ret_pct=(proceeds_ps/entry-1)*100,
                               R=(proceeds_ps-entry)/risk_ps, rate=rate(e['open']),
                               mfe_pct=mfe,mae_pct=mae,
                               mfe_R=mfe/100*entry/risk_ps if mfe==mfe else np.nan,
                               mae_R=mae/100*entry/risk_ps if mae==mae else np.nan,
                               hold=(d-e['open']).days))
            e['q']-=take; rem-=take
            if e['q']<=1e-9: L.pop(0)
        lots[s]=L
c=pd.DataFrame(closed); c.to_csv('closed_trades.csv',index=False)
w=c[c.pnl>0]; l=c[c.pnl<=0]
print(f"closed trades: {len(c)} | symbols {c.sym.nunique()} | realised P&L Rs{c.pnl.sum():,.2f}")
print(f"\n[6] win rate {len(w)/len(c)*100:.2f}% ({len(w)}/{len(c)}) | avg win Rs{w.pnl.mean():,.2f} | "
      f"avg loss Rs{l.pnl.mean():,.2f} | payoff {abs(w.pnl.mean()/l.pnl.mean()):.3f}")
print(f"    avg win {w.ret_pct.mean():+.2f}% | avg loss {l.ret_pct.mean():+.2f}% | expectancy Rs{c.pnl.mean():,.2f}/trade")
print(f"\n[7] R: mean {c.R.mean():+.4f} | median {c.R.median():+.4f} | std {c.R.std():.4f} | "
      f"sum {c.R.sum():+.2f}")
print(f"    rate split: 10% risk n={(c.rate==0.10).sum()}, 7% risk n={(c.rate==0.07).sum()}")
bins=[-1e9,-2,-1,-0.5,0,0.5,1,2,1e9]; lab=['<-2R','-2..-1R','-1..-0.5R','-0.5..0R','0..0.5R','0.5..1R','1..2R','>2R']
print("\n    R distribution:"); 
for k,v in c.R.pipe(pd.cut,bins=bins,labels=lab).value_counts().reindex(lab).items():
    print(f"      {k:<12}{v:>4}  {v/len(c)*100:>5.1f}%")
hb=[-1,1,7,30,90,180,1e9]; hl=['0-1d','2-7d','8-30d','31-90d','91-180d','>180d']
c['bucket']=pd.cut(c.hold,bins=hb,labels=hl)
g=c.groupby('bucket',observed=True).agg(n=('R','size'),meanR=('R','mean'),medR=('R','median'),
      win=('pnl',lambda x:(x>0).mean()*100),pnl=('pnl','sum'))
print("\n    R by holding-period bucket:"); print(g.round(3).to_string())
print(f"\n[5] MFE/MAE (close-basis, n={c.mfe_pct.notna().sum()}):")
print(f"    MFE%: mean {c.mfe_pct.mean():+.2f} median {c.mfe_pct.median():+.2f} | "
      f"MFE R: mean {c.mfe_R.mean():+.3f} median {c.mfe_R.median():+.3f}")
print(f"    MAE%: mean {c.mae_pct.mean():+.2f} median {c.mae_pct.median():+.2f} | "
      f"MAE R: mean {c.mae_R.mean():+.3f} median {c.mae_R.median():+.3f}")
mb=[-1e9,-20,-10,-5,-2,0,1e9]; ml=['<-20%','-20..-10%','-10..-5%','-5..-2%','-2..0%','>=0%']
print("\n    MAE distribution:")
for k,v in c.mae_pct.pipe(pd.cut,bins=mb,labels=ml).value_counts().reindex(ml).items():
    print(f"      {k:<12}{v:>4}  {v/len(c)*100:>5.1f}%")
fb=[-1e9,0,2,5,10,20,1e9]; fl=['<=0%','0-2%','2-5%','5-10%','10-20%','>20%']
print("\n    MFE distribution:")
for k,v in c.mfe_pct.pipe(pd.cut,bins=fb,labels=fl).value_counts().reindex(fl).items():
    print(f"      {k:<12}{v:>4}  {v/len(c)*100:>5.1f}%")
