"""Legible connector-location map from actual native KiCad footprint positions."""
from pathlib import Path
import pcbnew as p
R=Path(__file__).resolve().parents[1];b=p.LoadBoard(str(R/'hardware/a3-compact/esp32-ecu.kicad_pcb'));fs={f.GetReference():f for f in b.GetFootprints()}
s=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="-3 -3 126 126">','<rect x="-3" y="-3" width="126" height="126" fill="white"/>','<rect width="120" height="120" fill="#f1f5f2" stroke="#173137" stroke-width=".5"/>']
for ref in ['U3','H1','H2','H3','H4','H5']+[r for r in fs if r.startswith('J')]:
 f=fs[ref];padlist=[q for q in f.Pads() if q.GetNumber()]
 if ref.startswith('H'):
  x,y=f.GetPosition().x/1e6-10,f.GetPosition().y/1e6-10;s.append(f'<circle cx="{x}" cy="{y}" r="1.6" fill="white" stroke="#556964" stroke-width=".4"/>')
  if ref=='H5':s.append(f'<text x="{x+3}" y="{y+.7}" font-family="sans-serif" font-size="2.2" fill="#173137">H5</text>')
  continue
 bb=[g.GetBoundingBox() for g in f.GraphicalItems() if g.GetLayer()==p.F_CrtYd]
 if not bb:continue
 x=min(q.GetX() for q in bb)/1e6-10;y=min(q.GetY() for q in bb)/1e6-10;w=max(q.GetRight() for q in bb)/1e6-10-x;h=max(q.GetBottom() for q in bb)/1e6-10-y
 fill='#d4ded8' if ref=='U3' else '#f5e7c9' if ref in ['J2','J3','J4','JP1','JP2'] else '#d5e9e4';s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx=".4" fill="{fill}" stroke="#3b6951" stroke-width=".35"/>')
 for pad in padlist:
  px,py=pad.GetPosition().x/1e6-10,pad.GetPosition().y/1e6-10
  s.append(f'<circle cx="{px}" cy="{py}" r=".58" fill="{chr(35)+"3b6951" if pad.GetNumber()=="1" else "white"}" stroke="#3b6951" stroke-width=".2"/>')
 if ref not in ['U3','J2','J3','J4','JP1','JP2']:
  angle=90 if h>w*1.5 else 0;cx=x+1.8 if angle else x+w/2;cy=y+h/2 if angle else y+h-1.8
  s.append(f'<text x="{cx}" y="{cy+.75}" transform="rotate({angle} {cx} {cy})" text-anchor="middle" font-family="sans-serif" font-size="2.4" font-weight="bold" fill="#173137">{ref}</text>')
# Callouts point to each exact header, with text in otherwise empty map space.
for ref,tx,ty,label in [('J2',62,47,'J2 UART'),('J3',42,45,'J3 INTERLOCK'),('J4',60,66,'J4 EXPANSION'),('JP1',81,92,'JP1 RECEIVE'),('JP2',72,97,'JP2 TERMINATION'),('J20',104,88,'J20 SHIELD')]:
 f=fs[ref];x,y=f.GetPosition().x/1e6-10,f.GetPosition().y/1e6-10;s.append(f'<path d="M{x} {y} L{tx} {ty+1}" fill="none" stroke="#627770" stroke-width=".25"/><text x="{tx}" y="{ty}" text-anchor="middle" font-family="sans-serif" font-size="2.2" fill="#173137">{label}</text>')
s.append('<text x="20" y="54" transform="rotate(90 20 54)" text-anchor="middle" font-family="sans-serif" font-size="3" fill="#173137">PLUG-IN ESP32-S3</text><text x="59" y="15" text-anchor="middle" font-family="sans-serif" font-size="2.2" fill="#596c70">Top view / 120 × 120 mm</text><text x="59" y="20" text-anchor="middle" font-family="sans-serif" font-size="1.8" fill="#596c70">Filled dot = pin 1</text></svg>');(R/'reports/a3/connection-map.svg').write_text(''.join(s))
