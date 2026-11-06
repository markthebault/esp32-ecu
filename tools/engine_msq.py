"""Own-signature offline MSQ exchange. Speeduino/MegaSquirt tunes are rejected."""
import argparse
import copy
import json
import math
import struct
from pathlib import Path
import xml.etree.ElementTree as ET

from engine_protocol import DEFAULT,NUMBERS,FLAGS,CURVES,SIGNATURE,FLEX_SIGNATURE,SECONDARY_SIGNATURE,LOAD_SIGNATURE,TRANSIENT_SIGNATURE,SEMI_SIGNATURE,IDLE_SIGNATURE,WHOLE_SIGNATURE,LEGACY_SIGNATURE,SEQUENTIAL_SIGNATURE,CYLINDER_SIGNATURE,TIMING_FIELDS,STRATEGIES,STRATEGY_LABELS,PAGE_SIZES,field_units,BOOST_SIGNATURE
from idle_config import ALGORITHMS,SCALARS,ARRAYS,UNITS,name as idle_name
from transient_config import MODES,MODE_LABELS,APPLIES,APPLY_LABELS,SCALARS as AE_SCALARS,ARRAYS as AE_ARRAYS,UNITS as AE_UNITS,name as ae_name
from load_config import ENUM_FIELDS as LOAD_ENUM_FIELDS,SCALARS as LOAD_SCALARS,ENUMS as LOAD_ENUMS,LABELS as LOAD_LABELS,UNITS as LOAD_UNITS,name as load_name
from secondary_config import KINDS,ENUM_FIELDS as SEC_ENUM_FIELDS,SCALARS as SEC_SCALARS,ENUMS as SEC_ENUMS,LABELS as SEC_LABELS,name as sec_name,constant_unit

from flex_config import BOOLEANS as FLEX_BOOLS,CAPTURE_FLOATS as FLEX_FLOATS,ARRAYS as FLEX_ARRAYS,get as flex_get,set_value as flex_set,constant as flex_name,UNITS as FLEX_UNITS

from boost_config import SCALARS as BOOST_SCALARS,TABLES as BOOST_TABLES,MODES as BOOST_MODES,ACTIVATIONS as BOOST_ACTIVATIONS,UNITS as BOOST_UNITS,constant as boost_name

from profile_config import MSQ_MAXIMUM

NS='http://www.msefi.com/:msq'
ET.register_namespace('',NS)
def tag(name):return '{'+NS+'}'+name

def valid_revision(value):
 return type(value) in (int,float) and 1<=value<=4294967295 and math.isfinite(value) and int(value)==value

