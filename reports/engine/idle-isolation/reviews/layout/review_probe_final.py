#!/usr/bin/python3
"""Read-only independent IAC-DRAFT2 pin/copper audit. Writes only this cache dir.
Run /usr/bin/python3 .cache/engine/idle-isolated-layout-review/review_probe.py.
Centerline lengths include every intervening branch; not inductance/SPICE claims.
"""
from pathlib import Path
from collections import defaultdict,Counter,deque
import hashlib,json,xml.etree.ElementTree as ET,math,heapq,csv,sys,itertools
import pcbnew as pcb
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent/'final'
ROOT=OUT.parents[3]
SNAP=Path((OUT/'snapshot-path.txt').read_text().strip())
PROJ=SNAP/'hardware/idle-isolated'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
# Independent literal expected pin-to-net assignment, checked against primary pin
# diagrams and the intended circuit. No generator/contract import for expectations.
P={}
def pins(ref,seq):P[ref]={str(i):v if v!='NC' else None for i,v in enumerate(seq.split(),1)}
pins('J1','IDLE_CMD RUN_5V CARRIER_5V CARRIER_GND')
pins('J2','ACT_12V ACT_GND');pins('J3','ACT_12V IAC_LS')
pins('Q1','GATE IAC_LS ACT_GND')
pins('Q2','CARRIER_GND PWM_BASE PWM_LED_K');pins('Q3','CARRIER_GND RUN_BASE RUN_LED_K')
pins('U1','ENA INA ACT_GND ACT_GND NC ACT_5V2 DRIVE ACT_GND')
pins('U2','NC PWM_LED_A PWM_LED_K NC ACT_GND PWM_N ACT_5V2 ACT_5V2')
pins('U3','NC RUN_LED_A RUN_LED_K NC ACT_GND RUN_N ACT_5V2 ACT_5V2')
pins('U4','PWM_RUN PWM_N RUN_N NC ACT_GND ACT_GND ACT_GND ACT_GND ACT_GND NC ACT_GND ACT_GND NC ACT_5V2')
pins('U5','LOCAL_OK ACT_5V2 ACT_GND');pins('U6','ADJ ACT_5V2 ACT_12V')
pins('D1','ACT_12V IAC_LS');pins('D2','ACT_12V ACT_5V2')
pins('D3','PWM_BASE CARRIER_GND');pins('D4','RUN_BASE CARRIER_GND')
for i,seq in enumerate(['IDLE_CMD PWM_BASE','RUN_5V RUN_BASE','CARRIER_5V PWM_LED_A','CARRIER_5V RUN_LED_A','PWM_BASE CARRIER_GND','RUN_BASE CARRIER_GND','ACT_5V2 PWM_N','ACT_5V2 RUN_N','PWM_RUN INA','INA ACT_GND','LOCAL_OK ENA','ENA ACT_GND','DRIVE GATE','GATE ACT_GND','ACT_5V2 ADJ','ADJ ACT_GND'],1):pins('R'+str(i),seq)
for i,seq in enumerate(['ACT_5V2 ACT_GND']*5+['ACT_12V ACT_GND','ACT_5V2 ACT_GND','ACT_12V ACT_GND','CARRIER_5V CARRIER_GND'],1):pins('C'+str(i),seq)
pins('C10','ACT_5V2 LOGIC_GND')
for ref in ['U1','U2','U3','U4','U5','U6','R10','R12','R16','C1','C2','C3','C4','C5','C7','C8']:
 P[ref]={n:'LOGIC_GND' if v=='ACT_GND' else v for n,v in P[ref].items()}
pins('NT1','ACT_GND LOGIC_GND')
for i in range(1,5):P['H'+str(i)]={}
manifest=json.loads((SNAP/'snapshot-manifest.json').read_text())
assert all(sha(SNAP/p)==h for p,h in manifest['files'].items())
working=OUT/'native-working-copy'
assert all(sha(p)==sha(working/p.relative_to(PROJ)) for p in PROJ.rglob('*') if p.is_file())
b=pcb.LoadBoard(str(PROJ/'isolated.kicad_pcb'))
edges=[(tuple(d.GetStart()),tuple(d.GetEnd())) for d in b.GetDrawings() if d.GetLayer()==pcb.Edge_Cuts]
assert {frozenset(e) for e in edges}=={frozenset(e) for e in [((10000000,10000000),(100000000,10000000)),((100000000,10000000),(100000000,70000000)),((100000000,70000000),(10000000,70000000)),((10000000,70000000),(10000000,10000000))]}
assert b.GetDesignSettings().GetBoardThickness()==1600000 and b.GetCopperLayerCount()==2
FP={fp.GetReference():fp for fp in b.GetFootprints()}
assert len(FP)==len(list(b.GetFootprints()))==47
assert set(FP)==set(P)
contract=json.loads((PROJ/'net_contract.json').read_text())
assert {p['reference']:p['pins'] for p in contract['parts']}==P
xml=ET.parse(OUT/'schematic-netlist.xml').getroot()
S=defaultdict(dict)
for n in xml.findall('./nets/net'):
 for pd in n.findall('node'):S[pd.attrib['ref']][pd.attrib['pin']]=n.attrib['name']
