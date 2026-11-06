from helpers import *
import copy,json,hashlib,re,struct,subprocess,tempfile,types,threading,xml.etree.ElementTree as ET
from unittest import mock
from engine_protocol import DEFAULT,SIGNATURE,IDLE_SIGNATURE,pages,decode_pages,live_block,Session
from engine_msq import export_msq,import_msq,tag
from idle_config import SCALARS,ARRAYS,name as idle_name
compact=lambda t:json.dumps(t,separators=(',',':'),allow_nan=False).encode()
results={}
def distinct():
 t=copy.deepcopy(DEFAULT);t['strategy']='sequential_4cyl';t['revision']=37;t['settings']['idle_enabled']=True
 t['idle_control']['algorithm']='closed_loop';t['idle_control']['frequency_hz']=80;t['idle_control']['control_period_ms']=25;t['idle_control']['kd']=.005
 t['idle_control']['run_pct']=[31,29,27,25,23,21];t['idle_control']['target_add_rpm']=[400,300,200,100,50,0]
 t['cylinder_trims']['enabled']=True;t['cylinder_trims']['spark_deg']=[1.25,-2.5,3.75,-4.0]
 for i,m in enumerate(t['cylinder_trims']['fuel_maps']):m['cells']=[95+i*5+(c%4)*.25 for c in range(36)]
 return t
# Native schema4 migration is exactly a schema bump and preserves raw file.
old=distinct();old['schema_version']=4
with tempfile.TemporaryDirectory(prefix='semi-schema4-review-') as td:
 path=Path(td)/'tune.json';raw=json.dumps(old,indent=1).encode();path.write_bytes(raw);store=er.EngineStore(path,b)
 expected=copy.deepcopy(old);expected['schema_version']=5;assert store.tune==expected and path.read_bytes()==raw and store.storage_ok
 code,saved=store.save(compact(store.tune));assert code==200 and saved['revision']==38 and json.loads(path.read_bytes())['schema_version']==5
 store.runtime.close();store.trigger_capture.close()
results['schema4']='Raw file retained on load; idle/trims/revision unchanged in RAM; explicit save bumps schema5 and revision37→38'
# Earlier schemas retain fixed disabled-idle migration and existing trim rules.
results['legacy_json']={}
for version in (1,2,3):
 t=distinct();t['schema_version']=version;t.pop('idle_control');t['settings']['idle_enabled']=True
 if version<3:t.pop('cylinder_trims')
 if version==1:t.pop('timing');t['strategy']='batch_wasted_4cyl'
 with tempfile.TemporaryDirectory(prefix='semi-old-json-review-') as td:
  path=Path(td)/'tune.json';raw=compact(t);path.write_bytes(raw);store=er.EngineStore(path,b)
  assert store.storage_ok and path.read_bytes()==raw and store.tune['schema_version']==5 and store.tune['revision']==37 and not store.tune['settings']['idle_enabled']
  fixed={k:([struct.unpack('<f',struct.pack('<f',v))[0] for v in x] if isinstance(x,list) else struct.unpack('<f',struct.pack('<f',x))[0] if isinstance(x,(int,float)) else x) for k,x in DEFAULT['idle_control'].items()}
  assert store.tune['idle_control']==fixed
  if version==3:assert store.tune['cylinder_trims']==t['cylinder_trims']
  else:assert not store.tune['cylinder_trims']['enabled'] and all(m['cells']==[100]*36 for m in store.tune['cylinder_trims']['fuel_maps'])
  results['legacy_json'][str(version)]='Fixed disabled idle, raw bytes/revision retained, expected trims preserved/neutralized';store.runtime.close();store.trigger_capture.close()
# Strategy2 is only accepted by schema5 and trims remain strict.
semi=distinct();semi['strategy']='semi_sequential_4cyl';semi['cylinder_trims']['enabled']=False
for version in (1,2,3,4):
 bad=copy.deepcopy(semi);bad['schema_version']=version
 if version<4:bad.pop('idle_control')
 if version<3:bad.pop('cylinder_trims')
 if version==1:bad.pop('timing')
 assert not b.engine_validate(compact(bad)),version
assert b.engine_validate(compact(semi))
with tempfile.TemporaryDirectory(prefix='semi-atomic-review-') as td:
 path=Path(td)/'tune.json';store=er.EngineStore(path,b);assert store.save(compact(dict(distinct(),revision=1)))[0]==200
 before=copy.deepcopy(store.tune);file_before=path.read_bytes();handle=store.runtime.handle
 bad=copy.deepcopy(before);bad['strategy']='semi_sequential_4cyl'
 assert store.save(compact(bad))[0]==422 and store.tune==before and path.read_bytes()==file_before and store.runtime.handle==handle and store.storage_ok
 session=Session(store);page_before=session.buffers[1]
 write=lambda offset,v:b'M'+struct.pack('<BBHH',0,1,offset,len(v))+v
 assert session.command(write(272,struct.pack('<I',2)))==b'\0' and session.command(b'b\0\1')==b'\x84'
 assert store.tune==before and path.read_bytes()==file_before and session.dirty
 assert session.command(write(4752,bytes(4)))==b'\0' and session.command(b'b\0\1')==b'\4'
 assert store.tune['strategy']==semi['strategy'] and not store.tune['cylinder_trims']['enabled']
 assert store.tune['cylinder_trims']['fuel_maps']==before['cylinder_trims']['fuel_maps'] and store.tune['cylinder_trims']['spark_deg']==before['cylinder_trims']['spark_deg']
 assert all(struct.pack('<f',store.tune['idle_control'][k])==struct.pack('<f',v) if isinstance(v,(int,float)) else store.tune['idle_control'][k]==v for k,v in before['idle_control'].items())
 assert struct.unpack_from('<I',session.buffers[1],268)[0]==before['revision']
 session.close();store.runtime.close();store.trigger_capture.close()
