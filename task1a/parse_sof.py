"""
Parse ICICI weekly SOF (Statement of Accounts for Funds) PDFs into:
  * daily MTF loan balance   (Exchange Segment: MTF-MTF-TRADE, running 'Balance' col)
  * daily SOF-billed interest (JE rows 'Interest on NSE MTF <id>')
  * daily pledge charges      (DBNOTE rows labelled 'Being MTF pledge Charges')
LAYOUT NOTE: in the extracted text the particulars label sits on the line BEFORE
the amount row it belongs to, so labels are carried forward one line.
PLEDGE BASIS: project standing rule DN = SOF x 1.18 (DebitNote_VERIFIED).
  Corroborated in-file: a 225.00 pledge debit is mirrored by a 265.50
  'GST and MTF pledge Charges recovered' credit = 225.00 x 1.18 exactly.
"""
import re, glob
from pathlib import Path
import pandas as pd

TXT = Path('/home/user/Scratch-2/task1a/sof_txt')
AMT = r'([\d,]+\.\d{2})'
ROW = re.compile(r'^(\d{2}/\d{2}/\d{4})\s+(\d{2}-\d{2}-\d{2})\s+(.*?)' + AMT + r'\s+' + AMT
                 + r'\s+' + AMT + r'\s*(DR|CR)?\s*$')
num = lambda s: float(s.replace(',', ''))

bal_rows, chg_rows = [], []
for f in sorted(TXT.glob('*.txt')):
    seg, prev = None, ''
    for line in f.read_text().splitlines():
        s = line.strip()
        if s.startswith('Exchange Segment:'):
            seg = s.split(':', 1)[1].strip(); prev = s; continue
        m = ROW.match(s)
        if not m:
            prev = s; continue
        d, _, mid, dr, cr, bal, sfx = m.groups()
        d = pd.to_datetime(d, format='%d/%m/%Y').date()
        label = (prev + ' ' + mid).lower()
        if seg == 'MTF-MTF-TRADE':
            bal_rows.append(dict(date=d, debit=num(dr), credit=num(cr),
                                 balance=num(bal), sfx=sfx or '', src=f.name))
        if 'interest on nse mtf' in label and num(dr) > 0:
            chg_rows.append(dict(date=d, kind='interest', amt=num(dr), src=f.name, ref=mid.strip()))
        elif 'being mtf pledge charges' in label and 'recovered' not in label and num(dr) > 0:
            chg_rows.append(dict(date=d, kind='pledge_sof', amt=num(dr), src=f.name, ref=mid.strip()))
        prev = s

bal = pd.DataFrame(bal_rows)
# last row per date within a statement = that day's closing MTF balance
# Consecutive weekly statements overlap. A date can therefore appear in two
# files, and a file that only PARTIALLY covers that date (statement cut-off) has
# fewer rows for it. Resolve per date by taking the ONE statement with the most
# rows for that date (ties -> the later statement), never a blend: mixing two
# files' rows for the same day double-counts debits and breaks reconstruction.
bal['stmt'] = bal['src'].str.extract(r'_(\d{8})_')[0]
pick = (bal.groupby(['date', 'stmt']).size().rename('n').reset_index()
          .sort_values(['date', 'n', 'stmt']).groupby('date').tail(1)[['date', 'stmt']])
bal = bal.merge(pick, on=['date', 'stmt'])
eod = bal.groupby('date').tail(1).set_index('date')['balance'].sort_index()
grs = bal.groupby('date')[['debit', 'credit']].sum().rename(
        columns={'debit': 'draw', 'credit': 'repay'})
chg = pd.DataFrame(chg_rows).drop_duplicates(subset=['date', 'kind', 'amt', 'ref'])
piv = chg.pivot_table(index='date', columns='kind', values='amt', aggfunc='sum').fillna(0.0)
for c in ('interest', 'pledge_sof'):
    if c not in piv: piv[c] = 0.0
piv['pledge_dn'] = (piv['pledge_sof'] * 1.18).round(2)
out = pd.concat([eod.rename('mtf_balance'), grs, piv], axis=1).sort_index()
out.to_csv('/home/user/Scratch-2/task1a/sof_extract.csv')
print(f"dates {out.index.min()} .. {out.index.max()}  ({len(out)} rows)")
print(out.to_string())
print("\nTOTALS  interest %.2f | pledge SOF %.2f | pledge DN %.2f"
      % (out.interest.sum(), out.pledge_sof.sum(), out.pledge_dn.sum()))
