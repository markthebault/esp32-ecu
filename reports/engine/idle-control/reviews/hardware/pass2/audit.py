#!/usr/bin/python3
"""Independent read-only consistency audit of the idle accessory draft."""
import hashlib,json,re,sys,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
import pcbnew

ROOT=Path('/home/mark/persospace/esp32-ecu')
D=ROOT/'hardware/idle-accessory'
OUT=ROOT/'.cache/engine/idle-hardware-review/pass2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def parse(data):
    tokens=re.findall(r'"(?:\\.|[^"\\])*"|[^\s()]+|[()]',data)
    stack=[];result=None
    for t in tokens:
        if t=='(':
            n=[]
            if stack:stack[-1].append(n)
            stack.append(n)
        elif t==')':result=stack.pop()
        else:stack[-1].append(t)
    assert not stack
    return result
def ordinary(tree):
    # Only documented top-level non-electrical format/metadata transformations.
    return [x for x in tree if not(isinstance(x,list) and (x[0]=='version' or x[0]=='point' or x==['duplicate_pad_numbers_are_jumpers','no']))]

contract=json.loads((D/'net_contract.json').read_text())
parts={p['reference']:p for p in contract['parts']}
board=pcbnew.LoadBoard(str(D/'idle.kicad_pcb'))
xml=ET.parse(OUT/'schematic.xml').getroot()
sch={}
for net in xml.findall('./nets/net'):
    for node in net.findall('node'):sch[node.attrib['ref'],node.attrib['pin']]=net.attrib['name'].lstrip('/')
pcb={}
footprints=[]
for fp in board.GetFootprints():
    ref=fp.GetReference()
    item={'reference':ref,'value':fp.GetValue(),'footprint':str(fp.GetFPID().GetLibItemName()),'x_mm':pcbnew.ToMM(fp.GetPosition().x),'y_mm':pcbnew.ToMM(fp.GetPosition().y),'pads':[]}
    for pad in fp.Pads():
        num=pad.GetNumber()
        item['pads'].append({'number':num,'net':pad.GetNetname(),'drill_mm':[pcbnew.ToMM(pad.GetDrillSize().x),pcbnew.ToMM(pad.GetDrillSize().y)],'size_mm':[pcbnew.ToMM(pad.GetSize().x),pcbnew.ToMM(pad.GetSize().y)],'attribute':pad.GetAttribute()})
        if num:pcb[ref,num]=pad.GetNetname()
    footprints.append(item)
issues=[]
for ref,p in parts.items():
    for pin,net in p['pins'].items():
        actual=[sch.get((ref,pin)),pcb.get((ref,pin))]
        if net is not None and actual!=[net,net]:issues.append({'reference':ref,'pin':pin,'contract':net,'schematic':actual[0],'pcb':actual[1]})
        if net is None and not all(v and v.startswith('unconnected-') for v in actual):issues.append({'reference':ref,'pin':pin,'contract':None,'actual':actual})
extra_pads=[(r,p) for r,p in pcb if r not in parts or p not in parts[r]['pins']]
nc_names=[{'reference':r,'pin':p,'schematic':v,'pcb':pcb.get((r,p))} for (r,p),v in sch.items() if v.startswith('unconnected-') and v!=pcb.get((r,p))]
provenance=json.loads((D/'footprint-provenance.json').read_text())
copies=[]
for stem,p in provenance.items():
    new=D/'lib/ecu.pretty'/(stem+'.kicad_mod')
    if p['source'].startswith('https://'):
        data=urllib.request.urlopen(p['source'],timeout=15).read()
        (OUT/'terminal-upstream.kicad_mod').write_bytes(data)
        assert hashlib.sha256(data).hexdigest()==p['sha256']==sha(new)
        copies.append({'footprint':stem,'pinned_upstream_bytes_equal':data==new.read_bytes(),'source_and_copy_hash_matches':True})
        continue
    src=ROOT/p['source']
    record={'footprint':stem,'source_hash_matches':sha(src)==p['sha256'],'copy_hash_matches':sha(new)==p['new_copy_sha256'],'all_non_metadata_tree_equal':ordinary(parse(src.read_text()))==ordinary(parse(new.read_text()))}
    assert all(record[k] for k in ('source_hash_matches','copy_hash_matches','all_non_metadata_tree_equal')),record
    copies.append(record)
# Independently specified primary-datasheet pin constraints.
expected={'U1':{'1':'ENA','2':'INA','3':'GND','4':'GND','5':None,'6':'+5V_LOGIC','7':'DRIVE_A','8':'GND'},'Q1':{'1':'SWITCH_INPUT','2':'IAC_LS','3':'GND'},'D1':{'1':'IAC_12V_PROTECTED','2':'IAC_LS'}}
assert all(parts[r]['pins']==p for r,p in expected.items())
assert not issues and not extra_pads,(issues,extra_pads)
result={'reviewed_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [D/'idle.kicad_sch',D/'idle.kicad_pcb',D/'net_contract.json',D/'bom.csv',ROOT/'scripts/build_idle_accessory.py',ROOT/'firmware/include/ecu/idle_hardware.hpp']},'contract_parts':len(parts),'board_footprints':len(footprints),'connected_pads_checked':sum(n is not None for p in parts.values() for n in p['pins'].values()),'datasheet_pin_constraints':'pass','connected_net_contract_disagreements':issues,'extra_pads':extra_pads,'unused_output_nc_name_disagreements':nc_names,'footprint_metadata_only_copy_checks':copies,'track_count':len(list(board.GetTracks())),'zone_count':board.GetAreaCount(),'thickness_mm':pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness()),'copper_layers':board.GetCopperLayerCount(),'footprints':sorted(footprints,key=lambda x:x['reference'])}
(OUT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('reviewed_sha256','footprints','footprint_metadata_only_copy_checks')},indent=2))
print('Provenance copies checked:',len(copies))