assert set(S)==set(P)-{'H1','H2','H3','H4'}
actual={};inventory=[];npth=[]
for ref,fp in sorted(FP.items()):
 actual[ref]={}
 for pd in fp.Pads():
  no=pd.GetNumber();net=pd.GetNetname()
  if not no:
   assert ref.startswith('H') and pd.GetAttribute()==pcb.PAD_ATTRIB_NPTH
   npth.append(ref);continue
  expected=P[ref][no]
  assert net==S[ref][no]
  assert net==expected if expected is not None else net.startswith('unconnected-')
  assert pd.GetAttribute()==(pcb.PAD_ATTRIB_SMD if ref=='NT1' else pcb.PAD_ATTRIB_PTH)
  actual[ref][no]=pd
  inventory.append(dict(reference=ref,value=fp.GetValue(),pin=no,net=net,expected_net=expected,
    x_mm=pd.GetPosition().x/1e6,y_mm=pd.GetPosition().y/1e6,
    pad_mm=[pd.GetSize().x/1e6,pd.GetSize().y/1e6],
    drill_mm=[pd.GetDrillSize().x/1e6,pd.GetDrillSize().y/1e6],
    footprint=str(fp.GetFPID().GetLibNickname())+':'+str(fp.GetFPID().GetLibItemName())))
 assert set(actual[ref])==set(P[ref])
# Rule area and actual copper extents: conservative axis-aligned bounding boxes.
carrier={'CARRIER_5V','CARRIER_GND','IDLE_CMD','RUN_5V','PWM_BASE','RUN_BASE','PWM_LED_A','PWM_LED_K','RUN_LED_A','RUN_LED_K'}
actuator={v for m in P.values() for v in m.values() if v is not None}-carrier
zones=list(b.Zones());assert len(zones)==1
z=zones[0];assert z.GetIsRuleArea() and all([z.GetDoNotAllowTracks(),z.GetDoNotAllowVias(),z.GetDoNotAllowCopperPour(),z.GetDoNotAllowPads()])
assert z.GetLayerSet().Contains(pcb.F_Cu) and z.GetLayerSet().Contains(pcb.B_Cu)
zb=z.Outline().BBox();assert (zb.GetLeft(),zb.GetTop(),zb.GetRight(),zb.GetBottom())==(35300000,10000000,40300000,70000000)
track_records=[];objects=[];via_records=[]
for t in b.GetTracks():
 if isinstance(t,pcb.PCB_VIA):
  via_records.append(dict(net=t.GetNetname(),position=[t.GetPosition().x/1e6,t.GetPosition().y/1e6],diameter_mm=t.GetWidth(pcb.F_Cu)/1e6,drill_mm=t.GetDrillValue()/1e6,locked=t.IsLocked()))
  objects.append((t.GetNetname(),t.GetBoundingBox(),t.GetClass()));continue
 track_records.append(dict(net=t.GetNetname(),layer=pcb.LayerName(t.GetLayer()),width_mm=t.GetWidth()/1e6,locked=t.IsLocked(),start=[t.GetStart().x/1e6,t.GetStart().y/1e6],end=[t.GetEnd().x/1e6,t.GetEnd().y/1e6]))
 objects.append((t.GetNetname(),t.GetBoundingBox(),t.GetClass()))
for row in inventory:
 pd=actual[row['reference']][row['pin']]
 if row['net'].startswith('unconnected-'):
  # NC pins are physically on their appropriate package side.
  dom=carrier if row['reference'] in ['U2','U3'] else actuator
  objects.append(('__carrier_nc' if dom is carrier else '__actuator_nc',pd.GetBoundingBox(),row['reference']+'.'+row['pin']))
 else:objects.append((row['net'],pd.GetBoundingBox(),row['reference']+'.'+row['pin']))
