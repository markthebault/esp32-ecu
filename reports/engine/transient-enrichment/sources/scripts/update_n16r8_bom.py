#!/usr/bin/env python3
"""Derive provisional N16R8 purchasing CSVs without changing historical A3."""
import csv,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'hardware/a4-n16r8';c=json.loads((O/'net_contract.json').read_text());u=next(p for p in c['parts'] if p['ref']=='U3')
for name in ['bom.csv','bom-shopping.csv']:
 with (R/'hardware/a3-compact'/name).open() as f:
  reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
 for row in rows:
  for key,value in row.items():
   assert key is not None
   row[key]=value.replace('ESP32-S3-DevKitC-1-N8R8',u['value']).replace('A3-120','A4-N16R8 provisional').replace('Use manufacturing/a3 and native KiCad project','HOLD: no A4 fabrication release; module fit/RF checks pending').replace('Exact 44-pin DevKitC-1 v1.1 / N8R8; two 22-pin rows 22.86 mm apart.','Selected N16R8; 22.86 mm socket row spacing is provisional and unmeasured.')
  if row.get('References / use')=='U3':row['MPN / specification']=u['mpn'];row['Selection status']='Selected module; socket fit unverified'
  if row.get('Reference')=='U3':
   for k in row:
    if k.lower()=='mpn':row[k]=u['mpn']
 if name=='bom-shopping.csv':
  for qty,item,use,fit in [(1,'Separate WS2812 status module','GPIO38 / U3 pad32','3.3V-data-compatible; verify supply and decoupling'),(1,'Sealed two-button momentary pendant','J2 pins 1, 4, 5','PAIR/BOOT and RESET dry contacts; round jacketed cable and matched gland'),(1,'Sealed transparent indicator window','External status visibility','Select lens/window and adhesive for actual case; leak test required')]:
   rows.append(dict(zip(fields,['Wireless accessories',qty,0,item,'Select exact part',use,fit,'Exact part / physical fit selection required','See docs/espnow.md; not a PCB fitted reference.'])))
 with (O/name).open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
p=O/'BOM.md';s=p.read_text();note='Wireless accessories: one separate 3.3 V-data-compatible WS2812 status module, a sealed two-button pendant and matched gland, and a sealed status-light window. Exact parts and physical fit remain to be selected. These are accessory lines in `bom-shopping.csv`, not fitted PCB references. See `../../docs/espnow.md`.'
if note not in s:p.write_text(s+'\n'+note+'\n')
