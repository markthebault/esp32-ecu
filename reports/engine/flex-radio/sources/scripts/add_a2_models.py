"""Attach module envelopes and stock female socket models without changing copper."""
import pcbnew as p
from pathlib import Path
R=Path(__file__).resolve().parents[1];path=R/'hardware/a2-through-hole/esp32-ecu.kicad_pcb';b=p.LoadBoard(str(path))
for f in b.GetFootprints():
 if f.GetReference() not in ['U1','U3']:continue
 f.Models().clear()
 name='esp32-s3-devkitc-envelope' if f.GetReference()=='U3' else 'pololu-d36v6-envelope'
 m=p.FP_3DMODEL();m.m_Filename='${KIPRJMOD}/lib/models/'+name+'.step';f.Models().push_back(m)
 if f.GetReference()=='U3':
  for x in [0,22.86]:
   m=p.FP_3DMODEL();m.m_Filename='${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x22_P2.54mm_Vertical.step';m.m_Offset.x=x;f.Models().push_back(m)
p.SaveBoard(str(path),b);print('Attached purchased-module envelope and female socket models')
