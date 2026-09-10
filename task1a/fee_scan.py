"""
Fee-completeness scan: enumerate EVERY distinct particulars label across ALL
segments of all 10 source SOF documents (9 weeklies + the Apr-Jun quarterly),
reconcile my own extraction against each statement's own totals/running
balance, and classify every label into: counted (interest+pledge), clearly
non-MTF, or ambiguous (left for a ruling).

Nothing here decides scope. It only measures what is in the source documents.
"""
import re, glob
from pathlib import Path
from collections import defaultdict
import pandas as pd

TXT = Path('/home/user/Scratch-2/task1a/sof_txt')
AMT = r'([\d,]+\.\d{2})'
ROW = re.compile(r'^(\d{2}/\d{2}/\d{4})\s+(\d{2}-\d{2}-\d{2})\s+(.*?)' + AMT + r'\s+' + AMT
                 + r'\s+' + AMT + r'\s*(DR|CR)?\s*$')
OPEN_RE = re.compile(r'OPENING BALANCE\s+' + AMT + r'\s*(DR|CR)?')
CLOSE_RE = re.compile(r'CLOSING BALANCE\s+' + AMT + r'\s*(DR|CR)?')
TOTAL_RE = re.compile(r'^Total\s*:\s*' + AMT + r'\s+' + AMT)
SEG_RE = re.compile(r'^Exchange Segment:\s*(.+)$')
BOILERPLATE = ('Transaction Bill', 'Settlement Settlement', 'Date Cheque',
               'Date No No', 'No', 'Page ', 'Following is', 'Statement of Account',
               'Net Balance', 'Notes:', 'This is a computer', '1. In case',
               '2. Client needs', '3. If you have')
num = lambda s: float(s.replace(',', ''))

def sign(bal, sfx):  # CR positive, DR negative
    return bal if sfx == 'CR' else -bal

files = sorted(TXT.glob('*.txt'))
all_rows, blocks, recon, continuity = [], [], [], []

for f in files:
    lines = f.read_text().splitlines()
    seg, cur_open, cur_open_sfx, cur_rows, prev = None, None, None, [], ''
    signed_bal = None
    stop = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('Pending Obligations'):
            stop = True
        if stop:
            continue
        m = SEG_RE.match(s)
        if m:
            seg = m.group(1).strip(); cur_open = cur_open_sfx = None; cur_rows = []; signed_bal = None
            prev = s; continue
        mo = OPEN_RE.search(s)
        if mo and 'CLOSING' not in s:
            cur_open = num(mo.group(1)); cur_open_sfx = mo.group(2) or 'CR'
            signed_bal = sign(cur_open, cur_open_sfx)
            prev = s; continue
        mt = TOTAL_RE.match(s)
        if mt:
            td, tc = num(mt.group(1)), num(mt.group(2))
            sum_d = sum(r['debit'] for r in cur_rows)
            sum_c = sum(r['credit'] for r in cur_rows)
            recon.append(dict(file=f.name, segment=seg, n_rows=len(cur_rows),
                              stated_total_debit=td, stated_total_credit=tc,
                              parsed_total_debit=round(sum_d, 2), parsed_total_credit=round(sum_c, 2),
                              delta_debit=round(sum_d - td, 2), delta_credit=round(sum_c - tc, 2)))
            blocks.append(dict(file=f.name, segment=seg, opening=cur_open, opening_sfx=cur_open_sfx,
                               rows=list(cur_rows)))
            seg = None; prev = s; continue
        mc = CLOSE_RE.search(s)
        # CLOSING BALANCE rows never carry 3 amounts, so ROW won't match them; skip separately
        m2 = ROW.match(s)
        if m2 and 'CLOSING BALANCE' not in s and 'OPENING BALANCE' not in s:
            d, _, mid, dr, cr, bal, sfx = m2.groups()
            debit, credit, bal_v = num(dr), num(cr), num(bal)
            sfx = sfx or 'CR'
            cont = prev if not (prev.startswith(BOILERPLATE) or SEG_RE.match(prev)
                                or TOTAL_RE.match(prev) or OPEN_RE.search(prev)) else ''
            raw_label = (cont + ' ' + mid).strip()
            if signed_bal is not None:
                exp = signed_bal + credit - debit
                stated_signed = sign(bal_v, sfx)
                delta = round(exp - stated_signed, 2)
                if abs(delta) > 0.02:
                    continuity.append(dict(file=f.name, segment=seg, date=d, label=raw_label[:70],
                                           prior_signed=round(signed_bal, 2), debit=debit, credit=credit,
                                           expected_signed=round(exp, 2), stated_signed=stated_signed,
                                           delta=delta))
                signed_bal = stated_signed  # resync so one break doesn't cascade into every later row
            row = dict(file=f.name, segment=seg, date=d, raw_label=raw_label,
                      debit=debit, credit=credit, balance=bal_v, sfx=sfx)
            cur_rows.append(row); all_rows.append(row)
            prev = s; continue
        if s.startswith(BOILERPLATE):
            prev = s; continue
        prev = s  # ordinary continuation text carried to next data row