left=[];right=[]
for net,box,desc in objects:
 if net in carrier or net=='__carrier_nc':
  assert box.GetRight()<=35300000,(net,desc,box.GetRight())
  left.append((box.GetRight(),desc,net))
 elif net in actuator or net=='__actuator_nc':
  assert box.GetLeft()>=40300000,(net,desc,box.GetLeft())
  right.append((box.GetLeft(),desc,net))
 else:raise AssertionError(net)
leftmax=max(left);rightmin=min(right)
# Verify all manually seeded power segments survive exactly as broad, locked copper.
seed=[('ACT_12V','B.Cu',[(90,23),(90,30),(98.5,38.5),(98.5,53),(90,53),(90,57)]),('ACT_12V','F.Cu',[(70,15),(73,18),(85,18),(90,23)]),('IAC_LS','F.Cu',[(85.24,15),(89,15),(93.96,19.96),(93.96,23),(93.96,29.3),(92.54,30.72),(92.54,39)]),('ACT_GND','F.Cu',[(95.08,39),(95.08,57)])]
retained=[]
for net,layer,path in seed:
 for start,end in zip(path,path[1:]):
  match=[t for t in track_records if t['net']==net and t['layer']==layer and t['width_mm']==2 and t['locked'] and {tuple(t['start']),tuple(t['end'])}=={start,end}]
  assert len(match)==1,(net,layer,start,end)
  retained+=match
assert len(retained)==15
# Conservative DC graph: every ordinary part can connect all its non-NC pins.
# Only optical input/output groups remain separate. No optical component short.
graph=defaultdict(set)
for ref,m in P.items():
 groups=[['2','3'],['5','6','7','8']] if ref in ['U2','U3'] else [list(m)]
 for group in groups:
  nets=[m[p] for p in group if m[p] is not None]
  for n in nets:graph[n].update(nets)
def reach(start,graph):
 seen={start};todo=[start]
 while todo:
  for n in graph[todo.pop()]-seen:seen.add(n);todo.append(n)
 return seen
assert not (reach('ACT_GND',graph)&carrier)
negative={n:set(v) for n,v in graph.items()}
negative['ACT_GND'].add('CARRIER_GND');negative['CARRIER_GND'].add('ACT_GND')
assert reach('ACT_GND',negative)&carrier
# Independent track graph, with splits at collinear endpoints and same-net crossings.
# PTH pads connect F/B at their centers. Centerline lengths include no package wires.
G=defaultdict(list);nets={t.GetNetname() for t in b.GetTracks()}
def point(v):return (round(v.x/1e6,6),round(v.y/1e6,6))
def edge(a,z,w):G[a].append((z,w));G[z].append((a,w))
def on(q,a,z):
 dx,dy=z[0]-a[0],z[1]-a[1];t=((q[0]-a[0])*dx+(q[1]-a[1])*dy)/(dx*dx+dy*dy)
 return -1e-6<=t<=1+1e-6 and abs((q[0]-a[0])*dy-(q[1]-a[1])*dx)<1e-5
for net in nets:
 ts=[t for t in b.GetTracks() if t.GetNetname()==net and not isinstance(t,pcb.PCB_VIA)]
 for layer in [pcb.F_Cu,pcb.B_Cu]:
  segs=[(point(t.GetStart()),point(t.GetEnd())) for t in ts if t.GetLayer()==layer]
  pts={v for s in segs for v in s}
  pts.update(point(pd.GetPosition()) for m in actual.values() for pd in m.values() if pd.GetNetname()==net)
  for a,z in segs:
   split=sorted((q for q in pts if on(q,a,z)),key=lambda q:math.dist(q,a))
   for u,v in zip(split,split[1:]):edge((net,layer,*u),(net,layer,*v),math.dist(u,v))
 for m in actual.values():
  for pd in m.values():
   if pd.GetNetname()==net and pd.GetAttribute()==pcb.PAD_ATTRIB_PTH:
    xy=point(pd.GetPosition());edge((net,pcb.F_Cu,*xy),(net,pcb.B_Cu,*xy),0)
for t in b.GetTracks():
 if isinstance(t,pcb.PCB_VIA):
  xy=point(t.GetPosition());net=t.GetNetname();edge((net,pcb.F_Cu,*xy),(net,pcb.B_Cu,*xy),0)