results['atomic_trim_rejection']='HTTP and typed burn reject enabled trims atomically; explicit disabling commits semi while retaining all nonneutral maps, spark offsets and idle configuration'
# The longer new strategy requires an allocation in the private template update.
with tempfile.TemporaryDirectory(prefix='semi-oom-review-') as td:
 path=Path(td)/'tune.json';initial=distinct();initial['revision']=1;initial['cylinder_trims']['enabled']=False;path.write_bytes(compact(initial));store=er.EngineStore(path,b);session=Session(store)
 assert session.command(write(272,struct.pack('<I',2)))==b'\0';prior=path.read_bytes();old_tune=copy.deepcopy(store.tune)
 budget=native.review_parse_allocations(session.handle);assert native.review_live()==0
 native.review_budget(budget);code=session.command(b'b\0\1');used=native.review_allocations();native.review_budget(-1)
 assert code==b'\x85' and native.review_live()==0 and store.tune==old_tune and path.read_bytes()==prior and session.dirty
 assert session.command(b'b\0\1')==b'\4' and store.tune['strategy']==semi['strategy'];session.close();store.runtime.close();store.trigger_capture.close()
results['strategy_string_oom']={'parse_allocations':budget,'allocations_attempted':used,'result':'Busy; no active/file change, no leak, staged bytes retained; retry succeeds'}
# Golden005 ABI and new enum are the only mapped-byte change.
golden=types.ModuleType('golden005');exec(subprocess.check_output(['git','show','HEAD:tools/engine_protocol.py']).decode(),golden.__dict__)
for mode in ('batch_wasted_4cyl','sequential_4cyl'):
 t=copy.deepcopy(semi);t['strategy']=mode;assert golden.pages(t)==pages(t)
 sp=pages(semi)[1];bp=pages(dict(semi,strategy='batch_wasted_4cyl'))[1];assert len(sp)==4992 and sp[:272]==bp[:272] and sp[276:]==bp[276:] and struct.unpack_from('<I',sp,272)[0]==2
 decoded=decode_pages({1:sp},semi);assert pages(decoded)[1]==sp and decoded['cylinder_trims']==semi['cylinder_trims']
view=types.SimpleNamespace(lock=threading.RLock(),tune=copy.deepcopy(semi),last_run=None,coherent_sample=lambda:{'flags':0})
for mode in ('batch_wasted_4cyl','sequential_4cyl'):
 view.tune['strategy']=mode
 with mock.patch('time.monotonic',return_value=100):assert golden.live_block(view)==live_block(view)
view.tune['strategy']='semi_sequential_4cyl';block=live_block(view);assert len(block)==256 and struct.unpack_from('<I',block,92)[0]==2
assert (R/'tuning/esp32-ecu-idle.ini').read_bytes()==subprocess.check_output(['git','show','HEAD:tuning/esp32-ecu-idle.ini'])
results['wire']='Full4992-byte pages unchanged for old modes; semi differs only enum272; old256-byte live bytes unchanged; semi strategy92=2; original005 INI byte-identical'
# Old005 preserves full idle and trim data; only006 admits enum2.
seq=distinct();text=export_msq(seq);oldtext=text.replace(SIGNATURE.decode(),IDLE_SIGNATURE.decode());assert import_msq(oldtext)==seq
assert import_msq(export_msq(semi))==semi
for value in ['"Semi-sequential"','2','3','"INVALID"']:
 root=ET.fromstring(oldtext)
 for e in root.iter(tag('constant')):
  if e.get('name')=='engineStrategy':e.text=value
 try:import_msq(ET.tostring(root));raise AssertionError('Old005 accepted '+value)
 except ValueError:pass
required=[]
for key in ['iac_algorithm',*[idle_name(k) for k in SCALARS],*[idle_name(k) for k,_ in ARRAYS]]:
 root=ET.fromstring(oldtext)
 for p in root.findall(tag('page')):
  for e in list(p.findall(tag('constant'))):
   if e.get('name')==key:p.remove(e)
 try:import_msq(ET.tostring(root));raise AssertionError('005 omitted '+key)
 except ValueError:required.append(key)
results['msq']='005 full idle/trims/revision preserved; all23 idle fields mandatory; new enum rejected by005;006 semi roundtrip preserves disabled nonneutral trims'
# New INI units and offsets still agree with current exports.
ini=(R/'tuning/esp32-ecu-semi.ini').read_text().split('[Constants]',1)[1].split('[ConstantsExtensions]',1)[0]
units={}
for line in ini.splitlines():
 m=re.match(r'\s*(\w+)\s*=\s*(scalar|array),\s*\w+,\s*\d+,\s*(?:\[[^]]+\],\s*)?"([^"]*)"',line)
 if m:units[m[1]]=m[3]
exported={e.get('name'):e.get('units','') for e in ET.fromstring(export_msq(semi)).iter(tag('constant'))};assert all(exported[k]==v for k,v in units.items())
results['ini_unit_fields_checked']=len(units)
(OUT/'native-results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
