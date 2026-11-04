import pcbnew as p
from pathlib import Path
R=Path(__file__).resolve().parents[1];path=R/'hardware/a3-compact/esp32-ecu.kicad_pcb';b=p.LoadBoard(str(path))
def label(text,x,y,angle=0,layer=p.F_SilkS,size=.8):
 if any(isinstance(d,p.PCB_TEXT) and d.GetText()==text for d in b.GetDrawings()):return
 t=p.PCB_TEXT(b);t.SetText(text);t.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));t.SetTextSize(p.VECTOR2I(p.FromMM(size),p.FromMM(size)));t.SetTextThickness(p.FromMM(.12));t.SetTextAngle(p.EDA_ANGLE(angle,p.DEGREES_T));t.SetLayer(layer)
 if layer==p.B_SilkS:t.SetMirrored(True)
 b.Add(t)
for i,name in enumerate(['MAP','TPS','CLT','IAT','WB','POSTCAT','CRANK','CAM']):label(f'J{11+i} {name}',25.5+12.2*i,129.1)
for text,x,y,a in [('J9 INJECTORS',129,40,90),('J10 IGNITION',129,74,90),('J8 RELAYS',129,101,90),('J1 12V',22,17.8,0),('J19 GND',110,11.2,0),('J7 CAN',11.5,98,90)]:label(text,x,y,a)
label('A3-120 / ESP32-S3\n6 LAYER / BENCH ONLY',30,68,90,p.B_SilkS,1.0)
p.SaveBoard(str(path),b)
