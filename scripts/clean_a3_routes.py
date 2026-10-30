"""Prune unused router tails, requiring a clean, connected native DRC after cleanup."""
from pathlib import Path
import json,subprocess,sys
R=Path(__file__).resolve().parents[1]
if '--remove' in sys.argv:
 import pcbnew as p
 path=R/'hardware/a3-compact/esp32-ecu.kicad_pcb';b=p.LoadBoard(str(path));s=json.loads((R/'reports/a3/drc.json').read_text());bad={i['uuid'] for v in s['violations'] if v['type'] in ['track_dangling','via_dangling'] for i in v['items']}
 tracks=list(b.GetTracks())
 for t in tracks:
  if t.m_Uuid.AsString() in bad:b.Remove(t)
 p.SaveBoard(str(path),b);raise SystemExit
python='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3'
for attempt in range(10):
 s=json.loads((R/'reports/a3/drc.json').read_text());assert not s['unconnected_items'] and not s['schematic_parity'],s
 print('Cleanup',attempt,'violations',len(s['violations']),flush=True)
 if not s['violations']:break
 assert all(v['type'] in ['track_dangling','via_dangling'] for v in s['violations']),s['violations']
 subprocess.run([python,__file__,'--remove'],check=True)
 subprocess.run(['sh','scripts/kicad.sh','pcb','drc','--format','json','--refill-zones','--save-board','--schematic-parity','--output','reports/a3/drc.json','hardware/a3-compact/esp32-ecu.kicad_pcb'],cwd=R,check=True,stdout=subprocess.DEVNULL)
else:raise RuntimeError('Route cleanup did not converge')
