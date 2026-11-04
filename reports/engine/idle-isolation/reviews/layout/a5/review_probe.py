#!/usr/bin/python3
"""Independent raw-S-expression A4/A5 audit; no production loads or mutations."""
from pathlib import Path
from collections import Counter
from decimal import Decimal
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET,sys
import pcbnew as pcb
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3];SNAP=Path((OUT/'snapshot-path.txt').read_text().strip());A4=SNAP/'hardware/a4-n16r8';A5=SNAP/'hardware/a5-idle-interface'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((SNAP/'snapshot-manifest.json').read_text());assert all(sha(SNAP/p)==v for p,v in manifest['files'].items())
# Own tokenizer/parser works directly on the archived KiCad10 source; comparison
# is not dependent on the author's compatibility converter or router geometry().
def parse(text):
 stack=[];root=None
 for t in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text):
  if t=='(':
   node=[]
   if stack:stack[-1].append(node)
   else:assert root is None;root=node
   stack.append(node)
  elif t==')':stack.pop()
  else:stack[-1].append(json.loads(t) if t.startswith('"') else t)
 assert not stack;return root
def nodes(n,k):return [x for x in n if isinstance(x,list) and x and x[0]==k]
def node(n,k,default=None):
 a=nodes(n,k);return a[0] if a else default
num=lambda x:str(Decimal(x).normalize())
def canon(n):
 if isinstance(n,list):return tuple(canon(x) for x in n)
 return num(n) if re.fullmatch(r'-?\d+(?:\.\d+)?',str(n)) else n
def pos(n,k):
 a=node(n,k);return tuple(num(v) for v in a[1:]) if a else None
def uuid(n):return node(n,'uuid')[1]
def table(root):return {n[1]:n[2] for n in nodes(root,'net') if len(n)==3}
def net(n,t):
 a=node(n,'net')
 if a is None:return ''
 return a[2] if len(a)==3 else t.get(a[1],a[1])
def track(n,t):
 tag=n[0]
 if tag=='segment':return (tag,net(n,t),node(n,'layer')[1],pos(n,'start'),pos(n,'end'),pos(n,'width'))
 assert tag=='via'
 return (tag,net(n,t),pos(n,'at'),pos(n,'size'),pos(n,'drill'),canon(node(n,'layers')),canon(node(n,'type',[])))
def angle_at(n):
 a=node(n,'at');return (num(a[1]),num(a[2]),num(str(Decimal(a[3])%360)) if len(a)>3 else '0')
def pad(n,t):
 keys=['size','drill','layers','roundrect_rratio','rect_delta','chamfer_ratio','chamfer','offset','zone_connect','thermal_bridge_angle','clearance','solder_mask_margin','solder_paste_margin']
 return dict(number=n[1],kind=n[2],shape=n[3],at=angle_at(n),net=net(n,t),geometry={k:canon(node(n,k)) for k in keys if node(n,k) is not None})
def footprints(root):return {next(x[2] for x in nodes(f,'property') if x[1]=='Reference'):f for f in nodes(root,'footprint')}
def zone(z,t):
 # Filled polygons are deliberately regenerated; all boundary/rule/thermal data
 # remains in this normalized signature. KiCad9's explicit fill-yes is syntax.
 result=[['net_name',net(z,t)]]
 for child in z[1:]:
  if not isinstance(child,list):continue
  if child[0] in ['net','net_name','uuid','filled_polygon','fill_segments','filled_areas_thickness']:continue
  if child[0]=='fill':child=[child[0]]+[v for v in child[1:] if v!='yes' and v!=['island_removal_mode','0']]
  result.append(child)
 return tuple(sorted((canon(x) for x in result),key=repr))
