import copy,json,math,struct,sys,tempfile,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))
from engine_runtime import EngineRuntime,EngineStore
from engine_msq import import_msq,export_msq,tag
from engine_protocol import DEFAULT,Session,pages,decode_pages,LEGACY_SIGNATURE,SEQUENTIAL_SIGNATURE,CYLINDER_SIGNATURE,WHOLE_SIGNATURE,SIGNATURE
from idle_config import SCALAR_OFFSETS,ARRAY_OFFSETS,LIMITS

out=Path(__file__).parent;checks=[];evidence={}
def canonical(tune):
 runtime=EngineRuntime(tune)
 try:return runtime.tune
 finally:runtime.close()
default=canonical(DEFAULT)
def same_idle(a,b):
 if set(a)!=set(b):return False
 return all(a[k]==b[k] if isinstance(a[k],str) else all(struct.pack('<f',x)==struct.pack('<f',y) for x,y in zip(a[k],b[k])) if isinstance(a[k],list) else struct.pack('<f',a[k])==struct.pack('<f',b[k]) for k in a)
for schema in (1,2,3):
 old=json.loads((ROOT/'config/engine/defaults-v3.json').read_text());old['schema_version']=schema;old['revision']=53;old['settings']['idle_enabled']=True
 if schema<3:del old['cylinder_trims']
 if schema==1:del old['timing']
 migrated=canonical(old);assert migrated['schema_version']==4 and not migrated['settings']['idle_enabled'] and same_idle(migrated['idle_control'],default['idle_control']) and migrated['revision']==53
 with tempfile.TemporaryDirectory() as directory:
  path=Path(directory)/'engine.json';original=json.dumps(old).encode();path.write_bytes(original);store=EngineStore(path);assert store.storage_ok and path.read_bytes()==original and store.tune==migrated
checks.append('schema1/2/3 enabled legacy JSON migrations disable idle, keep fixed defaults/revision and original file bytes')
legacy_files=['tunerstudio-roundtrip.msq','tunerstudio-sequential-roundtrip.msq','tunerstudio-cylinder-roundtrip.msq','tunerstudio-development-roundtrip.msq']
legacy_bodies={}
for name in legacy_files:
 tree=ET.fromstring((ROOT/'tuning/examples'/name).read_bytes())
 for element in tree.iter(tag('constant')):
  if element.get('name')=='idle_enabled':element.text='"On"'
 body=ET.tostring(tree);legacy_bodies[name]=body.decode();tune=import_msq(body);assert not tune['settings']['idle_enabled'] and tune['idle_control']==default['idle_control']
checks.append('all four historical MSQ signatures forcibly enabled migrate to disabled fixed idle')
bad_json=[]
for change in ('extra_control','extra_scalar','missing_scalar','unknown_algorithm','repeated_axis','invalid_target_sum'):
 t=copy.deepcopy(default)
 if change=='extra_control':t['extraneous_idle_control']={}
 elif change=='extra_scalar':t['idle_control']['unsupported']=0
 elif change=='missing_scalar':del t['idle_control']['kd']
 elif change=='unknown_algorithm':t['idle_control']['algorithm']='pwm_stepper'
 elif change=='repeated_axis':t['idle_control']['coolant_c'][1]=t['idle_control']['coolant_c'][0]
 else:t['idle_control']['target_add_rpm']=[-500]*6
 try:canonical(t);bad_json.append(change)
 except ValueError:pass
assert not bad_json
checks.append('native JSON rejects extra/missing/unknown and coupled curve/target violations even disabled')
invalid_binary=0
for name,offset in SCALAR_OFFSETS.items():
 for value in (float('nan'),float('inf'),float('-inf'),LIMITS[name][0]-1,LIMITS[name][1]+1):
  p=pages(default);struct.pack_into('<f',p[1],offset,value)
  try:decode_pages(p,default);raise AssertionError((name,value,'accepted'))
  except ValueError:invalid_binary+=1
for offset in (292,511,4756,4767,4940,4991):
 p=pages(default);p[1][offset]=1
 try:decode_pages(p,default);raise AssertionError((offset,'reserved accepted'))
 except ValueError:invalid_binary+=1