def constants(tune,legacy=False,sequential=False,whole=True,idle=True,transient=True,model=True,secondary=True,flex=True,boost=True,profiles=True):
 revision=tune['revision']
 if not valid_revision(revision):raise ValueError('Invalid MSQ base revision')
 result=[(0,'baseRevision',[int(revision)],None)]
 result += [(0,k,[tune[group][k]],None) for group,k in NUMBERS]
 result += [(0,k,['"On"' if tune['settings'][k] else '"Off"'],None) for k in FLAGS]
 result += [(0,k,tune['curves'][k],(n,1)) for k,n in CURVES]
 if not legacy:
  result += [(0,'engineStrategy',['"'+STRATEGY_LABELS[STRATEGIES.index(tune['strategy'])]+'"'],None)]
  result += [(0,k,[tune['timing'][k]],None) for k,_ in TIMING_FIELDS]
  result += [(0,f'fireOrder{i+1}',[v],None) for i,v in enumerate(tune['timing']['firing_order'][:8 if profiles else 4])]
 for page,name in enumerate(('ve','spark','lambda'),1):
  result += [(page,name+'Rpm',tune['maps'][name]['rpm'],(16,1)),(page,name+'Load',tune['maps'][name]['load'],(16,1)),(page,name+'Table',tune['maps'][name]['cells'],(16,16))]
 if not legacy and not sequential:
  result += [(4,'cylinderTrimsEnabled',['\"On\"' if tune['cylinder_trims']['enabled'] else '\"Off\"'],None)]
  for i in range(8 if profiles else 4):
   result += [(4,f'c{i+1}SparkTrim',[tune['cylinder_trims']['spark_deg'][i]],None)]
   m=tune['cylinder_trims']['fuel_maps'][i]
   result += [(4,f'c{i+1}FuelRpm',m['rpm'],(6,1)),(4,f'c{i+1}FuelLoad',m['load'],(6,1)),(4,f'c{i+1}FuelTable',m['cells'],(6,6))]
 if idle and whole and not legacy and not sequential:
  control=tune['idle_control']
  result += [(0,'iac_algorithm',['"'+control['algorithm']+'"'],None)]
  result += [(0,idle_name(k),[control[k]],None) for k in SCALARS]
  result += [(0,idle_name(k),control[k],(n,1)) for k,n in ARRAYS]
 if transient and whole and not legacy and not sequential:
  ae=tune['transient_enrichment'];result += [(0,'ae_mode',['"'+MODE_LABELS[MODES.index(ae['mode'])]+'"'],None),(0,'ae_apply',['"'+APPLY_LABELS[APPLIES.index(ae['apply'])]+'"'],None)]
  result += [(0,ae_name(k),[ae[k]],None) for k in AE_SCALARS]
  result += [(0,ae_name(k),ae[k],(4,1)) for k in AE_ARRAYS]
 if model and whole and not legacy and not sequential:
  c=tune['load_model'];result += [(0,load_name(k),['"'+LOAD_LABELS[k][LOAD_ENUMS[k].index(c[k])]+'"'],None) for k in LOAD_ENUM_FIELDS]
  result += [(0,load_name(k),[c[k]],None) for k in LOAD_SCALARS]
 if secondary and whole and not legacy and not sequential:
  for kind in KINDS:
   c=tune['secondary_tables'][kind]
   result += [(0,sec_name(kind,k),['"'+SEC_LABELS[k][SEC_ENUMS[k].index(c[k])]+'"'],None) for k in SEC_ENUM_FIELDS]
   result += [(0,sec_name(kind,k),[c[k]],None) for k in SEC_SCALARS+('input_channel',)]
   result += [(0,sec_name(kind,'active_high'),['"Active high"' if c['active_high'] else '"Active low"'],None)]
   result += [(0,sec_name(kind,'map'+suffix),c['map'][key],shape) for suffix,key,shape in [('Rpm','rpm',(16,1)),('Load','load',(16,1)),('Table','cells',(16,16))]]
 if flex and whole and not legacy and not sequential:
  c=tune['flex_fuel']
  result += [(0,flex_name(k),['"On"' if flex_get(c,k) else '"Off"'],None) for k in FLEX_BOOLS]
  result += [(0,flex_name(k),[flex_get(c,k)],None) for k in FLEX_FLOATS+('cycles',)]
  result += [(0,flex_name(k),flex_get(c,k),(6,1)) for k in FLEX_ARRAYS]
 if boost and whole and not legacy and not sequential:
  c=tune['boost_control']
  result += [(0,boost_name('pressure_enabled'),['"On"' if c['pressure_enabled'] else '"Off"'],None),(0,boost_name('mode'),['"'+c['mode']+'"'],None),(0,boost_name('activation'),['"'+c['activation']+'"'],None)]
  result += [(0,boost_name(k),[c[k]],None) for k in BOOST_SCALARS]
  for name in BOOST_TABLES:
   result += [(0,boost_name(name+'_'+key),c[name][key],(8,8) if key=='cells' else (8,1)) for key in ('rpm','axis','cells')]
 return [(0,name,values,shape) for _,name,values,shape in result] if whole and not legacy and not sequential else result

def export_msq(tune):
 from engine_runtime import EngineRuntime
 runtime=EngineRuntime(tune);tune=runtime.tune;runtime.close()
 root=ET.Element(tag('msq'))
 ET.SubElement(root,tag('bibliography'),author='ESP32ECU',tuneComment='SHADOW ONLY; physical outputs inhibited; illustrative development tune')
 ET.SubElement(root,tag('versionInfo'),fileFormat='5.0',firmwareInfo='ESP32ECU development',nPages='1',signature=SIGNATURE.decode())
 elements={i:ET.SubElement(root,tag('page'),number=str(i),size=str(PAGE_SIZES[i+1])) for i in range(1)}
 for page,name,values,shape in constants(tune):
  units=LOAD_UNITS.get(name[5:],'') if name.startswith('load_') else AE_UNITS.get(name[3:],'') if name.startswith('ae_') else UNITS.get(name[4:],'') if name.startswith('iac_') else field_units(name) if name in ({k for _,k in NUMBERS}|{k for k,_ in TIMING_FIELDS}) else 'RPM' if name.endswith('Rpm') else 'source_units' if name.endswith('Load') else {'veTable':'%','sparkTable':'deg','lambdaTable':'lambda'}.get(name,'deg' if name.endswith('SparkTrim') else '%' if name.endswith('FuelTable') else '')
  if name.startswith('flex_'):units=FLEX_UNITS.get(name[5:],'')
  if name.startswith('boost_'):
   units='' if name in ('boost_pressure_enabled','boost_mode','boost_activation') else BOOST_UNITS.get(name[6:],'RPM' if name.endswith('_rpm') else 'kPa absolute' if name=='boost_feedforward_axis' or name=='boost_target_cells' else '% TPS' if name.endswith('_axis') else '%')
  if name.startswith('secondary_'):
   _,kind,key=name.split('_',2);rule=tune['secondary_tables'][kind]
   units=constant_unit(kind,key,rule)
  element=ET.SubElement(elements[page],tag('constant'),name=name,units=units)
  if shape:element.set('rows',str(shape[0]));element.set('cols',str(shape[1]))
  formatted=[str(v) if isinstance(v,int) else format(v,'.9g') if isinstance(v,float) else v for v in values]
  element.text='\n'+'\n'.join(' '.join(formatted[i:i+shape[1]]) for i in range(0,len(values),shape[1]))+'\n' if shape else formatted[0]
 ET.indent(root,space='  ')
 return ET.tostring(root,encoding='utf-8',xml_declaration=True).decode()+'\n'

