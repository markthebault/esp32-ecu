"""Deterministic courtyard packing candidates for a NEW A6 carrier copy only.

This is a two-dimensional placement heuristic, not routing, soldering/thermal,
module/enclosure fit or electrical qualification. Original carrier is untouched.
"""
import json,math,random
from pathlib import Path
import pcbnew as pcb
from build_a5_idle_interface import box,overlaps

GAP=.15
ANTENNA=(14,29,44,40)
BYPASS={'C10':('U2','2'),'C15':('U4','8'),'C16':('U5','2'),'C28':('U6','16'),
 'C32':('U7','14'),'C33':('U8','3'),'C34':('U8','5'),'C35':('U9','14'),
 'C36':('U10','14'),'C37':('U11','14'),'C38':('U12','16'),'C39':('U13','16'),
 'C40':('U14','16'),'C41':('U15','16'),'C42':('U16','14'),'C43':('U17','14'),
 'C160':('U18','8'),'C161':('U19','18'),'C162':('U20','2')}
def expanded(b):return b[0]-GAP/2,b[1]-GAP/2,b[2]+GAP/2,b[3]+GAP/2
def contains(a,b):return a[0]<=b[0]+1e-8 and a[1]<=b[1]+1e-8 and a[2]>=b[2]-1e-8 and a[3]>=b[3]-1e-8
def subtract(free,used):
 pieces=[]
 for r in free:
  if not overlaps(r,used,0):pieces.append(r);continue
  if r[0]<used[0]<r[2]:pieces.append((r[0],r[1],used[0],r[3]))
  if r[0]<used[2]<r[2]:pieces.append((used[2],r[1],r[2],r[3]))
  if r[1]<used[1]<r[3]:pieces.append((r[0],r[1],r[2],used[1]))
  if r[1]<used[3]<r[3]:pieces.append((r[0],used[3],r[2],r[3]))
 unique=list(dict.fromkeys(pieces))
 return [r for i,r in enumerate(unique)if r[2]-r[0]>.1 and r[3]-r[1]>.1 and not any(i!=j and contains(o,r)for j,o in enumerate(unique))]