checks.append(f'{invalid_binary} scalar/nonfinite/reserved binary variants rejected by native whole tune validation')
with tempfile.TemporaryDirectory() as directory:
 store=EngineStore(Path(directory)/'engine.json');a=Session(store);b=Session(store)
 try:
  read=lambda session,offset,count:session.command(b'p'+struct.pack('<BBHH',0,1,offset,count))
  assert len(read(a,4991,1))==2 and read(a,4992,1)==b'\x84' and read(a,4991,2)==b'\x84'
  assert len(a.command(b'r'+struct.pack('<BBHH',0,0x30,0,256)))==257
  assert len(a.command(b'r'+struct.pack('<BBHH',0,0x30,216,40)))==41
  assert a.command(b'r'+struct.pack('<BBHH',0,0x30,255,2))==b'\x84'
  offset=SCALAR_OFFSETS['frequency_hz']
  assert a.command(b'M'+struct.pack('<BBHH',0,1,offset,4)+struct.pack('<f',80))==b'\0'
  assert a.command(b'b\0\1')==b'\4' and store.tune['revision']==2 and store.tune['idle_control']['frequency_hz']==80
  assert b.command(b'M'+struct.pack('<BBHH',0,1,offset,4)+struct.pack('<f',90))==b'\x84'
  assert b.command(b'b\0\1')==b'\x84' and store.tune['idle_control']['frequency_hz']==80
  assert a.command(b'M'+struct.pack('<BBHH',0,1,offset,4)+struct.pack('<f',90))==b'\0' and a.command(b'b\0\1')==b'\4' and store.tune['revision']==3
  assert struct.unpack_from('<I',a.buffers[1],268)[0]==1
  evidence['session']=a.diagnostics()
 finally:a.close();b.close()
checks.append('4992B page/256B live exact boundaries, whole-page burn, persistence, stale-writer rejection and stable session origin verified')
for field in ('idle_control','cylinder_trims'):
 assert import_msq(export_msq(default))[field]==default[field]
checks.append('own005 default MSQ roundtrip native validators retains idle and cylinder data')
nondefault=copy.deepcopy(default);nondefault['settings'].update(idle_enabled=True,idle_target_rpm=1000,idle_kp=.03125,idle_ki=.015625);control=nondefault['idle_control']
control.update(algorithm='open_loop',frequency_hz=82.5,control_period_ms=125,min_pct=5,max_pct=90,tps_closed_pct=1.25,tps_hysteresis_pct=.75,entry_rpm_above=150,exit_rpm_above=400,entry_delay_s=.5,afterstart_taper_s=3,dashpot_pct=6,dashpot_decay_pct_s=12,slew_pct_s=150,integral_limit_pct=30,kd=.001,derivative_filter_s=.25,fast_idle_temp_c=45,fast_idle_hysteresis_c=6,coolant_c=[-30,5,25,45,75,120],run_pct=[70,55,40,30,15,10],crank_pct=[80,70,60,50,40,30],target_add_rpm=[500,350,250,150,50,0])
nondefault=canonical(nondefault);assert same_idle(import_msq(export_msq(nondefault))['idle_control'],control)
with tempfile.TemporaryDirectory() as directory:
 store=EngineStore(Path(directory)/'engine.json');session=Session(store)
 try:
  target=pages(nondefault)[1]
  for offset in range(0,4992,256):
   data=target[offset:offset+256];assert session.command(b'M'+struct.pack('<BBHH',0,1,offset,len(data))+data)==b'\0'
  assert session.command(b'b\0\1')==b'\4'
  saved=pages(store.tune)[1];struct.pack_into('<I',saved,268,1);assert saved==target
  restored=EngineStore(store.path);assert same_idle(restored.tune['idle_control'],control) and restored.tune['settings']['idle_enabled']
 finally:session.close()
checks.append('Every idle/master field changed together survives20 native page chunks, full burn, persisted reload and MSQ with equal float32 payloads')
# Record exact current UI fixtures for independent browser semantic probes.
(out/'browser-fixtures.json').write_text(json.dumps(dict(default=default,legacy=legacy_bodies),indent=2)+'\n')
evidence.update(passed=True,checks=checks)
(out/'python-probe.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence,indent=2))
