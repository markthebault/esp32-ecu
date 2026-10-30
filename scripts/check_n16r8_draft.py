#!/usr/bin/env python3
"""Source comparison only, not a replacement for native KiCad or fit checks."""
import hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
a=(R/'hardware/a3-compact/esp32-ecu.kicad_pcb').read_text();b=(R/'hardware/a4-n16r8/esp32-ecu.kicad_pcb').read_text()
def blocks(text,kind):
 result=[]
 for match in re.finditer(r'\('+kind+r'(?=\s)',text):
  start=match.start();depth=0;quoted=False;escape=False
  for i in range(start,len(text)):
   ch=text[i]
   if quoted:
    if escape:escape=False
    elif ch=='\\':escape=True
    elif ch=='"':quoted=False
   elif ch=='"':quoted=True
   elif ch=='(':depth+=1
   elif ch==')':
    depth-=1
    if not depth:result.append(text[start:i+1]);break
 return result
counts={}
for kind in ['pad','segment','arc','via','zone']:
 left=blocks(a,kind);right=blocks(b,kind);assert left==right,kind+' unexpectedly changed';counts[kind]=len(left)
c=json.loads((R/'hardware/a4-n16r8/net_contract.json').read_text());old=json.loads((R/'hardware/a3-compact/net_contract.json').read_text())
assert c['gpio']==old['gpio']
for p,q in zip(c['parts'],old['parts']):assert p['ref']==q['ref'] and p['pins']==q['pins']
assert c['selected_module']['antenna_extension_from_first_header_mm']==10
assert 'esp32-s3-n16r8-provisional.stl' in b
pdf=R/'hardware/references/esp32-s3-44pin-aliexpress.pdf'
result=dict(check='source-only comparison',unchanged_electrical_objects=counts,unchanged_gpio_and_pin_contract=True,reference_pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),native_a4_erc_drc_run=False,physical_fit_tested=False,radio_range_tested=False,manufacturing_release=False)
(R/'reports/espnow/module-source-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
