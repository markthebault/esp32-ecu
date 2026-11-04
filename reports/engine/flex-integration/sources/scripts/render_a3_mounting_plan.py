import json
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'enclosure/a3';d=json.loads((O/'dimensions.json').read_text());W,H=d['base_outer_mm'][:2]
s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000" viewBox="-8 -10 {W+16} {H+42}">',f'<rect x="-8" y="-10" width="{W+16}" height="{H+42}" fill="#f6f8fa"/>',f'<rect width="{W}" height="{H}" fill="#dfe5eb" stroke="#465566" stroke-width=".5"/>','<rect x="9" y="9" width="120" height="120" fill="#dcecdf" stroke="#45825a" stroke-width=".4" stroke-dasharray="2 1"/>']
pts=' '.join(f'{x},{y}' for x,y in d['gasket_centerline_mm']);s.append(f'<polygon points="{pts}" fill="none" stroke="#2084c6" stroke-width="3"/>')
for x,y in d['lid_fasteners_mm']:s.append(f'<circle cx="{x}" cy="{y}" r="3.2" fill="#56616f"/><circle cx="{x}" cy="{y}" r="1.1" fill="white"/>')
for ref,(x,y),tx,ty in zip(['H1','H2','H3','H4'],d['pcb_mounts_mm'],[26,105,26,105],[30,30,114,114]):
 s.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#e6a63a" stroke="#936012" stroke-width=".4"/><circle cx="{x}" cy="{y}" r="1.6" fill="white"/><path d="M{x} {y} {tx} {ty-2}" stroke="#936012" stroke-width=".3"/><text x="{tx}" y="{ty}" font-family="sans-serif" font-size="4" fill="#5b3a09">{ref}</text>')
s.append('<text x="69" y="58" text-anchor="middle" font-family="sans-serif" font-size="5" fill="#27543a">120 × 120 mm PCB</text><text x="69" y="67" text-anchor="middle" font-family="sans-serif" font-size="3.2" fill="#27543a">112 × 112 mm mounting centers</text><text x="69" y="79" text-anchor="middle" font-family="sans-serif" font-size="3" fill="#344352">Four blind M3 insert supports</text>')
for x in d['cable_entry_x_mm']:s.append(f'<path d="M{x-8} 150h16" stroke="#2084c6" stroke-width="2"/>')
s.extend(['<circle cx="6" cy="163" r="2.5" fill="#e6a63a"/><text x="12" y="165" font-family="sans-serif" font-size="3.4">4 PCB mounts / 6 mm above the floor</text>','<circle cx="6" cy="174" r="2.5" fill="#56616f"/><text x="12" y="176" font-family="sans-serif" font-size="3.4">8 lid screws / outside the gasket</text>','</svg>']);(O/'mounting-plan.svg').write_text(''.join(s))