# Front/back PTH capacitor pads may intentionally touch same-net IC pads.
# Include native shape overlap; pad-center separation is a conservative center
# path convention, not a measured length of separate trace between those pads.
pad_contacts=[]
for net in nets:
 pads=[(ref,no,pd) for ref,m in actual.items() for no,pd in m.items() if pd.GetNetname()==net]
 for i,(ar,an,a) in enumerate(pads):
  for zr,zn,z in pads[i+1:]:
   for layer in [pcb.F_Cu,pcb.B_Cu]:
    if a.IsOnLayer(layer) and z.IsOnLayer(layer) and a.GetEffectiveShape(layer).Collide(z.GetEffectiveShape(layer),0):
     ap,zp=point(a.GetPosition()),point(z.GetPosition());edge((net,layer,*ap),(net,layer,*zp),math.dist(ap,zp))
     pad_contacts.append(dict(net=net,from_pin=ar+'.'+an,to_pin=zr+'.'+zn,layer=pcb.LayerName(layer),center_separation_mm=math.dist(ap,zp)))
# NT1 is exactly one intentional, unfitted F.Cu connection at Q1 source.
tie_text=(PROJ/'lib/ecu.pretty/NetTie_Source_Star.kicad_mod').read_text()
assert '(net_tie_pad_groups "1,2")' in tie_text
assert FP['NT1'].GetAttributes() & pcb.FP_BOARD_ONLY and FP['NT1'].GetAttributes() & pcb.FP_EXCLUDE_FROM_BOM
assert point(actual['NT1']['1'].GetPosition())==point(actual['Q1']['3'].GetPosition())==(95.08,39)
assert point(actual['NT1']['2'].GetPosition())==(96.88,39)
tie_graphics=list(FP['NT1'].GraphicalItems());assert len(tie_graphics)==1
tg=tie_graphics[0];assert tg.GetLayer()==pcb.F_Cu and point(tg.GetStart())==(95.08,39) and point(tg.GetEnd())==(96.88,39) and tg.GetWidth()==600000
edge(('ACT_GND',pcb.F_Cu,95.08,39),('LOGIC_GND',pcb.F_Cu,96.88,39),1.8)
physical_cross_contacts=[]
copper=[(ref+'.'+no,pd) for ref,m in actual.items() for no,pd in m.items() if pd.GetNetname() in ['ACT_GND','LOGIC_GND']]+[(str(t.m_Uuid.AsString()),t) for t in b.GetTracks() if t.GetNetname() in ['ACT_GND','LOGIC_GND']]
for i,(an,a) in enumerate(copper):
 for zn,z in copper[i+1:]:
  if a.GetNetname()==z.GetNetname():continue
  for layer in [pcb.F_Cu,pcb.B_Cu]:
   if a.IsOnLayer(layer) and z.IsOnLayer(layer) and a.GetEffectiveShape(layer).Collide(z.GetEffectiveShape(layer),0):physical_cross_contacts.append(dict(a=an,z=zn,layer=pcb.LayerName(layer)))
assert not physical_cross_contacts,physical_cross_contacts
def route(a,z):
 ap=actual[a[0]][str(a[1])];zp=actual[z[0]][str(z[1])]
 net=ap.GetNetname();start=(net,pcb.F_Cu,*point(ap.GetPosition()));end=(zp.GetNetname(),pcb.F_Cu,*point(zp.GetPosition()))
 todo=[(0,start)];dist={start:0};parent={}
 while todo:
  d,u=heapq.heappop(todo)
  if d!=dist[u]:continue
  if u==end:break
  for v,w in G[u]:
   nd=d+w
   if nd<dist.get(v,float('inf')):dist[v]=nd;parent[v]=u;heapq.heappush(todo,(nd,v))
 assert end in dist,(a,z)
 path=[end]
 while path[-1]!=start:path.append(parent[path[-1]])
 return dict(from_pin='.'.join(map(str,a)),to_pin='.'.join(map(str,z)),net=net,length_mm=dist[end],path=list(reversed(path)))
lengths={}
for ic,cap,vdd,gnd in [('U2','C1',8,5),('U3','C2',8,5),('U4','C3',14,7),('U1','C4',6,3),('U5','C5',2,3),('U1','C10',6,3)]:
 rail=route((ic,vdd),(cap,1));ret=route((cap,2),(ic,gnd));lengths[ic+'_'+cap]=dict(rail=rail,return_path=ret,total_copper_mm=rail['length_mm']+ret['length_mm'])
