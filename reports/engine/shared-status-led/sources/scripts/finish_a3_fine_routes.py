"""Shorten reviewed timing nets with a three-layer grid search. KiCad Python.
The output must pass fresh KiCad DRC before it is accepted.
"""
import math,heapq,json,re,sys
from array import array
from pathlib import Path
import pcbnew as p
R=Path(__file__).resolve().parents[1];PATH=R/'hardware/a3-compact/esp32-ecu.kicad_pcb';b=p.LoadBoard(str(PATH));LAYERS=[p.F_Cu,p.In2_Cu,p.B_Cu];step=.05
V=lambda x,y:p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def xy(v):return v.x/1e6,v.y/1e6
def pad(ref,n):return next(x for f in b.GetFootprints() if f.GetReference()==ref for x in f.Pads() if x.GetNumber()==str(n))
def track(a,c,net,layer):
 if math.dist(a,c)<.001:return
 t=p.PCB_TRACK(b);t.SetStart(V(*a));t.SetEnd(V(*c));t.SetWidth(p.FromMM(.2));t.SetLayer(layer);t.SetNet(b.FindNet(net));b.Add(t)
def route(a,c,net,allowed_start=None,allowed_goal=None):
 x0=max(11,math.floor(min(a[0],c[0])-18));y0=max(11,math.floor(min(a[1],c[1])-18));x1=min(129,math.ceil(max(a[0],c[0])+18));y1=min(129,math.ceil(max(a[1],c[1])+18));w=round((x1-x0)/step)+1;h=round((y1-y0)/step)+1;size=w*h
 occ=[bytearray(size) for _ in LAYERS];vocc=bytearray(size)
 def pt(v):return round((v[0]-x0)/step),round((v[1]-y0)/step)
 def rect(mask,bb,r):
  left,top=pt((bb.GetX()/1e6-r,bb.GetY()/1e6-r));right,bottom=pt((bb.GetRight()/1e6+r,bb.GetBottom()/1e6+r));left=max(0,left);right=min(w-1,right)
  if right<left:return
  for y in range(max(0,top),min(h-1,bottom)+1):mask[y*w+left:y*w+right+1]=b'\1'*(right-left+1)
 def disk(mask,v,r):
  cx,cy=pt(v);rr=math.ceil(r/step)
  if cx+rr<0 or cx-rr>=w or cy+rr<0 or cy-rr>=h:return
  for y in range(max(0,cy-rr),min(h-1,cy+rr)+1):
   dy=(y-cy)*step
   if abs(dy)>r:continue
   dx=math.floor(math.sqrt(max(0,r*r-dy*dy))/step);left=max(0,cx-dx);right=min(w-1,cx+dx)
   if right>=left:mask[y*w+left:y*w+right+1]=b'\1'*(right-left+1)
 # All-layer antenna keepout.
 for mask in occ:
  class Box:
   def GetX(self):return 16e6
   def GetY(self):return 29e6
   def GetRight(self):return 43e6
   def GetBottom(self):return 36e6
  rect(mask,Box(),.45)
 for f in b.GetFootprints():
  for q in f.Pads():
   if not q.GetNumber():continue
   bb=q.GetBoundingBox();rect(vocc,bb,.65)
   if q.GetNetname()==net:continue
   for li,l in enumerate(LAYERS):
    if q.IsOnLayer(l):rect(occ[li],bb,.35)
 for t in b.GetTracks():
  if isinstance(t,p.PCB_VIA):
   disk(vocc,xy(t.GetPosition()),t.GetWidth(p.F_Cu)/2e6+.65)
   if t.GetNetname()!=net:
    for mask in occ:disk(mask,xy(t.GetPosition()),t.GetWidth(p.F_Cu)/2e6+.35)
   continue
  if t.GetNetname()==net:continue
  if t.GetLayer() not in LAYERS:continue
  mask=occ[LAYERS.index(t.GetLayer())];u,v=xy(t.GetStart()),xy(t.GetEnd());samples=max(1,math.ceil(math.dist(u,v)/step*2))
  for j in range(samples+1):
   d=(u[0]+(v[0]-u[0])*j/samples,u[1]+(v[1]-u[1])*j/samples);disk(mask,d,t.GetWidth()/2e6+.35);disk(vocc,d,t.GetWidth()/2e6+.73)
 ax,ay=pt(a);gx,gy=pt(c);start=ay*w+ax;goal=gy*w+gx
 cost=array('I',[0xffffffff])*(size*3);parent=array('i',[-1])*(size*3);closed=bytearray(size*3);heap=[]
 for li in range(3):
  if not occ[li][start] and (allowed_start is None or LAYERS[li] in allowed_start):cost[li*size+start]=0;heapq.heappush(heap,(0,li*size+start))
 def push(ni,i,nc):
  if nc>=cost[ni]:return
  cost[ni]=nc;parent[ni]=i;pi=ni%size;x,y=pi%w,pi//w;dx,dy=abs(x-gx),abs(y-gy);heapq.heappush(heap,(nc+10*max(dx,dy)+4*min(dx,dy),ni))
 end=None
 while heap:
  _,i=heapq.heappop(heap)
  if closed[i]:continue
  closed[i]=1;li,pi=divmod(i,size)
  if pi==goal and (allowed_goal is None or LAYERS[li] in allowed_goal):end=i;break
  x,y=pi%w,pi//w;mask=occ[li]
  for dx,dy,price in [(1,0,10),(-1,0,10),(0,1,10),(0,-1,10),(1,1,14),(-1,1,14),(1,-1,14),(-1,-1,14)]:
   nx,ny=x+dx,y+dy
   if not (1<=nx<w-1 and 1<=ny<h-1):continue
   np=ny*w+nx;ni=li*size+np
   if mask[np] or closed[ni] or (dx and dy and (mask[y*w+nx] or mask[ny*w+x])):continue
   push(ni,i,cost[i]+price)
  if not vocc[pi] and all(not mask[pi] for mask in occ):
   for ll in range(3):
    if ll!=li:push(ll*size+pi,i,cost[i]+250)
 if end is None:raise RuntimeError('No multilayer path for '+net)
 path=[];i=end
 while i!=-1:
  li,pi=divmod(i,size);path.append((x0+(pi%w)*step,y0+(pi//w)*step,li));i=parent[i]
 path.reverse();vias=set();length=0;points=[(*a,path[0][2])]
 for j,v in enumerate(path):
  if j==0 or j==len(path)-1 or v[2]!=path[j-1][2] or (j+1<len(path) and v[2]!=path[j+1][2]) or (round(v[0]-path[j-1][0],3),round(v[1]-path[j-1][1],3))!=(round(path[j+1][0]-v[0],3),round(path[j+1][1]-v[1],3)):
   points.append(v)
 points.append((*c,path[-1][2]))
 for u,v in zip(points,points[1:]):
  if u[2]!=v[2]:
   key=(v[0],v[1])
   if key not in vias:
    q=p.PCB_VIA(b);q.SetPosition(V(*key));q.SetWidth(p.FromMM(.7));q.SetDrill(p.FromMM(.35));q.SetViaType(p.VIATYPE_THROUGH);q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetNet(b.FindNet(net));b.Add(q);vias.add(key)
  else:track(u[:2],v[:2],net,LAYERS[u[2]]);length+=math.dist(u[:2],v[:2])
 print(net,round(length,2),'mm',len(vias),'vias',flush=True)
report=json.loads((R/'reports/a3/drc.json').read_text())
items={q.m_Uuid.AsString():q for f in b.GetFootprints() for q in f.Pads()}
items.update({t.m_Uuid.AsString():t for t in b.GetTracks()})
items.update({z.m_Uuid.AsString():z for z in b.Zones()})
connectivity=b.GetConnectivity()
def endpoints(item):
 obj=items[item['uuid']]
 if isinstance(obj,p.PCB_TRACK) and not isinstance(obj,p.PCB_VIA):return xy(obj.GetStart()),[obj.GetLayer()]
 return xy(obj.GetPosition()),None
def options(item):
 obj=items[item['uuid']]
 if isinstance(obj,p.ZONE):return [(xy(pad('H5',1).GetPosition()),None)]
 result=[endpoints(item)];seen={item['uuid']}
 for connected in connectivity.GetConnectedItems(obj):
  uid=connected.m_Uuid.AsString()
  q=items.get(uid)
  if q is None or uid in seen or isinstance(q,p.ZONE):continue
  seen.add(uid)
  if isinstance(q,p.PAD) or isinstance(q,p.PCB_VIA):result.append((xy(q.GetPosition()),None))
 return result
failed=[]
for index,v in enumerate(report['unconnected_items']):
 connectivity.Build(b)
 first,second=v['items'];net=re.search(r'\[([^\]]+)\]',first['description']).group(1)
 obj=items[first['uuid']]
 if not isinstance(obj,p.ZONE) and second['uuid'] in {q.m_Uuid.AsString() for q in connectivity.GetConnectedItems(obj)}:
  print('Already connected',index,net,flush=True);continue
 candidates=[(a,al,c,cl) for a,al in options(first) for c,cl in options(second)]
 candidates.sort(key=lambda o:math.dist(o[0],o[2]))
 for a,al,c,cl in candidates[:8]:
  try:
   route(a,c,net,al,cl);p.SaveBoard(str(PATH),b);break
  except RuntimeError:pass
 else:failed.append([index,net]);print('FAILED',index,net,flush=True)
print('Failures',failed,flush=True)
