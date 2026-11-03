"""Own-signature offline MSQ exchange. Speeduino/MegaSquirt tunes are rejected."""
import argparse
import copy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from engine_protocol import DEFAULT,NUMBERS,FLAGS,CURVES,SIGNATURE,LEGACY_SIGNATURE,TIMING_FIELDS,STRATEGIES,PAGE_SIZES,field_units

NS='http://www.msefi.com/:msq'
ET.register_namespace('',NS)
def tag(name):return '{'+NS+'}'+name

def constants(tune,legacy=False):
 revision=tune['revision']
 if isinstance(revision,bool) or not isinstance(revision,(int,float)) or not math.isfinite(revision) or int(revision)!=revision or not 1<=revision<=4294967295:raise ValueError('Invalid MSQ base revision')
 result=[(0,'baseRevision',[int(revision)],None)]
 result += [(0,k,[tune[group][k]],None) for group,k in NUMBERS]
 result += [(0,k,['"On"' if tune['settings'][k] else '"Off"'],None) for k in FLAGS]
 result += [(0,k,tune['curves'][k],(n,1)) for k,n in CURVES]
 if not legacy:
  result += [(0,'engineStrategy',['"Sequential"' if tune['strategy']=='sequential_4cyl' else '"Batch / wasted"'],None)]
  result += [(0,k,[tune['timing'][k]],None) for k,_ in TIMING_FIELDS]
  result += [(0,f'fireOrder{i+1}',[v],None) for i,v in enumerate(tune['timing']['firing_order'])]
 for page,name in enumerate(('ve','spark','lambda'),1):
  result += [(page,name+'Rpm',tune['maps'][name]['rpm'],(16,1)),(page,name+'Load',tune['maps'][name]['load'],(16,1)),(page,name+'Table',tune['maps'][name]['cells'],(16,16))]
 return result

def export_msq(tune):
 from engine_runtime import EngineRuntime
 runtime=EngineRuntime(tune);tune=runtime.tune;runtime.close()
 root=ET.Element(tag('msq'))
 ET.SubElement(root,tag('bibliography'),author='ESP32ECU',tuneComment='SHADOW ONLY; physical outputs inhibited; illustrative development tune')
 ET.SubElement(root,tag('versionInfo'),fileFormat='5.0',firmwareInfo='ESP32ECU SIL',nPages='4',signature=SIGNATURE.decode())
 elements={i:ET.SubElement(root,tag('page'),number=str(i),size=str(PAGE_SIZES[i+1])) for i in range(4)}
 for page,name,values,shape in constants(tune):
  units=field_units(name) if page==0 and name not in dict(CURVES) else 'RPM' if name.endswith('Rpm') else 'kPa' if name.endswith('Load') else {'veTable':'%','sparkTable':'deg','lambdaTable':'lambda'}.get(name,'')
  element=ET.SubElement(elements[page],tag('constant'),name=name,units=units)
  if shape:element.set('rows',str(shape[0]));element.set('cols',str(shape[1]))
  formatted=[str(v) if isinstance(v,int) else format(v,'.9g') if isinstance(v,float) else v for v in values]
  element.text='\n'+'\n'.join(' '.join(formatted[i:i+shape[1]]) for i in range(0,len(values),shape[1]))+'\n' if shape else formatted[0]
 ET.indent(root,space='  ')
 return ET.tostring(root,encoding='utf-8',xml_declaration=True).decode()+'\n'

def import_msq(body):
 if isinstance(body,str):body=body.encode()
 if len(body)>65536 or b'\0' in body or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('MSQ size or XML declarations rejected')
 try:root=ET.fromstring(body)
 except ET.ParseError as error:raise ValueError('Malformed MSQ XML') from error
 info=root.find(tag('versionInfo'))
 if root.tag!=tag('msq') or info is None or info.get('signature') not in (SIGNATURE.decode(),LEGACY_SIGNATURE.decode()) or info.get('nPages')!='4':raise ValueError('MSQ must match this ESP32ECU definition; other ECU tunes are incompatible')
 legacy=info.get('signature')==LEGACY_SIGNATURE.decode()
 expected={name:(page,len(values),shape) for page,name,values,shape in constants(DEFAULT,legacy=legacy)}
 values={}
 for page in root.findall(tag('page')):
  for element in page.findall(tag('constant')):
   name=element.get('name')
   if name not in expected or name in values:raise ValueError('Unknown or duplicate MSQ constant')
   page_number,count,shape=expected[name]
   if page.get('number')!=str(page_number):raise ValueError('MSQ constant on wrong page')
   text=(element.text or '').strip()
   if name=='engineStrategy':
    if text not in ('"Batch / wasted"','"Sequential"','0','1'):raise ValueError('Invalid MSQ strategy')
    values[name]=1 if text in ('"Sequential"','1') else 0
   elif name in FLAGS:
    if text not in ('"Off"','"On"','0','1'):raise ValueError('Invalid MSQ flag')
    values[name]=text in ('"On"','1')
   else:
    try:parsed=[float(v) for v in text.split()]
    except ValueError as error:raise ValueError('Non-numeric MSQ constant') from error
    if len(parsed)!=count or not all(math.isfinite(v) for v in parsed):raise ValueError('MSQ value count or non-finite number')
    values[name]=parsed if shape else parsed[0]
 if set(values)!=set(expected):raise ValueError('Incomplete MSQ tune')
 revision=values['baseRevision']
 if revision!=int(revision) or not 1<=revision<=4294967295:raise ValueError('Invalid MSQ base revision')
 tune=copy.deepcopy(DEFAULT);tune['revision']=int(revision)
 if legacy:
  tune['strategy']='batch_wasted_4cyl';tune['timing']=dict(firing_order=[1,3,4,2],injection_end_deg=540,cam_sync_deg=450,cam_window_deg=20)
 if not legacy:
  tune['strategy']=STRATEGIES[values['engineStrategy']]
  for name,_ in TIMING_FIELDS:tune['timing'][name]=values[name]
  tune['timing']['firing_order']=[values[f'fireOrder{i+1}'] for i in range(4)]
 for group,name in NUMBERS:tune[group][name]=values[name]
 for name in FLAGS:tune['settings'][name]=values[name]
 for name,n in CURVES:tune['curves'][name]=values[name]
 for name in ('ve','spark','lambda'):tune['maps'][name]=dict(rpm=values[name+'Rpm'],load=values[name+'Load'],cells=values[name+'Table'])
 from engine_runtime import EngineRuntime
 runtime=EngineRuntime(tune);tune=runtime.tune;runtime.close()
 return tune

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
 args=parser.parse_args()
 if args.output.exists():raise SystemExit('Output exists; choose a new filename')
 data=import_msq(args.input.read_bytes()) if args.input.suffix.lower()=='.msq' else json.loads(args.input.read_text())
 from engine_runtime import EngineRuntime
 runtime=EngineRuntime(data);runtime.close()
 if args.output.suffix.lower()=='.msq':args.output.write_text(export_msq(data))
 else:args.output.write_text(json.dumps(data,indent=2)+'\n')
