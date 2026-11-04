"""Own-signature offline MSQ exchange. Speeduino/MegaSquirt tunes are rejected."""
import argparse
import copy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from engine_protocol import DEFAULT,NUMBERS,FLAGS,CURVES,SIGNATURE,IDLE_SIGNATURE,WHOLE_SIGNATURE,LEGACY_SIGNATURE,SEQUENTIAL_SIGNATURE,CYLINDER_SIGNATURE,TIMING_FIELDS,STRATEGIES,STRATEGY_LABELS,PAGE_SIZES,field_units
from idle_config import ALGORITHMS,SCALARS,ARRAYS,UNITS,name as idle_name

NS='http://www.msefi.com/:msq'
ET.register_namespace('',NS)
def tag(name):return '{'+NS+'}'+name

def valid_revision(value):
 return type(value) in (int,float) and 1<=value<=4294967295 and math.isfinite(value) and int(value)==value

def constants(tune,legacy=False,sequential=False,whole=True,idle=True):
 revision=tune['revision']
 if not valid_revision(revision):raise ValueError('Invalid MSQ base revision')
 result=[(0,'baseRevision',[int(revision)],None)]
 result += [(0,k,[tune[group][k]],None) for group,k in NUMBERS]
 result += [(0,k,['"On"' if tune['settings'][k] else '"Off"'],None) for k in FLAGS]
 result += [(0,k,tune['curves'][k],(n,1)) for k,n in CURVES]
 if not legacy:
  result += [(0,'engineStrategy',['"'+STRATEGY_LABELS[STRATEGIES.index(tune['strategy'])]+'"'],None)]
  result += [(0,k,[tune['timing'][k]],None) for k,_ in TIMING_FIELDS]
  result += [(0,f'fireOrder{i+1}',[v],None) for i,v in enumerate(tune['timing']['firing_order'])]
 for page,name in enumerate(('ve','spark','lambda'),1):
  result += [(page,name+'Rpm',tune['maps'][name]['rpm'],(16,1)),(page,name+'Load',tune['maps'][name]['load'],(16,1)),(page,name+'Table',tune['maps'][name]['cells'],(16,16))]
 if not legacy and not sequential:
  result += [(4,'cylinderTrimsEnabled',['\"On\"' if tune['cylinder_trims']['enabled'] else '\"Off\"'],None)]
  for i in range(4):
   result += [(4,f'c{i+1}SparkTrim',[tune['cylinder_trims']['spark_deg'][i]],None)]
   m=tune['cylinder_trims']['fuel_maps'][i]
   result += [(4,f'c{i+1}FuelRpm',m['rpm'],(6,1)),(4,f'c{i+1}FuelLoad',m['load'],(6,1)),(4,f'c{i+1}FuelTable',m['cells'],(6,6))]
 if idle and whole and not legacy and not sequential:
  control=tune['idle_control']
  result += [(0,'iac_algorithm',['"'+control['algorithm']+'"'],None)]
  result += [(0,idle_name(k),[control[k]],None) for k in SCALARS]
  result += [(0,idle_name(k),control[k],(n,1)) for k,n in ARRAYS]
 return [(0,name,values,shape) for _,name,values,shape in result] if whole and not legacy and not sequential else result

def export_msq(tune):
 from engine_runtime import EngineRuntime
 runtime=EngineRuntime(tune);tune=runtime.tune;runtime.close()
 root=ET.Element(tag('msq'))
 ET.SubElement(root,tag('bibliography'),author='ESP32ECU',tuneComment='SHADOW ONLY; physical outputs inhibited; illustrative development tune')
 ET.SubElement(root,tag('versionInfo'),fileFormat='5.0',firmwareInfo='ESP32ECU development',nPages='1',signature=SIGNATURE.decode())
 elements={i:ET.SubElement(root,tag('page'),number=str(i),size=str(PAGE_SIZES[i+1])) for i in range(1)}
 for page,name,values,shape in constants(tune):
  units=UNITS.get(name[4:],'') if name.startswith('iac_') else field_units(name) if name in ({k for _,k in NUMBERS}|{k for k,_ in TIMING_FIELDS}) else 'RPM' if name.endswith('Rpm') else 'kPa' if name.endswith('Load') else {'veTable':'%','sparkTable':'deg','lambdaTable':'lambda'}.get(name,'deg' if name.endswith('SparkTrim') else '%' if name.endswith('FuelTable') else '')
  element=ET.SubElement(elements[page],tag('constant'),name=name,units=units)
  if shape:element.set('rows',str(shape[0]));element.set('cols',str(shape[1]))
  formatted=[str(v) if isinstance(v,int) else format(v,'.9g') if isinstance(v,float) else v for v in values]
  element.text='\n'+'\n'.join(' '.join(formatted[i:i+shape[1]]) for i in range(0,len(values),shape[1]))+'\n' if shape else formatted[0]
 ET.indent(root,space='  ')
 return ET.tostring(root,encoding='utf-8',xml_declaration=True).decode()+'\n'

