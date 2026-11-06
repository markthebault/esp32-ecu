"""Dimension-driven top-view diagram of the PCB mounts and water seal."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'enclosure/a2';d=json.loads((O/'dimensions.json').read_text())
s=['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1000" viewBox="-8 -10 234 260">','<rect x="-8" y="-10" width="234" height="260" rx="3" fill="#f6f8fa"/>','<rect x="0" y="0" width="218" height="218" rx="1" fill="#dfe5eb" stroke="#465566" stroke-width=".6"/>','<rect x="9" y="9" width="200" height="200" fill="#dcecdf" stroke="#45825a" stroke-width=".5" stroke-dasharray="2 1"/>']
pts=' '.join(f'{x},{y}' for x,y in d['gasket_centerline_mm']);s.append(f'<polygon points="{pts}" fill="none" stroke="#2084c6" stroke-width="3" stroke-linejoin="round"/>')
for x,y in d['lid_fasteners_mm']:s.append(f'<circle cx="{x}" cy="{y}" r="3.2" fill="#56616f"/><circle cx="{x}" cy="{y}" r="1.2" fill="#f6f8fa"/>')
for name,(x,y),tx,ty in zip(['H1','H2','H3','H4'],d['pcb_mounts_mm'],[29,170,29,170],[34,34,184,184]):
 s.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#e6a63a" stroke="#936012" stroke-width=".5"/><circle cx="{x}" cy="{y}" r="1.6" fill="#fff"/><path d="M{x} {y} L{tx} {ty-3}" stroke="#936012" stroke-width=".5"/><text x="{tx}" y="{ty}" font-family="sans-serif" font-size="5" fill="#5b3a09">{name}</text>')
s.append('<text x="109" y="98" text-anchor="middle" font-family="sans-serif" font-size="7" fill="#27543a">200 × 200 mm PCB</text><text x="109" y="108" text-anchor="middle" font-family="sans-serif" font-size="5" fill="#27543a">Four corner screws into blind M3 inserts</text>')
s.append('<text x="109" y="126" text-anchor="middle" font-family="sans-serif" font-size="4.5" fill="#344352">H5 is a separate electrical shield lug.</text>')
s.extend(['<circle cx="7" cy="231" r="3" fill="#e6a63a"/><text x="14" y="233" font-family="sans-serif" font-size="4.5">4 PCB supports, 6 mm above the floor</text>','<circle cx="7" cy="241" r="3" fill="#56616f"/><text x="14" y="243" font-family="sans-serif" font-size="4.5">8 lid screws, outside the blue gasket</text>','</svg>'])
(O/'mounting-plan.svg').write_text(''.join(s));print(O/'mounting-plan.svg')
