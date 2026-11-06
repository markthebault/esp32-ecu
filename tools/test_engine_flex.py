"""Cross-surface flex integration tests; synthetic input and inhibited control."""
import copy,csv,io,json,struct,tempfile,unittest
from pathlib import Path
from engine_runtime import EngineRuntime,EngineStore,R
from target_runtime import TargetRuntime
from engine_protocol import DEFAULT,SIGNATURE,pages,decode_pages,live_block,Session
from engine_msq import export_msq,import_msq
from engine_observability import EngineRecorder,encoded
from flex_config import DEFAULT as FLEX_DEFAULT,OFFSETS,BOOLEANS,CAPTURE_FLOATS,ARRAYS,FLAGS,CODES,TIMES,VALUES
from flex_stimulus import FlexStimulus

def tune():
 t=copy.deepcopy(DEFAULT);t['flex_fuel']['correction'].update(enabled=True,temperature_enabled=True,fuel_pct=[150]*6,spark_deg=[5]*6,temperature_pct=[80]*6)
 return t
def edges(r,start=920000,cycles=8,period=10000,width=3000):
 r.flex_edge(start,True)
 for n in range(1,cycles+1):r.flex_edge(start+n*period-width,False);r.flex_edge(start+n*period,True)
 return start+cycles*period
def step(r,time=1000000,**kw):return r.step(dict(rpm=2000,synced=True,phase_synced=True,**kw),time,use_decoder=False)

