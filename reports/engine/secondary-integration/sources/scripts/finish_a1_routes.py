#!/usr/bin/env python3
"""Complete reviewed A1 residual logic nets. Requires fresh reports/a1/drc.json."""
from pathlib import Path
import sys,json,re
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pcbnew as p
root=Path(__file__).resolve().parents[1]
# Reuse the conservative path finder, not the A0-specific plans or board.
s=(root/'scripts/finish_routes.py').read_text().split('report=json.loads')[0]
s=s.replace('for radius in [1.2,1.6,2,2.6,3.2,4]:','for radius in [0,.4,.6,.8,1,1.2,1.6,2,2.6,3.2,4]:')
s=s.replace('PATH=ROOT/"hardware/esp32-ecu.kicad_pcb"','PATH=ROOT/"hardware/a1-hand-solder/esp32-ecu.kicad_pcb"')
s=s.replace('clear(*v,.56,net,l)','clear(*v,.85,net,l)')
s=s.replace('if occupied[si] or occupied[gi]:raise RuntimeError(f"Blocked route endpoint: {net}")','if occupied[si] or occupied[gi]:raise RuntimeError(f"Blocked route endpoint: {net} {bool(occupied[si])} {bool(occupied[gi])}")')
exec(compile(s,__file__,'exec'))
original_escape=escape
def escape(ref,n,net):
 try:return original_escape(ref,n,net)
 except RuntimeError:pass
 f=board.FindFootprintByReference(ref);pad=next(x for x in f.Pads() if x.GetNumber()==str(n));a=xy(pad.GetPosition())
 for radius in [1,1.5,2,3,4,5,6,8,10]:
  for i in range(32):
   angle=i*math.pi/16;v=(round((a[0]+radius*math.cos(angle))/step)*step,round((a[1]+radius*math.sin(angle))/step)*step)
   if not all(clear(*v,.6,net,l) for l in [p.F_Cu,p.In2_Cu,p.B_Cu]):continue
   try:route(a,v,net,p.F_Cu)
   except RuntimeError:continue
   via=p.PCB_VIA(board);via.SetPosition(vec(*v));via.SetWidth(p.FromMM(.7));via.SetDrill(p.FromMM(.35));via.SetViaType(p.VIATYPE_THROUGH);via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetNet(board.FindNet(net));board.Add(via);return v
 raise RuntimeError('Cannot find A1 via escape '+ref+':'+str(n))
report=json.loads((root/'reports/a1/drc.json').read_text())
plans={'CAN_TERM':(('R46',2),('JP2',1)), 'ADC1':(('U6',2),('R22',2)), 'ADC0':(('U6',1),('R20',2)), 'ADC_CS':(('U3',16),('U6',10)), 'SPI_MOSI':(('U3',17),('U6',11)), 'INJ4_RESET_N':(('U16',11),('U13',11)), 'IGN1_WINDOW':(('U14',13),('U11',2))}
missing={re.search(r'\[([^\]]+)\]',v['items'][0]['description']).group(1) for v in report['unconnected_items']}
for net in sorted(missing):
 if net not in plans:raise RuntimeError('Unreviewed A1 residual net '+net)
 start,end=plans[net];a=escape(*start,net);b=escape(*end,net);print(net,a,b,flush=True);route(a,b,net)
 p.SaveBoard(str(PATH),board)
# Remove only dangling stubs from before the completion; these are now redundant.
ids={v['items'][0]['uuid'] for v in report['violations'] if v['type'] in ['track_dangling','via_dangling']}
for t in list(board.GetTracks()):
 if t.m_Uuid.AsString() in ids:board.Remove(t)
f=board.FindFootprintByReference('U3');pad=next(x for x in f.Pads() if x.GetNumber()=='35');n=p.NETINFO_ITEM(board,'unconnected-(U3-Pad35)');board.Add(n);pad.SetNet(n)
for f in board.GetFootprints():
 f.Reference().SetLayer(p.F_Fab);f.Reference().SetVisible(not f.GetReference().startswith('H'))
p.SaveBoard(str(PATH),board)