for name,a,z in [('driver_to_fet_return',('U1',3),('Q1',3)),('driver_output_to_gate_resistor',('U1',7),('R13',1)),('gate_resistor_to_fet',('R13',2),('Q1',1)),('driver_to_bulk_rail',('U1',6),('C7',1)),('driver_to_bulk_return',('C7',2),('U1',3)),('fet_source_to_supply_return',('Q1',3),('J2',2)),('flyback_plus',('D1',1),('J3',1)),('flyback_low',('D1',2),('J3',2))]:lengths[name]=route(a,z)
# Disconnect only the broad vertical source-to-J2 bus in the analysis graph.
# Which points on that bus does the driver/logic copper touch independently?
# This detects a second connection that could put logic copper in parallel with
# part of the coil-return bus. It does not simulate currents or inductance.
def is_bus_edge(u,v,w):
 return w>0 and u[0]==v[0]=='ACT_GND' and u[1]==v[1]==pcb.F_Cu and abs(u[2]-95.08)<1e-6 and abs(v[2]-95.08)<1e-6 and 39<=u[3]<=57 and 39<=v[3]<=57
bus_nodes={u for u,adj in G.items() for v,w in adj if is_bus_edge(u,v,w)}
start=('LOGIC_GND',pcb.F_Cu,*point(actual['U1']['3'].GetPosition()))
seen={start};todo=[start]
while todo:
 u=todo.pop()
 for v,w in G[u]:
  if v not in seen and not is_bus_edge(u,v,w):seen.add(v);todo.append(v)
star_contacts=sorted({tuple(u[2:]) for u in bus_nodes&seen});assert star_contacts==[(95.08,39)],star_contacts
# Independent truth table including local-rail validity gate. DC only.
truth=[]
for pwm in [0,1]:
 for run in [0,1]:
  for pg in [0,1]:truth.append(dict(pwm_led=pwm,run_led=run,local_ok=pg,pwm_n=1-pwm,run_n=1-run,nor=pwm&run,drive=pwm&run&pg))
# Fresh arithmetic, using the primary full-temperature LM317A bounds.
corners=[dict(vref=vref,r1=r1,r2=r2,iadj=iadj,vout=vref*(1+r2/r1)+iadj*r2) for vref,r1,r2,iadj in itertools.product([1.225,1.270],[120*.99,120*1.01],[374*.99,374*1.01],[0,.0001])]
railmin=min(c['vout'] for c in corners);railmax=max(c['vout'] for c in corners)
arithmetic=dict(regulator_corners=corners,rail_range_v=[railmin,railmax],divider_min_load_a=1.225/(120*1.01),headroom_at_9v_v=9-railmax,rail_above_max_supervisor_trip_v=railmin-4.85,rail_below_5p5_v=5.5-railmax,led_conditional_current_a=[(4.75-1.7-.3)/(357*1.01),5.25/(357*.99)],assumptions=['Carrier rail4.75..5.25V, LEDVF<=1.7V and NPNVCEsat<=0.3V are conditional operating assumptions','No loadedGPIO or full-temperature NPN guarantee asserted'])
# Provenance checks against archived hashes; never regenerate the board.
sys.path.insert(0,str(SNAP/'scripts'))
from kicad9_carrier_copy import footprint_copy
origins=json.loads((PROJ/'footprint-provenance.json').read_text());prov=[]
for stem,row in origins.items():
 target=PROJ/'lib/ecu.pretty'/(stem+'.kicad_mod')
 if 'source_sha256' in row:
  src=ROOT/row['source'];assert sha(src)==row['source_sha256']
  converted,removed=footprint_copy(src.read_bytes())
  assert sha(target)==row['copy_sha256']
  # Only the named silkscreen graphics and the footprint name may differ.
  if stem.endswith('_BackAssembly') or stem.endswith('_BypassClearSilk'):
   from kicad9_carrier_copy import chunks
   text=converted.decode();count=0
   for kind in ('fp_line','fp_arc','fp_circle','fp_poly','fp_text'):
    for start,end,block in reversed(list(chunks(text,kind))):
     if '(layer "F.SilkS")' in block and (stem.endswith('_BackAssembly') or kind=='fp_line'):text=text[:start]+text[end:];count+=1
   base=Path(row['source']).stem;text=text.replace('(footprint "'+base+'"','(footprint "'+stem+'"',1);converted=text.encode()
   removed['back_assembly_silkscreen_graphics' if stem.endswith('_BackAssembly') else 'front_bypass_outline_lines']=count
  assert converted==target.read_bytes() and removed==row['omitted_metadata']
 else:assert sha(target)==row['sha256']
 prov.append(dict(footprint=stem,hashes_verified=True,origin=row))
