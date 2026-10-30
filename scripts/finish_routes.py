#!/usr/bin/env python3
"""Finish residual A0 logic routes on In2.Cu using a conservative grid search.

This is a project repair utility, not a general PCB router. It reads the actual
KiCad DRC report, preserves other nets, and must be followed by check_hardware.sh.
"""
from array import array
import heapq
import json
import math
from pathlib import Path
import re
import pcbnew as p

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"hardware/esp32-ecu.kicad_pcb"
board=p.LoadBoard(str(PATH))
step=.2
width=1001
size=width*width


def xy(v):return v.x/1e6,v.y/1e6
def vec(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def distance_to_segment(x,y,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)


def clear(x,y,r,net,layer):
    if not (10.5+r<x<209.5-r and 10.5+r<y<209.5-r):return False
    for f in board.GetFootprints():
        for pad in f.Pads():
            if not pad.GetNumber() or not pad.IsOnLayer(layer) or pad.GetNetname()==net:continue
            b=pad.GetBoundingBox()
            dx=max(b.GetX()/1e6-x,0,x-b.GetRight()/1e6)
            dy=max(b.GetY()/1e6-y,0,y-b.GetBottom()/1e6)
            if math.hypot(dx,dy)<r:return False
    for t in board.GetTracks():
        if t.GetNetname()==net:continue
        if isinstance(t,p.PCB_VIA):
            a=xy(t.GetPosition())
            if math.hypot(x-a[0],y-a[1])<r+t.GetWidth(p.F_Cu)/2e6:return False
        elif t.GetLayer()==layer:
            if distance_to_segment(x,y,xy(t.GetStart()),xy(t.GetEnd()))<r+t.GetWidth()/2e6:return False
    return True


def track(a,b,net,layer,mm=.25):
    if math.dist(a,b)<.001:return
    t=p.PCB_TRACK(board);t.SetStart(vec(*a));t.SetEnd(vec(*b))
    t.SetWidth(p.FromMM(mm));t.SetLayer(layer);t.SetNet(board.FindNet(net));board.Add(t)


def escape(ref,n,net):
    f=board.FindFootprintByReference(ref)
    pad=next(pad for pad in f.Pads() if pad.GetNumber()==str(n))
    a=xy(pad.GetPosition())
    if pad.IsOnLayer(p.B_Cu):return a
    for radius in [1.2,1.6,2,2.6,3.2,4]:
        for i in range(32):
            angle=i*math.pi/16
            v=(round((a[0]+radius*math.cos(angle))/step)*step,
               round((a[1]+radius*math.sin(angle))/step)*step)
            if not all(clear(*v,.56,net,l) for l in [p.F_Cu,p.In2_Cu,p.B_Cu]):continue
            if not all(clear(a[0]+(v[0]-a[0])*j/40,a[1]+(v[1]-a[1])*j/40,.335,net,p.F_Cu) for j in range(41)):continue
            via=p.PCB_VIA(board);via.SetPosition(vec(*v));via.SetWidth(p.FromMM(.7));via.SetDrill(p.FromMM(.35))
            via.SetViaType(p.VIATYPE_THROUGH);via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetNet(board.FindNet(net));board.Add(via)
            track(a,v,net,p.F_Cu)
            return v
    raise RuntimeError(f"Cannot escape {ref}:{n}")


def route(a,b,net,layer=p.In2_Cu):
    occupied=bytearray(size)
    def point(v):return (round((v[0]-10)/step),round((v[1]-10)/step))
    def disk(v,r):
        cx,cy=point(v);rr=math.ceil((r+.15)/step)
        for y in range(max(0,cy-rr),min(width,cy+rr+1)):
            dy=(y-cy)*step
            for x in range(max(0,cx-rr),min(width,cx+rr+1)):
                if ((x-cx)*step)**2+dy*dy<=(r+.15)**2:occupied[y*width+x]=1
    for f in board.GetFootprints():
        for pad in f.Pads():
            if not pad.GetNumber() or not pad.IsOnLayer(layer) or pad.GetNetname()==net:continue
            box=pad.GetBoundingBox()
            l,t=point((box.GetX()/1e6-.45,box.GetY()/1e6-.45))
            r,bottom=point((box.GetRight()/1e6+.45,box.GetBottom()/1e6+.45))
            for y in range(max(0,t),min(width,bottom+1)):
                occupied[y*width+max(0,l):y*width+min(width,r+1)]=b'\x01'*(min(width,r+1)-max(0,l))
    for t in board.GetTracks():
        if t.GetNetname()==net:continue
        if isinstance(t,p.PCB_VIA):disk(xy(t.GetPosition()),t.GetWidth(layer)/2e6+.335)
        elif t.GetLayer()==layer:
            start,end=xy(t.GetStart()),xy(t.GetEnd());samples=max(1,math.ceil(math.dist(start,end)/step*2))
            for j in range(samples+1):disk((start[0]+(end[0]-start[0])*j/samples,start[1]+(end[1]-start[1])*j/samples),t.GetWidth()/2e6+.335)
    start=point(a);goal=point(b);si=start[1]*width+start[0];gi=goal[1]*width+goal[0]
    if occupied[si] or occupied[gi]:raise RuntimeError(f"Blocked route endpoint: {net}")
    parent=array('i',[-1])*size;cost=array('I',[0xffffffff])*size;cost[si]=0
    heap=[(0,si)];closed=bytearray(size)
    while heap:
        _,i=heapq.heappop(heap)
        if closed[i]:continue
        closed[i]=1
        if i==gi:break
        x,y=i%width,i//width
        for dx,dy,w in [(1,0,10),(-1,0,10),(0,1,10),(0,-1,10),(1,1,14),(-1,1,14),(1,-1,14),(-1,-1,14)]:
            nx,ny=x+dx,y+dy
            if not (4<=nx<width-4 and 4<=ny<width-4):continue
            ni=ny*width+nx
            if occupied[ni] or closed[ni]:continue
            if dx and dy and (occupied[y*width+nx] or occupied[ny*width+x]):continue
            nc=cost[i]+w
            if nc>=cost[ni]:continue
            parent[ni]=i;cost[ni]=nc
            gx,gy=abs(nx-goal[0]),abs(ny-goal[1])
            heapq.heappush(heap,(nc+10*max(gx,gy)+4*min(gx,gy),ni))
    if not closed[gi]:raise RuntimeError(f"No B.Cu path for {net}")
    path=[];i=gi
    while i!=-1:
        path.append((10+(i%width)*step,10+(i//width)*step));i=parent[i]
    path.reverse()
    points=[a]
    for i,v in enumerate(path):
        if i==0 or i==len(path)-1 or (round(path[i][0]-path[i-1][0],3),round(path[i][1]-path[i-1][1],3)) != (round(path[i+1][0]-path[i][0],3),round(path[i+1][1]-path[i][1],3)):
            points.append(v)
    points.append(b)
    for start,end in zip(points,points[1:]):track(start,end,net,layer)
    print("Finished",net,"with",len(points)-1,"In2.Cu segments")


report=json.loads((ROOT/"reports/drc.json").read_text())
missing={re.search(r'\[([^\]]+)\]',v['items'][0]['description']).group(1) for v in report['unconnected_items']}
dangling={}
for v in report['violations']:
    if v['type']=="via_dangling":
        net=re.search(r'\[([^\]]+)\]',v['items'][0]['description']).group(1)
        pos=v['items'][0]['pos'];dangling[net]=(pos['x'],pos['y'])
plans={"IGN1_WINDOW":(("U11",2),("U14",13)),"IGN2_WINDOW":(("U11",5),("U14",5)),
       "IGN4_WINDOW":(("U11",10),("U15",5)),"IGN2_5V":(("R112",2),("J10",2))}
for net in sorted(missing):
    if net not in plans:raise RuntimeError("Unreviewed residual net: "+net)
    start,end=plans[net]
    a=dangling[net] if net in dangling else escape(*start,net)
    b=escape(*end,net)
    route(a,b,net)
if missing:p.SaveBoard(str(PATH),board)
