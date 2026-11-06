"""Remove disconnected routing tails, rechecking connectivity after each pass."""
import json,subprocess,sys
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parents[1];path=root/'hardware/a1-hand-solder/esp32-ecu.kicad_pcb';report=root/'reports/a1/drc.json'
for i in range(12):
 s=json.loads(report.read_text());ids={v['items'][0]['uuid'] for v in s['violations'] if v['type']=='track_dangling'}
 if not ids:break
 if s['unconnected_items']:raise RuntimeError('Connectivity must be complete before pruning redundant tails')
 code="""import json,pcbnew as p,sys
path,report=sys.argv[1:];b=p.LoadBoard(path);s=json.load(open(report));ids={v['items'][0]['uuid'] for v in s['violations'] if v['type']=='track_dangling'}
remove=[t for t in b.GetTracks() if t.m_Uuid.AsString() in ids]
for t in remove:b.Remove(t)
p.SaveBoard(path,b)
"""
 subprocess.run([sys.executable,'-c',code,str(path),str(report)],check=True)
 subprocess.run(['sh',str(root/'scripts/kicad.sh'),'pcb','drc','--refill-zones','--save-board','--schematic-parity','--format','json','-o',str(report),str(path)],check=True,stdout=subprocess.DEVNULL)
s=json.loads(report.read_text());print('DRC:',len(s['violations']),'unconnected:',len(s['unconnected_items']),'parity:',len(s['schematic_parity']))
if s['violations'] or s['unconnected_items'] or s['schematic_parity']:raise RuntimeError('A1 checks are not clean')
