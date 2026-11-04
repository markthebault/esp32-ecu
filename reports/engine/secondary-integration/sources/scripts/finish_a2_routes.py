"""Complete the three reviewed residual A2 nets using the conservative In2 grid."""
from pathlib import Path
import json,re
R=Path(__file__).resolve().parents[1]
s=(R/'scripts/finish_routes.py').read_text().split('report=json.loads')[0].replace('PATH=ROOT/"hardware/esp32-ecu.kicad_pcb"','PATH=ROOT/"hardware/a2-through-hole/esp32-ecu.kicad_pcb"')
s=s.replace('step=.2','step=.1').replace('width=1001','width=2001').replace('r+.15','r+.08').replace('/1e6-.45','/1e6-.40').replace('/1e6+.45','/1e6+.40')
exec(compile(s,__file__,'exec'))
report=json.loads((R/'reports/a2/drc.json').read_text());missing={re.search(r'\[([^\]]+)\]',v['items'][0]['description']).group(1) for v in report['unconnected_items']}
plans={'CAM_INV':(('U7',6),('U7',9)),'INJ4_RC':(('R64',2),('C64',1)),'IGN1_RESET_N':(('U14',3),('U17',3))}
for net in sorted(missing):
 if net not in plans:raise RuntimeError('Unreviewed residual net '+net)
 start,end=plans[net];a=escape(*start,net);c=escape(*end,net)
 for layer in [p.In2_Cu,p.F_Cu,p.B_Cu]:
  try:route(a,c,net,layer);break
  except RuntimeError:continue
 else:raise RuntimeError('No reviewed routing layer can connect '+net)
 p.SaveBoard(str(PATH),board)
for f in board.GetFootprints():
 if f.GetReference()=='H5':
  f.SetField('MPN','');f.GetField('MPN').SetVisible(False);f.GetField('MPN').SetLayer(p.F_Fab)
p.SaveBoard(str(PATH),board)
