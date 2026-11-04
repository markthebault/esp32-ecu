"""Secondary schema/codec/control integration. These are native probes, not HIL."""
import copy,csv,io,json,math,struct,tempfile,unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from engine_runtime import EngineRuntime,EngineStore,R
from engine_protocol import Session,Stream,SIGNATURE,LOAD_SIGNATURE,pages,decode_pages,envelope,LIVE_BYTES
from engine_msq import export_msq,import_msq
from engine_observability import EngineRecorder
from secondary_config import KINDS,ENUMS,enum_offset,MAP_OFFSETS,rule_offset

def tune():
 t=json.loads((R/'config/engine/defaults.json').read_text());t['settings'].update(afterstart_pct=0,ego_enabled=False,dfco_enabled=False);t['engine']['injector_cc_min']=600;t['transient_enrichment']['mode']='off';return t
def configure(t,kind,mode,source='map'):
 r=t['secondary_tables'][kind];r.update(mode=mode,source=source,axis={'map':'map_kpa','tps':'tps_pct','imap_emap':'imap_emap_pct'}[source],cells='multiplier' if mode=='multiply' else 'adder' if mode=='add' else 'absolute',condition='tps_pct',threshold=20,debounce_ms=0)
 r['map']['load']=[10+i*100/15 for i in range(16)] if source=='map' else [i*(100 if source=='tps' else 600)/15 for i in range(16)]
 r['map']['cells']=[150 if mode=='multiply' else 10 if mode=='add' else 80 if kind=='fuel' else 20]*256
 if source=='imap_emap':t['load_model']['aux_role']='emap'
 return r
def inputs(now=1000000,level=True):return dict(rpm=2000,synced=True,phase_synced=True,map_kpa=45,tps_pct=25,aux_pressure_kpa=125,aux_pressure_qualified=True,table_switches=[dict(valid=True,level=level,observed_us=str(now)),dict(valid=True,level=level,observed_us=str(now))])