def pack(board,parts,desired,attempts=32,problem_path=None,exclude=()):
 fps={f.GetReference():f for f in board.GetFootprints()if f.GetReference()not in exclude};assert set(fps)==set(parts)
 fixed={ref for ref in fps if ref.startswith(('J','H'))and ref not in ('J22','J23')}
 fixed.update(('U3','U1','U2','Q1','Q2','Q3','Q4','D1','L2','R150'))
 fixed&=set(fps)
 anchors={ref:(fps[ref].GetPosition().x,fps[ref].GetPosition().y,fps[ref].GetOrientationDegrees())for ref in fixed}
 base=[(11,11,129,129)]
 for ref in sorted(fixed):base=subtract(base,expanded(box(fps[ref])))
 base=subtract(base,expanded(ANTENNA))
 offsets={};pad_offsets={}
 for ref in sorted(fps):
  fp=fps[ref]
  if ref in fixed:continue
  offsets[ref]={};pad_offsets[ref]={}
  for angle in (0,90,180,270):
   fp.SetPosition(pcb.VECTOR2I(0,0));fp.SetOrientationDegrees(angle);offsets[ref][angle]=box(fp)
   pad_offsets[ref][angle]={p.GetNumber():[p.GetPosition().x/1e6,p.GetPosition().y/1e6]for p in fp.Pads()if p.GetNumber()}
 if problem_path is not None:
  problem=dict(schema=1,bounds_mm=[11,11,129,129],gap_mm=GAP,antenna_mm=ANTENNA,
   fixed={ref:dict(court_mm=box(fps[ref]),position_nm=anchors[ref],absolute_pads_mm={p.GetNumber():[p.GetPosition().x/1e6,p.GetPosition().y/1e6]for p in fps[ref].Pads()if p.GetNumber()})for ref in fixed},
   movable={ref:dict(rotated_courts_mm=offsets[ref],rotated_pads_mm=pad_offsets[ref],pin_nets=parts[ref].pins,desired_origin_mm=desired[ref])for ref in offsets},bypass={ref:value for ref,value in BYPASS.items()if ref in offsets},qualification='New copy2D geometry problem only; no route, fit or electrical acceptance')
  Path(problem_path).write_text(json.dumps(problem,indent=2)+'\n')
 def area(ref):b=offsets[ref][0];return(b[2]-b[0])*(b[3]-b[1])
 movable=set(offsets);failures=[];best={}
 for seed in range(attempts):
  rng=random.Random(seed);free=list(base);placed={ref:box(fps[ref])for ref in fixed};order=[]
  # Keep existing regulator bypass close, then allocate each IC and its bypass.
  order.extend(ref for ref in BYPASS if ref in movable and BYPASS[ref][0]in fixed)
  ics=sorted((ref for ref in sorted(movable)if ref.startswith('U')),key=lambda ref:-area(ref)*(1+rng.uniform(-.15,.15)))
  for ref in ics:
   order.append(ref);order.extend(c for c in BYPASS if c in movable and BYPASS[c][0]==ref)
  used=set(order)
  order.extend(sorted(sorted(movable-used),key=lambda ref:(0 if ref.startswith('J')else 1,-area(ref)*(1+rng.uniform(-.1,.1)))))
  positions={};failed=None
  for ref in order:
   fp=fps[ref];prefer=desired[ref]
   if ref in BYPASS:
    owner,pin=BYPASS[ref];pad=next(p for p in fps[owner].Pads()if p.GetNumber()==pin);prefer=(pad.GetPosition().x/1e6,pad.GetPosition().y/1e6)
   candidates=[]
   for angle,offset in offsets[ref].items():
    w,h=offset[2]-offset[0]+GAP,offset[3]-offset[1]+GAP
    for r in free:
     if w>r[2]-r[0]+1e-8 or h>r[3]-r[1]+1e-8:continue
     for x,y in ((r[0],r[1]),(r[2]-w,r[1]),(r[0],r[3]-h),(r[2]-w,r[3]-h)):
      px,py=x+GAP/2-offset[0],y+GAP/2-offset[1]
      distance=math.hypot(px-prefer[0],py-prefer[1])
      if ref in BYPASS:
       fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(px),pcb.FromMM(py)));fp.SetOrientationDegrees(angle)
       supply=parts[ref].pins['1'];d=min(math.dist((p.GetPosition().x/1e6,p.GetPosition().y/1e6),prefer)for p in fp.Pads()if p.GetNetname()==supply)
       if d>13:continue
      dw,dh=r[2]-r[0]-w,r[3]-r[1]-h
      if seed%3==0:score=(min(dw,dh),max(dw,dh),distance)
      elif seed%3==1:score=((r[2]-r[0])*(r[3]-r[1])-w*h,distance,min(dw,dh))
      else:score=(distance+.2*min(dw,dh),min(dw,dh),max(dw,dh))
      candidates.append((score,px,py,angle,(x,y,x+w,y+h)))
   if not candidates:failed=ref;break
   _,px,py,angle,rectangle=min(candidates);fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(px),pcb.FromMM(py)));fp.SetOrientationDegrees(angle)
   free=subtract(free,rectangle);placed[ref]=box(fp);positions[ref]=dict(xy_mm=[px,py],angle_deg=angle)
  if failed:
   if len(positions)>len(best.get('positions',{})):best=dict(seed=seed,positions=positions,unplaced=sorted(movable-set(positions)))
   failures.append(dict(seed=seed,failed=failed,placed=len(positions)));print('Packing attempt',seed,'stopped at',failed,'after',len(positions),'parts',flush=True);continue
  # Validate the actual integer-coordinate KiCad boxes, not ideal rectangles.
  bad=[]
  for ref,bounds in placed.items():
   if ref not in fixed and (min(bounds[:2])<11-1e-6 or max(bounds[2:])>129+1e-6 or overlaps(bounds,ANTENNA,0)):bad.append((ref,'boundary/antenna'))
   for other,ob in placed.items():
    if ref<other and overlaps(bounds,ob,0):bad.append((ref,other))
  if bad:raise RuntimeError('Packed integer courtyard overlap: '+str(bad[:5]))
  for ref,(x,y,angle)in anchors.items():
   f=fps[ref];assert(f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees())==(x,y,angle)
   positions[ref]=dict(xy_mm=[x/1e6,y/1e6],angle_deg=angle)
  return dict(seed=seed,attempts=failures,positions=positions,fixed_anchors=sorted(fixed),courtyard_gap_mm=GAP,full_antenna_rectangle_mm=ANTENNA,qualification='2D courtyard heuristic only; entire new routing, electrical/thermal and mechanical/assembly fit acceptance pending')
 if problem_path is not None:
  problem['greedy_best_partial']=best;Path(problem_path).write_text(json.dumps(problem,indent=2)+'\n')
 raise RuntimeError('No packing candidate in bounded attempts: '+str(failures[-4:]))