df = pd.DataFrame(all_rows)
df.to_csv('fee_scan_all_rows.csv', index=False)
recon_df = pd.DataFrame(recon)
recon_df.to_csv('fee_scan_reconciliation.csv', index=False)
cont_df = pd.DataFrame(continuity)
cont_df.to_csv('fee_scan_continuity_breaks.csv', index=False)

def norm(text):
    s = text
    s = re.sub(r'\b8503169324\b', '', s)
    s = re.sub(r'\bSETTNO=\S+', '', s)
    s = re.sub(r'\bINN\s*\d+\b', 'INN <ID>', s)
    s = re.sub(r'\b\d+\.(?=[A-Za-z])', '', s)
    s = re.sub(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(,)?\s*2026\b', '', s)
    s = re.sub(r'\b\d{5,}\b', '', s)
    s = re.sub(r'-M\b', '', s)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    return s

df['label'] = df['raw_label'].apply(norm)
grp = (df.groupby(['segment', 'label'])
         .agg(n=('debit', 'size'), total_debit=('debit', 'sum'), total_credit=('credit', 'sum'),
              date_min=('date', 'min'), date_max=('date', 'max'))
         .reset_index().sort_values('total_debit', ascending=False))
grp.to_csv('fee_scan_labels.csv', index=False)

print(f"Parsed {len(df)} detail rows across {df['file'].nunique()} files, "
      f"{df['segment'].nunique()} distinct segments, {len(grp)} distinct (segment,label) groups")
print(f"\n=== RECONCILIATION: parsed sum vs statement's own 'Total :' line, per segment block ===")
bad = recon_df[(recon_df['delta_debit'].abs() > 0.02) | (recon_df['delta_credit'].abs() > 0.02)]
print(f"Blocks checked: {len(recon_df)} | Blocks with a mismatch >Rs0.02: {len(bad)}")
if len(bad): print(bad.to_string(index=False))
else: print("ZERO mismatches. Every segment block's parsed debit/credit sum equals the statement's own printed Total line, in every one of the 10 documents.")

print(f"\n=== PER-ROW RUNNING-BALANCE CONTINUITY CHECK (opening -> row1 -> row2 -> ... vs each row's own stated balance) ===")
total_data_rows = len(df)
print(f"Rows checked: {total_data_rows} | continuity breaks (>Rs0.02, i.e. a row's stated balance doesn't "
      f"follow from the prior row's stated balance + this row's own debit/credit): {len(cont_df)}")
if len(cont_df):
    print(cont_df.to_string(index=False))
else:
    print("ZERO continuity breaks. Every one of the " + str(total_data_rows) + " parsed transaction rows, "
          "across all 10 documents and both active segments, reconstructs the exact next stated running "
          "balance from the prior row's stated balance plus its own debit/credit. This means my ROW regex "
          "did not silently skip or misparse any transaction line with a non-zero debit or credit anywhere "
          "in MTF-MTF-TRADE or NSE-CAPITAL across the full window.")
print(f"\n=== TOP LABELS BY TOTAL DEBIT (all segments) ===")
print(grp.head(40).to_string(index=False))