def import_msq(body,base_revision=None):
 # Own004/005/006 apps can omit readOnly origin. A caller may supply its already-loaded
 # CAS base; otherwise 1 is an offline placeholder, never a discovered revision.
 if isinstance(body,str):body=body.encode()
 if len(body)>65536 or b'\0' in body or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('MSQ size or XML declarations rejected')
 try:root=ET.fromstring(body)
 except ET.ParseError as error:raise ValueError('Malformed MSQ XML') from error
 info=root.find(tag('versionInfo'))
 if root.tag!=tag('msq') or info is None or info.get('signature') not in (SIGNATURE.decode(),IDLE_SIGNATURE.decode(),WHOLE_SIGNATURE.decode(),LEGACY_SIGNATURE.decode(),SEQUENTIAL_SIGNATURE.decode(),CYLINDER_SIGNATURE.decode()) or info.get('nPages')!=('1' if info.get('signature') in (SIGNATURE.decode(),IDLE_SIGNATURE.decode(),WHOLE_SIGNATURE.decode()) else '5' if info.get('signature')==CYLINDER_SIGNATURE.decode() else '4'):raise ValueError('MSQ must match this ESP32ECU definition; other ECU tunes are incompatible')
 legacy=info.get('signature')==LEGACY_SIGNATURE.decode();sequential=info.get('signature')==SEQUENTIAL_SIGNATURE.decode()
 current=info.get('signature')==SIGNATURE.decode();has_idle=info.get('signature') in (SIGNATURE.decode(),IDLE_SIGNATURE.decode());whole=info.get('signature') in (SIGNATURE.decode(),IDLE_SIGNATURE.decode(),WHOLE_SIGNATURE.decode())
 expected={name:(page,len(values),shape) for page,name,values,shape in constants(DEFAULT,legacy=legacy,sequential=sequential,whole=whole,idle=has_idle)}
 values={}
 for page in root.findall(tag('page')):
  for element in page.findall(tag('constant')):
   name=element.get('name')
   if name not in expected or name in values:raise ValueError('Unknown or duplicate MSQ constant')
   page_number,count,shape=expected[name]
   if page.get('number')!=str(page_number):raise ValueError('MSQ constant on wrong page')
   text=(element.text or '').strip()
   if name=='iac_algorithm':
    if text in ('0','1','2'):values[name]=ALGORITHMS[int(text)]
    elif text.strip('"') in ALGORITHMS and text=='"'+text.strip('"')+'"':values[name]=text.strip('"')
    else:raise ValueError('Invalid idle algorithm')
   elif name=='engineStrategy':
    allowed=STRATEGY_LABELS if current else STRATEGY_LABELS[:2]
    if text in tuple('"'+x+'"' for x in allowed):values[name]=allowed.index(text.strip('"'))
    elif text in tuple(str(i) for i in range(len(allowed))):values[name]=int(text)
    else:raise ValueError('Invalid MSQ strategy for its identity')
   elif name in FLAGS or name=='cylinderTrimsEnabled':
    if text not in ('"Off"','"On"','0','1'):raise ValueError('Invalid MSQ flag')
    values[name]=text in ('"On"','1')
   else:
    try:parsed=[float(v) for v in text.split()]
    except ValueError as error:raise ValueError('Non-numeric MSQ constant') from error
    if len(parsed)!=count or not all(math.isfinite(v) for v in parsed):raise ValueError('MSQ value count or non-finite number')
    values[name]=parsed if shape else parsed[0]
 if whole and 'baseRevision' not in values:
  values['baseRevision']=1
 if set(values)!=set(expected):raise ValueError('Incomplete MSQ tune')
 revision=values['baseRevision']
 if not valid_revision(revision):raise ValueError('Invalid MSQ base revision')
 if base_revision is not None:
  if not valid_revision(base_revision):raise ValueError('Invalid caller base revision')
  if whole:revision=base_revision
 tune=copy.deepcopy(DEFAULT);tune['revision']=int(revision)
 if legacy:
  tune['strategy']='batch_wasted_4cyl';tune['timing']=dict(firing_order=[1,3,4,2],injection_end_deg=540,cam_sync_deg=450,cam_window_deg=20)
 if not legacy:
  tune['strategy']=STRATEGIES[values['engineStrategy']]
  for name,_ in TIMING_FIELDS:tune['timing'][name]=values[name]
  tune['timing']['firing_order']=[values[f'fireOrder{i+1}'] for i in range(4)]
 if not legacy and not sequential:
  tune['cylinder_trims']['enabled']=values['cylinderTrimsEnabled']
  for i in range(4):
   tune['cylinder_trims']['spark_deg'][i]=values[f'c{i+1}SparkTrim']
   tune['cylinder_trims']['fuel_maps'][i]=dict(rpm=values[f'c{i+1}FuelRpm'],load=values[f'c{i+1}FuelLoad'],cells=values[f'c{i+1}FuelTable'])
 for group,name in NUMBERS:tune[group][name]=values[name]
 for name in FLAGS:tune['settings'][name]=values[name]
 if has_idle:
  tune['idle_control']['algorithm']=values['iac_algorithm']
  for name in SCALARS:tune['idle_control'][name]=values[idle_name(name)]
  for name,_ in ARRAYS:tune['idle_control'][name]=values[idle_name(name)]
 else:
  # Historical idle was a virtual proposal. Migration cannot authorize the new actuator.
  tune['settings']['idle_enabled']=False
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
