#!/usr/bin/python3
"""Report opposite-side front-PTH solder-land/back-Fab body plan overlaps.
These are 2D assembly warnings, not a 3D fit acceptance or lead-size model.
Pass a snapshot PCB path and output JSON. Never saves a PCB.
"""
import sys,json,math
import pcbnew as p
b=p.LoadBoard(sys.argv[1]);back=[];front=[]
for fp in b.GetFootprints():
 if fp.GetAttributes() & p.FP_EXCLUDE_FROM_BOM:continue
 if fp.GetLayer()==p.B_Cu:
  shapes=[g for g in fp.GraphicalItems() if g.GetLayer()==p.B_Fab and isinstance(g,p.PCB_SHAPE) and g.GetShape() in [p.SHAPE_T_RECT,p.SHAPE_T_CIRCLE,p.SHAPE_T_POLY]]
  assert shapes,fp.GetReference()
  body=max(shapes,key=lambda x:x.GetBoundingBox().GetWidth()*x.GetBoundingBox().GetHeight());back.append((fp.GetReference(),body.GetBoundingBox()))
 elif fp.GetLayer()==p.F_Cu:
  front.extend((fp.GetReference(),pad.GetNumber(),pad.GetBoundingBox()) for pad in fp.Pads() if pad.GetAttribute()==p.PAD_ATTRIB_PTH)
flags=[];minimums={}
for br,a in back:
 candidates=[]
 for fr,no,z in front:
  dx=max(a.GetLeft()-z.GetRight(),z.GetLeft()-a.GetRight(),0);dy=max(a.GetTop()-z.GetBottom(),z.GetTop()-a.GetBottom(),0)
  candidates.append((math.hypot(dx,dy)/1e6,fr+'.'+no))
  if a.GetLeft()<z.GetRight() and a.GetRight()>z.GetLeft() and a.GetTop()<z.GetBottom() and a.GetBottom()>z.GetTop():
   flags.append(dict(back_body=br,front_pad=fr+'.'+no,body_bounds_mm=[v/1e6 for v in [a.GetLeft(),a.GetTop(),a.GetRight(),a.GetBottom()]],pad_bounds_mm=[v/1e6 for v in [z.GetLeft(),z.GetTop(),z.GetRight(),z.GetBottom()]]))
 minimums[br]=min(candidates)
r=dict(minimum_body_to_front_pad_box_clearance_mm=minimums,back_body_count=len(back),opposite_side_plan_overlap_flags=flags,physical_qualification=False,limitations='Bounding boxes include drawing stroke. Exact package envelope, lead trimming, stand-off and Z clearance still require acceptance.')
open(sys.argv[2],'w').write(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