class FlexIntegration(unittest.TestCase):
 def runtime(self,t=None,kind=EngineRuntime):
  r=kind(t or tune());self.addCleanup(r.close);return r
 def recorder(self):
  r=EngineRecorder();self.addCleanup(r.close);return r
 def test_both_host_bridges_use_raw_edges_and_same_captured_time(self):
  for kind in (EngineRuntime,TargetRuntime):
   with self.subTest(kind=kind.__name__):
    r=self.runtime(kind=kind);edges(r);o=step(r);f=o['flex_fuel'];self.assertTrue(f['raw_capture_qualified']);self.assertTrue(f['control_ok']);self.assertEqual(f['source'],'synthetic_edges');self.assertEqual(f['ethanol_pct'],50);self.assertEqual(f['fuel_temp_c'],42.5)
    self.assertEqual((f['fuel_pct'],f['temperature_pct'],f['spark_add_deg']),(150,80,5));self.assertEqual(f['sample_us'],'1000000');self.assertEqual(f['sample_age_ms'],0)
    o=step(r,1100000);self.assertEqual(o['flex_fuel']['sample_us'],'1000000');self.assertEqual(o['flex_fuel']['sample_age_ms'],100)
    o=step(r,1250001);self.assertFalse(o['flex_fuel']['control_ok']);self.assertTrue(o['fuel_cut'] and o['spark_cut']);self.assertEqual(o['flex_fuel']['reason'],'stale')
 def test_explicit_scalar_selection_cannot_be_used_for_corrections(self):
  for kind in (EngineRuntime,TargetRuntime):
   t=copy.deepcopy(DEFAULT);t['secondary_tables']['fuel'].update(mode='conditional',condition='ethanol_pct',threshold=40)
   r=self.runtime(t,kind);o=step(r,ethanol_pct=50,ethanol_qualified=True);f=o['flex_fuel'];self.assertTrue(f['value_qualified']);self.assertFalse(f['raw_capture_qualified']);self.assertEqual(f['source'],'synthetic_value');self.assertIsNone(f['frequency_hz']);self.assertTrue(o['secondary_tables']['fuel']['active'])
   t['flex_fuel']['correction']['enabled']=True;r.configure(t);o=step(r,ethanol_pct=50,ethanol_qualified=True);self.assertFalse(o['flex_fuel']['control_ok']);self.assertEqual(o['flex_fuel']['reason'],'raw_capture_required')
   with self.assertRaises(ValueError):step(r,use_flex_capture=True,ethanol_pct=50,ethanol_qualified=True)
 def test_same_calibration_reconfigure_cannot_relabel_old_window(self):
  for kind in (EngineRuntime,TargetRuntime):
   r=self.runtime(kind=kind);edges(r);self.assertTrue(step(r)['flex_fuel']['raw_capture_qualified']);t=copy.deepcopy(r.tune);t['revision']+=1;t['flex_fuel']['correction']['fuel_pct']=[120]*6;r.configure(t)
   f=step(r,1000001)['flex_fuel'];self.assertFalse(f['raw_capture_qualified']);self.assertEqual(f['configuration_revision'],2);self.assertEqual(f['config_epoch'],'2');self.assertTrue(f['pending_fault']);generation=f['fault_generation']
   f=step(r,1000002)['flex_fuel'];self.assertFalse(f['pending_fault']);self.assertEqual(f['acknowledged_generation'],generation)
   end=edges(r,1010000,7);f=step(r,end)['flex_fuel'];self.assertFalse(f['raw_capture_qualified'])
   r.flex_edge(end+7000,False);r.flex_edge(end+10000,True);f=step(r,end+10000)['flex_fuel'];self.assertTrue(f['raw_capture_qualified']);self.assertEqual(f['fuel_pct'],120);self.assertEqual(f['configuration_revision'],2)
 def test_fault_must_be_consumed_by_completed_control(self):
  r=self.runtime();edges(r);step(r);r.flex_edge(1000001,True) # repeated high
  edges(r,1020000);f=step(r,1100000)['flex_fuel'];self.assertTrue(f['pending_fault']);self.assertFalse(f['raw_capture_qualified']);self.assertEqual(f['reason'],'repeated_level')
  f=step(r,1100001)['flex_fuel'];self.assertFalse(f['pending_fault']);self.assertTrue(f['raw_capture_qualified'])
 def test_tune_schema1_through8_migrate_neutral_and_keep_original_bytes(self):
  for schema in range(1,9):
   old=json.loads((R/f'config/engine/defaults-v{max(2,schema)}.json').read_text());old['revision']=81
   if schema==1:old['schema_version']=1;del old['timing']
   if schema==8:old['secondary_tables']['fuel']['map']['cells'][3]=91.25
   body=json.dumps(old,indent=1).encode()
   with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'tune.json';path.write_bytes(body);store=EngineStore(path)
    try:self.assertTrue(store.storage_ok);self.assertEqual(store.tune['schema_version'],11);self.assertEqual(store.tune['flex_fuel'],FLEX_DEFAULT);self.assertEqual(store.tune['revision'],81);self.assertEqual(path.read_bytes(),body)
    finally:store.runtime.close();store.data_recorder.close()
    if schema==8:self.assertEqual(store.tune['secondary_tables'],old['secondary_tables'])
 def test_schema9_requires_complete_strict_flex_config(self):
  mutations=[]
  for name in ('input_confirmed','capture','correction'):
   t=tune();del t['flex_fuel'][name];mutations.append(t)
  for key,value in [('cycles',256),('cycles',2.5),('low_hz',True),('high_hz',51),('fault_hz',151),('stale_ms',1),('filter_ms',5001),('unexpected',1)]:
   t=tune();t['flex_fuel']['capture'][key]=value;mutations.append(t)
  for key,value in [('enabled',1),('fuel_pct',[100]*5),('ethanol_bins',[0,20,20,60,80,100]),('spark_deg',[41]*6),('temperature_c',[-40,0,20,40,80,124])]:
   t=tune();t['flex_fuel']['correction'][key]=value;mutations.append(t)
  for t in mutations:
   with self.assertRaises(ValueError):self.runtime(t)
 def test_complete_page_roundtrip_reserved_tail_and_full_width_rejection(self):
  t=tune();t['flex_fuel']['input_confirmed']=True;t['flex_fuel']['capture']['filter_ms']=125.5
  b=pages(t)[1];self.assertEqual(len(b),12288);self.assertEqual(pages(decode_pages({1:b},DEFAULT)),{1:b})
  for offset in (7968,8191):
   bad=bytearray(b);bad[offset]=1
   with self.assertRaises(ValueError):decode_pages({1:bad},DEFAULT)
  for name in BOOLEANS+('cycles',):
   for value in (256,4294967295):
    bad=bytearray(b);struct.pack_into('<I',bad,OFFSETS[name],value)
    with self.assertRaises(ValueError):decode_pages({1:bad},DEFAULT)
 def test_own010_msq_and_nine_retained_identities(self):
  t=tune();text=export_msq(t);self.assertIn(SIGNATURE.decode(),text);self.assertEqual(pages(import_msq(text)),pages(t));self.assertEqual(import_msq(text)['flex_fuel'],t['flex_fuel'])
  for path in (R/'tuning/examples').glob('*.msq'):
   if SIGNATURE in path.read_bytes():continue
   migrated=import_msq(path.read_bytes());self.assertEqual(migrated['schema_version'],11)
   if b'ESP32ECU DEV 010 INHIBITED' in path.read_bytes():self.assertEqual(migrated['flex_fuel']['capture']['filter_ms'],130.5)
   else:self.assertEqual(migrated['flex_fuel'],FLEX_DEFAULT)
   if 'DEV 011' not in path.read_text():self.assertFalse(migrated['boost_control']['pressure_enabled'])
   else:self.assertTrue(migrated['boost_control']['pressure_enabled'])
 def test_runtime_json_log_preserves_flags_and_exact_u64(self):
  r=self.runtime();edges(r);step(r);s=r.data();f=s['flex_fuel'];f['raw_edges']='9007199254740993'
  d=self.recorder();self.assertEqual(d.bridge.data_validate(encoded(s)),1);self.assertEqual(d.command(dict(action='start',period_ms=20,duration_s=1),1000000),200);self.assertTrue(d.append(s,1000000));d.command(dict(action='stop',log_id=1),1000001)
  q=d.page(1,0)['records'][0]['sample']['flex_fuel'];self.assertEqual(q['raw_edges'],'9007199254740993');self.assertEqual(q['sample_us'],f['sample_us']);self.assertEqual(q['raw_capture_qualified'],True)
  rows=list(csv.reader(io.StringIO(d.msl(1)),delimiter='\t'));self.assertEqual([len(x) for x in rows[2:]],[265]*3);log=dict(zip(rows[2],rows[4]));self.assertEqual(log['FlexRawEdges'],'9007199254740993');self.assertEqual(log['FlexRawCaptureQualified'],'1');self.assertEqual(log['FlexAvailable'],'1')
  cases=[('source_code',4),('source','target_capture'),('reason_code',23),('pending_fault',True),('capture_valid',False),('raw_edges','01'),('sample_us','18446744073709551616'),('fuel_pct',None),('unexpected',0)]
  for key,value in cases:
   bad=copy.deepcopy(s);bad['flex_fuel'][key]=value;self.assertFalse(d.bridge.data_validate(encoded(bad)),key)
 def test_live_append_and_legacy_radio_suppression(self):
  with tempfile.TemporaryDirectory() as directory:
   store=EngineStore(Path(directory)/'t.json')
   try:
    store.runtime.configure(tune());step(store.runtime,900000);edges(store.runtime);step(store.runtime);s=store.runtime.data();store.coherent_sample=lambda:s
    b=live_block(store);self.assertEqual(len(b),1152);self.assertEqual(struct.unpack_from('<10f',b,640),(100,3000,50,42.5,50,42.5,0,150,5,80))
    self.assertEqual(struct.unpack_from('<I',b,680)[0],sum(1<<n for n,key in enumerate(FLAGS)if s['flex_fuel'][key]));self.assertEqual(struct.unpack_from('<7Q',b,712),tuple(int(s['flex_fuel'][key])for key in TIMES));self.assertEqual(b[796:832],bytes(36))
    rec=self.recorder()
    for schema in (1,2,3,4):
     with self.assertRaises(ValueError):rec.frame(s,b'k'*16,b'n'*32,1,1,schema=schema)
   finally:store.runtime.close();store.data_recorder.close()
 def test_stimulus_retains_waveform_when_queries_are_refined(self):
  class Sink:
   def __init__(self):self.events=[]
   def flex_edge(self,time,high):self.events.append((time,high))
  results=[]
  for increment in (1,997,20000):
   sink=Sink();wave=FlexStimulus(dict(frequency_hz=99.7,low_pulse_us=2999,dropout_at_s=.1))
   for now in range(0,120001,increment):wave.feed(sink,now)
   wave.feed(sink,120001);results.append(sink.events);self.assertTrue(all(time<100000 for time,_ in sink.events));self.assertEqual(wave.summary()['source'],'synthetic_edges')
  self.assertEqual(results[0],results[1]);self.assertEqual(results[1],results[2])
  for bad in (True,{},dict(frequency_hz=True,low_pulse_us=3000),dict(frequency_hz=500,low_pulse_us=3000),dict(frequency_hz=100,low_pulse_us=3000,dropout_at_s=None),dict(frequency_hz=100,low_pulse_us=3000,extra=1)):
   with self.assertRaises(ValueError):FlexStimulus(bad)

if __name__=='__main__':unittest.main()