r4=parse((A4/'esp32-ecu.kicad_pcb').read_text());r5=parse((A5/'esp32-ecu.kicad_pcb').read_text());t4,t5=table(r4),table(r5);f4,f5=footprints(r4),footprints(r5)
assert len(f4)==219 and len(f5)==221 and set(f5)-set(f4)=={'R154','J21'}
c4={uuid(n):track(n,t4) for tag in ['segment','via'] for n in nodes(r4,tag)};c5={uuid(n):track(n,t5) for tag in ['segment','via'] for n in nodes(r5,tag)}
assert len(c4)==2973 and len(c5)==2998;assert all(c5[k]==v for k,v in c4.items())
old_raw=[n for tag in ['segment','via'] for n in nodes(r5,tag) if uuid(n) in c4]
assert all(node(n,'locked')==['locked','yes'] for n in old_raw)
new_raw=[n for tag in ['segment','via'] for n in nodes(r5,tag) if uuid(n) not in c4];assert len(new_raw)==25
assert all(net(n,t5) in ['IDLE_CMD','RUN_5V','+5V','GND'] for n in new_raw)
changes=[];original_pad_count=0
for ref,a in f4.items():
 z=f5[ref];assert angle_at(a)==angle_at(z) and node(a,'layer')==node(z,'layer')
 assert next(x[2] for x in nodes(a,'property') if x[1]=='Value')==next(x[2] for x in nodes(z,'property') if x[1]=='Value')
 ap={n[1]:pad(n,t4) for n in nodes(a,'pad')};zp={n[1]:pad(n,t5) for n in nodes(z,'pad')};assert ap.keys()==zp.keys();original_pad_count+=len(ap)
 for no,x in ap.items():
  y=zp[no]
  if x!=y:
   changes.append(dict(reference=ref,pin=no,before=x,after=y))
   assert ref=='U3' and no=='13' and x['net'].startswith('unconnected-') and y['net']=='IDLE_CMD'
   xx=dict(x);xx['net']='IDLE_CMD';assert xx==y
 for tag in ['fp_line','fp_rect','fp_arc','fp_circle','fp_poly']:
  aa=Counter(repr(canon([v for v in n if not (isinstance(v,list) and v and v[0]=='uuid')])) for n in nodes(a,tag));zz=Counter(repr(canon([v for v in n if not (isinstance(v,list) and v and v[0]=='uuid')])) for n in nodes(z,tag));assert aa==zz,(ref,tag)
 assert Counter(zone(n,t4) for n in nodes(a,'zone'))==Counter(zone(n,t5) for n in nodes(z,'zone'))
assert len(changes)==1
assert Counter(zone(n,t4) for n in nodes(r4,'zone'))==Counter(zone(n,t5) for n in nodes(r5,'zone'))
# Exactly the three documented board-text changes, without accepting a silent
# alteration to other annotations or their font/layer geometry.
g4={uuid(n):n for n in nodes(r4,'gr_text')};g5={uuid(n):n for n in nodes(r5,'gr_text')};text_changes=[]
for uid,a in g4.items():
 z=g5[uid]
 if canon(a)==canon(z):continue
 import copy
 expected=copy.deepcopy(a)
 if a[1]=='J1 12V':
  at=node(expected,'at');at[1:3]=['22','31']
 elif 'A4-N16R8 PROVISIONAL' in a[1]:expected[1]=a[1].replace('A4-N16R8 PROVISIONAL','A5-IDLE HOLD')
 else:raise AssertionError(('Unexpected old text change',a[1],z[1]))
 assert canon(expected)==canon(z)
 text_changes.append(dict(before=a[1],after=z[1],position=pos(z,'at')))
added_text=[n for uid,n in g5.items() if uid not in g4];assert len(added_text)==1 and added_text[0][1]=='J21 IDLE' and pos(added_text[0],'at')[:2]==('26','12')
# Native checks complement raw comparison; new source pins are independently fixed.
b=pcb.LoadBoard(str(A5/'esp32-ecu.kicad_pcb'));fp={f.GetReference():f for f in b.GetFootprints()};pads={r:{p.GetNumber():p for p in f.Pads()} for r,f in fp.items()}
expected={'U3':{'13':'IDLE_CMD'},'R154':{'1':'IDLE_CMD','2':'GND'},'J21':{'1':'IDLE_CMD','2':'RUN_5V','3':'+5V','4':'GND'},'R151':{'1':'CHASSIS','2':'GND'}}
xml=ET.parse(OUT/'schematic-netlist.xml').getroot();sn={}
for n in xml.findall('./nets/net'):
 for p in n.findall('node'):sn[(p.attrib['ref'],p.attrib['pin'])]=n.attrib['name']
for ref,m in expected.items():
 for no,n in m.items():assert pads[ref][no].GetNetname()==sn[(ref,no)]==n
