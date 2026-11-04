#!/usr/bin/env python3
"""Export/import the separate SW2 prototype only. No carrier/archive writes."""
import argparse,hashlib,json,re
from pathlib import Path
import pcbnew as pcb
from kicad9_carrier_copy import chunks
ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'hardware/switch-inputs/switches.kicad_pcb'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',type=Path);p.add_argument('--import-session',type=Path);a=p.parse_args()
 if bool(a.prepare)==bool(a.import_session):p.error('Choose one operation')
 board=pcb.LoadBoard(str(BOARD))
 if a.prepare:
  assert not list(board.GetTracks()),'Preserve existing routed work'
  out=a.prepare.resolve();out.mkdir(parents=True,exist_ok=True);dsn=out/'switches.dsn'
  assert pcb.ExportSpecctraDSN(board,str(dsn));text=dsn.read_text();via=re.search(r'\(via "([^"]+)"',text)[1]
  classes=list(chunks(text,'class'));assert len(classes)==1;start,end,_=classes[0]
  nets=sorted(n.GetNetname()for n in board.GetNetsByNetcode().values()if n.GetNetname())
  groups=[('Supply',['+3V3','GND'],500),('Signals',[n for n in nets if n not in ('+3V3','GND')],350)]
  replacement='\n'.join('(class '+name+' '+' '.join(json.dumps(n)for n in members)+f' (circuit (use_via "{via}")) (rule (width {width}) (clearance 300)))'for name,members,width in groups)
  dsn.write_text(text[:start]+replacement+text[end:])
  (out/'routing-input.json').write_text(json.dumps(dict(board_sha256=hashlib.sha256(BOARD.read_bytes()).hexdigest(),dsn_sha256=hashlib.sha256(dsn.read_bytes()).hexdigest(),routing_clearance_mm=.3,signal_width_mm=.35,supply_width_mm=.5,qualification='Router input, not electrical/manufacturing qualification'),indent=2)+'\n')
 else:
  assert not list(board.GetTracks()),'Import requires the preserved unrouted prototype'
  assert pcb.ImportSpecctraSES(board,str(a.import_session.resolve()));pcb.SaveBoard(str(BOARD),board)
  path=BOARD.parent/'net_contract.json';c=json.loads(path.read_text());c['status']='ROUTED_DESIGN_HOLD_NOT_FOR_FABRICATION';path.write_text(json.dumps(c,indent=2)+'\n')
 print('SW2 prototype routing operation complete; native checks and physical holds remain')
if __name__=='__main__':main()