def import_msq(body,base_revision=None):
 # Own004/005/006/007 apps can omit readOnly origin. A caller may supply its already-loaded
 # CAS base; otherwise 1 is an offline placeholder, never a discovered revision.
 if isinstance(body,str):body=body.encode()
 if len(body)>MSQ_MAXIMUM or b'\0' in body or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('MSQ size or XML declarations rejected')
 try:root=ET.fromstring(body)
 except ET.ParseError as error:raise ValueError('Malformed MSQ XML') from error
 info=root.find(tag('versionInfo'))
 signatures=(LEGACY_SIGNATURE,SEQUENTIAL_SIGNATURE,CYLINDER_SIGNATURE,WHOLE_SIGNATURE,IDLE_SIGNATURE,SEMI_SIGNATURE,TRANSIENT_SIGNATURE,LOAD_SIGNATURE,SECONDARY_SIGNATURE,FLEX_SIGNATURE,BOOST_SIGNATURE,SIGNATURE)
 try:index=tuple(value.decode() for value in signatures).index(info.get('signature')) if info is not None else -1
 except ValueError:index=-1
 page_count='4' if index<2 else '5' if index==2 else '1'
 if root.tag!=tag('msq') or info is None or index<0 or info.get('nPages')!=page_count:raise ValueError('MSQ must match this ESP32ECU definition; other ECU tunes are incompatible')
 legacy=index==0;sequential=index==1;whole=index>=3;has_idle=index>=4;has_semi=index>=5;has_transient=index>=6;has_load=index>=7;has_secondary=index>=8;has_flex=index>=9;has_boost=index>=10;profiles=index>=11
 expected={name:(page,len(values),shape) for page,name,values,shape in constants(DEFAULT,legacy=legacy,sequential=sequential,whole=whole,idle=has_idle,transient=has_transient,model=has_load,secondary=has_secondary,flex=has_flex,boost=has_boost,profiles=profiles)}
 values={}
 for page in root.findall(tag('page')):
  for element in page.findall(tag('constant')):
   name=element.get('name')
   if name not in expected or name in values:raise ValueError('Unknown or duplicate MSQ constant')
   page_number,count,shape=expected[name]
   if page.get('number')!=str(page_number):raise ValueError('MSQ constant on wrong page')
   dimensions=(element.get('rows'),element.get('cols'))
   if dimensions!=(None,None) and dimensions!=tuple(str(v) for v in (shape or (1,1))):raise ValueError('MSQ declared dimensions disagree with its constant definition')
   text=(element.text or '').strip()
   if name.startswith('secondary_'):
    _,kind,key=name.split('_',2)
    if key in SEC_ENUM_FIELDS:
     labels=SEC_LABELS[key]
     if text in tuple('"'+label+'"' for label in labels):values[name]=SEC_ENUMS[key][labels.index(text.strip('"'))]
     elif text in tuple(str(i) for i in range(len(labels))):values[name]=SEC_ENUMS[key][int(text)]
     else:raise ValueError('Invalid secondary-table selection')
    elif key=='active_high':
     if text not in ('"Active low"','"Active high"','0','1'):raise ValueError('Invalid secondary polarity')
     values[name]=text in ('"Active high"','1')
    else:
     try:parsed=[float(v) for v in text.split()]
     except ValueError as error:raise ValueError('Invalid secondary numeric value') from error
     if len(parsed)!=count or not all(math.isfinite(v) for v in parsed):raise ValueError('Invalid secondary value count or finite value')
     values[name]=parsed if shape else parsed[0]
   elif name.startswith('load_') and name[5:] in LOAD_ENUM_FIELDS:
    field=name[5:];labels=LOAD_LABELS[field]
    if text in tuple('"'+label+'"' for label in labels):values[name]=LOAD_ENUMS[field][labels.index(text.strip('"'))]
    elif text in tuple(str(i) for i in range(len(labels))):values[name]=LOAD_ENUMS[field][int(text)]
    else:raise ValueError('Invalid load-model selection')
   elif name in ('ae_mode','ae_apply'):
    labels=MODE_LABELS if name=='ae_mode' else APPLY_LABELS
    if text in tuple('"'+label+'"' for label in labels):values[name]=labels.index(text.strip('"'))
    elif text in tuple(str(i) for i in range(len(labels))):values[name]=int(text)
    else:raise ValueError('Invalid transient selection')
   elif name in ('boost_mode','boost_activation'):
    choices=BOOST_MODES if name=='boost_mode' else BOOST_ACTIVATIONS
    if text in tuple('"'+v+'"' for v in choices):values[name]=text.strip('"')
    elif text in tuple(str(i) for i in range(len(choices))):values[name]=choices[int(text)]
    else:raise ValueError('Invalid boost selection')
   elif name=='iac_algorithm':
    if text in ('0','1','2'):values[name]=ALGORITHMS[int(text)]
    elif text.strip('"') in ALGORITHMS and text=='"'+text.strip('"')+'"':values[name]=text.strip('"')
    else:raise ValueError('Invalid idle algorithm')
   elif name=='engineStrategy':
    allowed=STRATEGY_LABELS if has_semi else STRATEGY_LABELS[:2]
    if text in tuple('"'+x+'"' for x in allowed):values[name]=allowed.index(text.strip('"'))
    elif text in tuple(str(i) for i in range(len(allowed))):values[name]=int(text)
    else:raise ValueError('Invalid MSQ strategy for its identity')
   elif name in FLAGS or name=='cylinderTrimsEnabled' or name=='boost_pressure_enabled' or name in tuple(flex_name(k) for k in FLEX_BOOLS):
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
  tune['strategy']='batch_wasted';tune['timing']=dict(firing_order=[1,3,4,2,0,0,0,0],injection_end_deg=540,cam_sync_deg=450,cam_window_deg=20)
 if not legacy:
  tune['strategy']=STRATEGIES[values['engineStrategy']]
  for name,_ in TIMING_FIELDS:tune['timing'][name]=values[name]
  tune['timing']['firing_order']=[values[f'fireOrder{i+1}'] for i in range(8 if profiles else 4)]+([] if profiles else [0]*4)
 if not legacy and not sequential:
  tune['cylinder_trims']['enabled']=values['cylinderTrimsEnabled']
  for i in range(8 if profiles else 4):
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
 if has_transient:
  ae=tune['transient_enrichment'];ae['mode']=MODES[values['ae_mode']];ae['apply']=APPLIES[values['ae_apply']]
  for name in AE_SCALARS+AE_ARRAYS:ae[name]=values[ae_name(name)]
 if has_load:
  for name in LOAD_ENUM_FIELDS+LOAD_SCALARS:tune['load_model'][name]=values[load_name(name)]
 if has_secondary:
  for kind in KINDS:
   rule=tune['secondary_tables'][kind]
   for key in SEC_ENUM_FIELDS+SEC_SCALARS+('input_channel','active_high'):rule[key]=values[sec_name(kind,key)]
   rule['map']=dict(rpm=values[sec_name(kind,'mapRpm')],load=values[sec_name(kind,'mapLoad')],cells=values[sec_name(kind,'mapTable')])
 if has_flex:
  for name in FLEX_BOOLS+FLEX_FLOATS+('cycles',)+FLEX_ARRAYS:flex_set(tune['flex_fuel'],name,values[flex_name(name)])
 if has_boost:
  c=tune['boost_control']
  for name in ('pressure_enabled','mode','activation')+BOOST_SCALARS:c[name]=values[boost_name(name)]
  for name in BOOST_TABLES:c[name]={key:values[boost_name(name+'_'+key)] for key in ('rpm','axis','cells')}
 for name,n in CURVES:tune['curves'][name]=values[name]
 for name in ('ve','spark','lambda'):tune['maps'][name]=dict(rpm=values[name+'Rpm'],load=values[name+'Load'],cells=values[name+'Table'])
 if not profiles:
  if tune['engine']['cylinders']!=4 or not 500<=tune['engine']['displacement_cc']<=4000 or not 100<=tune['engine']['injector_cc_min']<=1500:raise ValueError('Historical MSQ identity retains its four-cylinder engine-specification bounds')
  first=tune['cylinder_trims']['fuel_maps'][0]
  for index in range(4,8):
   tune['cylinder_trims']['spark_deg'][index]=0
   tune['cylinder_trims']['fuel_maps'][index]=dict(rpm=list(first['rpm']),load=list(first['load']),cells=[100]*36)
 if not has_load and any(abs(v)>1e6 or not 20<=struct.unpack('<f',struct.pack('<f',v))[0]<=120 for v in tune['maps']['ve']['cells']):raise ValueError('Historical identity retains20..120 F32 fuel-coefficient bounds')
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