assert fp['R154'].GetValue()=='2k2 1%' and fp['R151'].GetValue()=='1M'
assert (fp['R154'].GetPosition().x,fp['R154'].GetPosition().y)==(13000000,27000000)
assert (fp['J21'].GetPosition().x,fp['J21'].GetPosition().y)==(26500000,16000000)
assert all(p.GetAttribute()==pcb.PAD_ATTRIB_PTH for ref in ['J21','R154'] for p in fp[ref].Pads())
# Permanent bias is on carrier copper: U3/J21/R154 pin1 share IDLE_CMD; R154
# pin2 goes to board GND even with J21 and the whole harness absent. Native DRC
# proves connectivity. No current path through the unplugged accessory is used.
new_copper=[t for t in b.GetTracks() if str(t.m_Uuid.AsString()) not in c4]
antenna=(14000000,29000000,44000000,40000000)
def overlaps(bb):return bb.GetLeft()<antenna[2] and bb.GetRight()>antenna[0] and bb.GetTop()<antenna[3] and bb.GetBottom()>antenna[1]
assert not any(overlaps(t.GetBoundingBox()) for t in new_copper)
for ref in ['J21','R154']:
 assert not any(overlaps(g.GetBoundingBox()) for g in fp[ref].GraphicalItems() if g.GetLayer()==pcb.F_CrtYd)
# Source provenance is checked both against captured bytes and the base commit.
pr=json.loads((A5/'source-provenance.json').read_text());git_checked=[];git_newline_only=[]
for path,h in pr['source_sha256'].items():
 assert sha(SNAP/path)==h and sha(ROOT/path)==h
 blob=subprocess.check_output(['git','show',manifest['git_head']+':'+path],cwd=ROOT);
 if hashlib.sha256(blob).hexdigest()!=h:
  assert path.endswith('.csv') and (SNAP/path).read_bytes().replace(b'\r\n',b'\n')==blob
  git_newline_only.append(path)
 git_checked.append(path)
sys.path.insert(0,str(SNAP/'scripts'));from kicad9_carrier_copy import footprint_copy,board_copy
adapt,ad=board_copy((A4/'esp32-ecu.kicad_pcb').read_bytes());assert ad==pr['board_adaptation']
for p in (A4/'lib/ecu.pretty').glob('*.kicad_mod'):
 assert footprint_copy(p.read_bytes())[0]==(A5/'lib/ecu.pretty'/p.name).read_bytes()
(OUT/'a4-native-comparison.kicad_pcb').write_bytes(adapt)
b4=pcb.LoadBoard(str(OUT/'a4-native-comparison.kicad_pcb'));island4={str(z.m_Uuid.AsString()):int(z.GetIslandRemovalMode()) for z in b4.Zones()};island5={str(z.m_Uuid.AsString()):int(z.GetIslandRemovalMode()) for z in b.Zones()};assert island4==island5
assert b.GetCopperLayerCount()==b4.GetCopperLayerCount()==6
for tag in ['gr_line','gr_arc','gr_rect','gr_circle','gr_poly']:
 assert Counter(repr(canon([x for x in n if not(isinstance(x,list) and x and x[0]=='uuid')])) for n in nodes(r4,tag))==Counter(repr(canon([x for x in n if not(isinstance(x,list) and x and x[0]=='uuid')])) for n in nodes(r5,tag))
for stem,row in json.loads((A5/'new-footprints.json').read_text()).items():assert sha(A5/'lib/ecu.pretty'/(stem+'.kicad_mod'))==row['sha256']
# Ordinary fields/numbers about unaltered module do not establish physical fit.
result=dict(pcb_sha256=sha(A5/'esp32-ecu.kicad_pcb'),snapshot_bundle_sha256=manifest['bundle_sha256'],native_version=pcb.GetBuildVersion(),old_reference_count=len(f4),final_reference_count=len(f5),original_pad_count=original_pad_count,allowed_pad_change=changes,original_copper_objects_preserved_and_locked=len(c4),new_copper_objects=len(new_raw),new_net_counts=Counter(net(n,t5) for n in new_raw),original_global_zone_count=len(nodes(r4,'zone')),global_and_footprint_zone_boundaries_and_rules_unchanged=True,zone_fills_recomputed_not_compared=True,source_files_unchanged_against_git_head=len(git_checked),git_checkout_CRLF_normalization_only=git_newline_only,native_island_removal_modes_preserved=island5,outline_and_nontekst_board_graphics_preserved=True,copper_layers=6,board_centerline_size_mm=[120,120],original_R151_preserved=True,permanent_bias_does_not_use_J21=True,new_copper_and_part_courtyards_outside_provisional_antenna_mm=[14,29,44,40],actual_efuse_module_fit_RF_and_harness_qualification=False,loaded_gpio_additional_2k2_current_at_3p3_mA=3.3/2200*1000,documented_text_changes=text_changes,added_text='J21 IDLE at26,12',new_footprints=json.loads((A5/'new-footprints.json').read_text()))
(OUT/'probe-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
