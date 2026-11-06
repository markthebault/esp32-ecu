"""Keep local and cached KiCad symbol defaults consistent with the compact contract."""
from pathlib import Path
from dataclasses import fields
import json
from design import Part
import build_hardware as gen
R=Path(__file__).resolve().parents[1];O=R/'hardware/a3-compact';c=json.loads((O/'net_contract.json').read_text());names={f.name for f in fields(Part)};parts=[Part(**{k:v for k,v in d.items() if k in names}) for d in c['parts'] if d['pins']]
def end_block(text,start):
 depth=0;quoted=False;escaped=False
 for i in range(start,len(text)):
  ch=text[i]
  if quoted:
   if escaped:escaped=False
   elif ch=='\\':escaped=True
   elif ch=='"':quoted=False
  elif ch=='"':quoted=True
  elif ch=='(':depth+=1
  elif ch==')':
   depth-=1
   if depth==0:return i+1
 raise ValueError('Unclosed symbol')
for path in O.glob('*.kicad_sch'):
 s=path.read_text()
 for part in parts:
  needle='(symbol "ECU:'+part.ref+'"';start=s.find(needle)
  if start>=0:s=s[:start]+gen.symbol(part,True)[0]+s[end_block(s,start):]
 path.write_text(s)
flags=[Part('#FLG0'+str(i),'PWR_FLAG','ECU:unused',{'1':net},{},{'1':'power_out'},'power',(0,0)) for i,net in enumerate(['GND','VIN_PROT','+5V','VIN_FILTERED'],1)]
(O/'lib/ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "esp32_ecu") '+'\n'.join(gen.symbol(p)[0] for p in parts+flags)+')')