class SecondaryTests(unittest.TestCase):
 def runtime(self,t=None):
  r=EngineRuntime(t or tune());self.addCleanup(r.close);return r
 def recorder(self):
  r=EngineRecorder();self.addCleanup(r.close);return r
 def store(self,path):
  r=EngineStore(path);self.addCleanup(r.runtime.close);self.addCleanup(r.data_recorder.close);return r
 def test_modes_sources_strategies_and_coherent_metadata(self):
  for strategy in ('batch_wasted_4cyl','sequential_4cyl','semi_sequential_4cyl'):
   for mode in ENUMS['mode']:
    for source in ENUMS['source']:
     t=tune();t['strategy']=strategy
     for kind in KINDS:configure(t,kind,mode,source)
     r=self.runtime(t);o=r.step(inputs(),1000000,use_decoder=False);self.assertEqual(o['faults'],0,(strategy,mode,source,o))
     data=r.data()
     for kind in KINDS:
      d=data['secondary_tables'][kind];self.assertEqual(d['mode'],mode);self.assertEqual(d['source'],source);self.assertTrue(d['available'] and d['valid'] and d['evaluated']);self.assertEqual(d['active'],mode!='off');self.assertEqual(d['threshold'],20);self.assertEqual(d['condition'],'tps_pct')
     self.assertTrue(self.recorder().bridge.data_validate(json.dumps(data).encode()))
 def test_literal_f64_threshold_crossing_survives_f32_equal_diagnostic(self):
  t=tune();configure(t,'fuel','conditional');t['secondary_tables']['fuel']['threshold']=50;r=self.runtime(t)
  for value,active in [(49.999,False),(50,False),(50+1e-9,True)]:
   o=r.step(dict(rpm=1200,synced=True,tps_pct=value),1000000+int(active)*1000+int(value==50)*500,use_decoder=False)
   self.assertEqual(o['secondary_tables']['fuel']['active'],active)
  d=r.data();self.assertEqual(d['secondary_tables']['fuel']['condition_value'],50);self.assertTrue(d['secondary_tables']['fuel']['active']);self.assertTrue(self.recorder().bridge.data_validate(json.dumps(d).encode()))
 def test_switch_qualification_future_time_and_synthetic_provenance(self):
  t=tune();configure(t,'fuel','input');t['secondary_tables']['fuel']['debounce_ms']=20;r=self.runtime(t)
  for n in range(3):
   when=1000000+n*10000;o=r.step(inputs(when),when,use_decoder=False);self.assertEqual(bool(o['faults']&4),n<2)
  self.assertTrue(o['secondary_tables']['fuel']['input_qualified']);self.assertEqual(o['secondary_tables']['fuel']['input_source'],'synthetic_input')
  bad=inputs(1030000);bad['table_switches'][0]['observed_us']='18446744073709551615';o=r.step(bad,1030000,use_decoder=False);d=r.data()
  self.assertTrue(o['faults']&4);self.assertEqual(d['secondary_tables']['fuel']['reason'],'input_time_reversed');self.assertEqual(d['secondary_tables']['fuel']['input_observed_us'],'18446744073709551615');self.assertTrue(self.recorder().bridge.data_validate(json.dumps(d).encode()))
  bad=inputs(1040000);bad['table_switches'][0]['source']='target_protected_input'
  with self.assertRaises(ValueError):r.step(bad,1040000,use_decoder=False)
 def test_missing_target_style_input_and_ethanol_are_unknown_faults(self):
  t=tune();configure(t,'fuel','input');r=self.runtime(t);o=r.step(dict(rpm=1200,synced=True),1000000,use_decoder=False)
  self.assertTrue(o['faults']&4);self.assertEqual(o['secondary_tables']['fuel']['input_source'],'unavailable');self.assertIsNone(o['secondary_tables']['fuel']['input_observed_us'])
  t=tune();configure(t,'spark','conditional');t['secondary_tables']['spark'].update(condition='ethanol_pct',threshold=50);r=self.runtime(t)
  o=r.step(dict(rpm=220,synced=True),1000000,use_decoder=False);self.assertTrue(o['faults']&4);self.assertEqual(o['secondary_tables']['spark']['reason'],'required_ethanol_unavailable')
 def test_strict_schema_shapes_units_enums_and_physical_inhibition(self):
  r=self.runtime();base=tune();cases=[]
  for key,value in [('mode','unknown'),('source','follow_fuel'),('axis','tps_pct'),('cells','multiplier'),('condition','tps_pct'),('input_channel',256),('input_channel',True),('active_high',1),('debounce_ms',501),('threshold',-1)]:
   t=copy.deepcopy(base);t['secondary_tables']['fuel'][key]=value
   if key=='cells':t['secondary_tables']['fuel']['mode']='add'
   cases.append(t)
  for value in (None,{},[],dict(unexpected=0)):
   t=copy.deepcopy(base);t['secondary_tables']=value;cases.append(t)
  t=copy.deepcopy(base);del t['secondary_tables']['spark']['map'];cases.append(t)
  t=copy.deepcopy(base);t['secondary_tables']['fuel']['map']['load'][1]=10;cases.append(t)
  t=copy.deepcopy(base);t['physical_outputs']='enabled';cases.append(t)
  for t in cases:
   with self.assertRaises(ValueError):r.configure(t)
  t=copy.deepcopy(base);t['schema_version']=7
  with self.assertRaises(ValueError):r.configure(t) # A historical identity cannot smuggle new fields.
 def test_json7_retains_load_zero_coefficients_and_stored_bytes(self):
  old=json.loads((R/'config/engine/defaults-v7.json').read_text());old['maps']['ve']['cells'][0]=0;old['revision']=71;body=json.dumps(old,indent=2).encode()
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'old.json';path.write_bytes(body);store=self.store(path);self.assertTrue(store.storage_ok);self.assertEqual(path.read_bytes(),body);self.assertEqual(store.tune['revision'],71);self.assertEqual(store.tune['schema_version'],8);self.assertEqual(store.tune['load_model'],old['load_model']);self.assertEqual(store.tune['maps'],old['maps']);self.assertTrue(all(r['mode']=='off' for r in store.tune['secondary_tables'].values()))
   self.assertEqual(store.save(body)[0],200);self.assertEqual(json.loads(path.read_bytes())['schema_version'],8)
 def test_own008_actual_file_keeps_model_and_full_new_msq_roundtrip(self):
  old=import_msq((R/'tuning/examples/tunerstudio-load-roundtrip.msq').read_bytes());self.assertEqual(old['load_model']['fuel_source'],'tps');self.assertEqual(old['load_model']['afr'],'measured');self.assertEqual(old['load_model']['fixed_baro_kpa'],99.5);self.assertTrue(all(r['mode']=='off' for r in old['secondary_tables'].values()))
  t=tune();configure(t,'fuel','multiply','tps');configure(t,'spark','add','imap_emap');t['secondary_tables']['fuel']['map']['cells'][231]=123.125;t['secondary_tables']['spark']['map']['cells'][17]=-2.5
  text=export_msq(t);self.assertIn(SIGNATURE.decode(),text);self.assertEqual(pages(import_msq(text)),pages(t));self.assertEqual(len(pages(t)[1]),8192)
  units={e.get('name'):e.get('units') for e in ET.fromstring(text).iter() if e.tag.endswith('}constant')}
  for key,unit in dict(secondary_fuel_threshold='% TPS',secondary_fuel_mapLoad='% TPS',secondary_fuel_mapTable='% multiplier',secondary_spark_threshold='% TPS',secondary_spark_mapLoad='% IMAP/EMAP',secondary_spark_mapTable='deg delta').items():self.assertEqual(units[key],unit)
  with self.assertRaises(ValueError):import_msq(text.replace(SIGNATURE.decode(),LOAD_SIGNATURE.decode()))
 def test_dense_f32_tune_over24k_saves_and_typed_page_preserves_every_cell(self):
  t=tune()
  for kind in KINDS:configure(t,kind,'multiply')
  for name,m in [(k,t['maps'][k]) for k in ('ve','spark','lambda')]+[(k,t['secondary_tables'][k]['map']) for k in KINDS]:
   for i in range(256):
    raw=(.75+i/1000 if name=='lambda' else 10+i/100 if name=='spark' else 1e-38*(1+i/256))
    m['cells'][i]=struct.unpack('<f',struct.pack('<f',raw))[0]
  body=json.dumps(t,separators=(',',':')).encode();self.assertGreater(len(body),24576);self.assertLess(len(body),49152)
  with tempfile.TemporaryDirectory() as d:
   store=self.store(Path(d)/'dense.json');self.assertEqual(store.save(body)[0],200);self.assertEqual(pages(decode_pages(pages(store.tune),store.tune)),pages(store.tune))
 def test_reserved_regions_and_full_u32_reject_before_narrowing(self):
  t=tune();p=pages(t)[1]
  for offset in (292,511,4756,4767,5116,5119,5176,5375,5448,5503,7808,8191):
   bad=bytearray(p);bad[offset]=1
   with self.assertRaises(ValueError):decode_pages({1:bad},t)
  for offset in (rule_offset('fuel')+28,rule_offset('fuel')+32,enum_offset('spark','mode'),enum_offset('spark','source')):
   bad=bytearray(p);struct.pack_into('<I',bad,offset,256)
   with self.assertRaises(ValueError):decode_pages({1:bad},t)
 def test_atomic_two_map_burn_stale_edit_and_complete_runtime_reply(self):
  with tempfile.TemporaryDirectory() as d:
   store=self.store(Path(d)/'t.json');stream=Stream(store);self.addCleanup(stream.close);t=copy.deepcopy(store.tune);configure(t,'fuel','multiply');configure(t,'spark','add');page=pages(t)[1]
   for offset in range(0,len(page),256):self.assertEqual(stream.session.command(b'M'+struct.pack('<BBHH',0,1,offset,256)+page[offset:offset+256]),b'\0')
   self.assertEqual(store.tune['secondary_tables']['fuel']['mode'],'off');self.assertEqual(stream.session.command(b'b\0\1'),b'\4');self.assertEqual(store.tune['secondary_tables']['fuel']['mode'],'multiply');self.assertEqual(store.tune['secondary_tables']['spark']['mode'],'add')
   replies=stream.feed(envelope(b'r'+struct.pack('<BBHH',0,0x30,0,LIVE_BYTES)),1000000);self.assertEqual(len(replies[0]),647)
   before=bytes(stream.session.buffers[1]);external=copy.deepcopy(store.tune);external['secondary_tables']['spark']['map']['cells'][0]=3;self.assertEqual(store.save(json.dumps(external).encode())[0],200)
   self.assertEqual(stream.session.command(b'M'+struct.pack('<BBHH',0,1,MAP_OFFSETS['fuel']+128,4)+struct.pack('<f',110)),b'\x84');self.assertEqual(bytes(stream.session.buffers[1]),before)
 def test_malformed_observations_reject_and_188_column_msl_keeps_codes(self):
  r=self.runtime();r.step(inputs(),1000000,use_decoder=False);data=r.data();rec=self.recorder();self.assertTrue(rec.bridge.data_validate(json.dumps(data).encode()))
  for key,value in [('threshold',None),('debounce_ms',None),('input_observed_us','1'),('mode_code',5),('flags',0),('extra',0),('valid',False)]:
   bad=copy.deepcopy(data);bad['secondary_tables']['fuel'][key]=value;self.assertFalse(rec.bridge.data_validate(json.dumps(bad).encode()),key)
  self.assertEqual(rec.command(dict(action='start',period_ms=20,duration_s=1),1000000),200);self.assertTrue(rec.append(data,1000000));rec.command(dict(action='stop',log_id=1),1000001)
  rows=list(csv.reader(io.StringIO(rec.msl(1)),delimiter='\t'));self.assertEqual([len(row) for row in rows[2:]],[188,188,188]);values=dict(zip(rows[2],rows[4]));self.assertEqual(values['SecFuelAvailable'],'1');self.assertEqual(values['SecFuelMode'],'0');self.assertEqual(values['SecFuelObservedUs'],'NaN')

if __name__=='__main__':unittest.main(verbosity=2)