# Reviewer image rendered directly from actual KiCad coordinates, engineering aid.
def draw_board(name,layers,box=(9,9,101,71),scale=22):
 x0,y0,x1,y1=box;im=Image.new('RGB',(round((x1-x0)*scale),round((y1-y0)*scale)),(248,248,244));d=ImageDraw.Draw(im)
 xy=lambda pt:((pt[0]-x0)*scale,(pt[1]-y0)*scale)
 d.rectangle((*xy((35.3,10)),*xy((40.3,70))),fill=(246,236,211))
 for layer,color in [(pcb.B_Cu,(43,97,180)),(pcb.F_Cu,(193,67,61))]:
  if layer not in layers:continue
  for t in b.GetTracks():
   if isinstance(t,pcb.PCB_VIA):continue
   if t.GetLayer()==layer:d.line([xy(point(t.GetStart())),xy(point(t.GetEnd()))],fill=color,width=max(1,round(t.GetWidth()/1e6*scale)))
 for ref,fp in FP.items():
  for pd in fp.Pads():
   x,y=point(pd.GetPosition());sx,sy=pd.GetSize().x/1e6,pd.GetSize().y/1e6
   corners=(*xy((x-sx/2,y-sy/2)),*xy((x+sx/2,y+sy/2)))
   d.ellipse(corners,fill=(184,152,38),outline=(55,55,55))
   dx,dy=pd.GetDrillSize().x/1e6,pd.GetDrillSize().y/1e6
   d.ellipse((*xy((x-dx/2,y-dy/2)),*xy((x+dx/2,y+dy/2))),fill=(248,248,244))
   if pd.GetNumber():d.text(xy((x-.18,y-.23)),pd.GetNumber(),fill=(0,0,0))
  px,py=point(fp.GetPosition());d.text(xy((px-1,py-2.2)),ref,fill=(0,0,0))
 d.rectangle((*xy((10,10)),*xy((100,70))),outline=(20,20,20),width=2)
 im.save(OUT/name)
draw_board('actual-board.png',[pcb.F_Cu,pcb.B_Cu]);draw_board('actual-driver-loop.png',[pcb.F_Cu,pcb.B_Cu],(70,33,100,58),36)
with (OUT/'all-pins.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
summary=dict(snapshot_bundle_sha256=manifest['bundle_sha256'],pcb_sha256=sha(PROJ/'isolated.kicad_pcb'),native_version=pcb.GetBuildVersion(),all_reference_count=len(FP),electrical_reference_count=len(S),electrical_pin_count=len(inventory),mounting_holes=npth,board_mm=[90,60],copper_layers=b.GetCopperLayerCount(),all_fitted_electrical_pads_PTH=True,unfitted_copper_tie_reference='NT1',unfitted_copper_tie_pad_count=2,fitted_electrical_pin_count=sum(1 for r in inventory if r['reference']!='NT1'),drill_minmax_mm=[min(r['drill_mm'][0] for r in inventory if r['reference']!='NT1'),max(r['drill_mm'][0] for r in inventory)],via_count=len(via_records),vias=via_records,explicit_return_star_at_source=True,physical_ACT_GND_LOGIC_GND_shorts_outside_NT1=physical_cross_contacts,track_count=len(track_records),same_net_pad_copper_contacts=pad_contacts,track_width_counts=Counter(t['width_mm'] for t in track_records),actual_copper_extents=dict(carrier_right_mm=leftmax[0]/1e6,actuator_left_mm=rightmin[0]/1e6,horizontal_gap_lower_bound_mm=(rightmin[0]-leftmax[0])/1e6),barrier_rule_area_mm=[35.3,10,40.3,70],carrier_to_actuator_DC_path=False,deliberate_ground_bridge_negative_control=True,power_segments_2mm_locked_retained=len(retained),driver_logic_contacts_on_source_to_J2_power_bus_mm=star_contacts,copper_path_lengths=lengths,truth_table=truth,independent_arithmetic=arithmetic,footprint_provenance=prov,limitations=['Conservative static graph, not fault/semiconductor simulation','Track-centerline lengths exclude internal package wires, solder/lead inductance and broad-pad shortcuts','No physical fit, current capacity, thermal, EMI, brownout/timing or certified isolation acceptance'])
(OUT/'probe-result.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['copper_path_lengths','footprint_provenance','truth_table','independent_arithmetic']},indent=2))
print('CENTERLINE COPPER LENGTHS')
for k,v in lengths.items():print(k,round(v.get('total_copper_mm',v.get('length_mm')),3))
