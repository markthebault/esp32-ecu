"""Idle tune migration, whole-page transactions, observations and NC actuator physics."""
import copy,csv,io,json,math,struct,tempfile,unittest
from pathlib import Path
from engine_runtime import EngineRuntime,EngineStore,R
from engine_msq import export_msq,import_msq,tag
from engine_protocol import DEFAULT,pages,decode_pages,Session,LIVE_BYTES
from idle_config import SCALAR_OFFSETS,ARRAY_OFFSETS
from idle_valve_plant import IdleValve
from target_runtime import TargetRuntime

class IdleTests(unittest.TestCase):
 def test_all_historical_json_keeps_source_and_disables_former_virtual_flag(self):
  for schema in (1,2,3):
   old=json.loads((R/f'config/engine/defaults-v{3 if schema==3 else 2}.json').read_text());old['schema_version']=schema;old['revision']=71;old['settings']['idle_enabled']=True
   if schema==1:old.pop('timing')
   with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'old.json';body=json.dumps(old).encode();path.write_bytes(body);store=EngineStore(path)
    self.assertTrue(store.storage_ok);self.assertEqual(path.read_bytes(),body);self.assertEqual(store.tune['revision'],71)
    self.assertEqual(store.tune['schema_version'],11);self.assertFalse(store.tune['settings']['idle_enabled']);self.assertEqual(store.tune['idle_control']['algorithm'],DEFAULT['idle_control']['algorithm']);self.assertAlmostEqual(store.tune['idle_control']['derivative_filter_s'],DEFAULT['idle_control']['derivative_filter_s'])
 def test_all_historical_msqs_disable_new_output_without_resetting_supported_trims(self):
  for filename in ('tunerstudio-roundtrip.msq','tunerstudio-sequential-roundtrip.msq','tunerstudio-cylinder-roundtrip.msq','tunerstudio-development-roundtrip.msq'):
   path=R/'tuning/examples'/filename
   t=import_msq(path.read_bytes());self.assertFalse(t['settings']['idle_enabled']);self.assertEqual(t['idle_control'],DEFAULT['idle_control'])
  t=import_msq((R/'tuning/examples/tunerstudio-development-roundtrip.msq').read_bytes());self.assertTrue(t['cylinder_trims']['enabled']);self.assertEqual(t['cylinder_trims']['spark_deg'][1],-2.5)
 def test_own005_nondefault_every_idle_field_roundtrips_native_msq_and_binary(self):
  t=copy.deepcopy(DEFAULT);t['settings']['idle_enabled']=True;c=t['idle_control'];c.update(algorithm='open_loop',frequency_hz=80,control_period_ms=125,min_pct=5,max_pct=90,tps_closed_pct=1.25,tps_hysteresis_pct=.75,entry_rpm_above=150,exit_rpm_above=400,entry_delay_s=.5,afterstart_taper_s=3,dashpot_pct=6,dashpot_decay_pct_s=12,slew_pct_s=150,integral_limit_pct=30,kd=.001,derivative_filter_s=.25,fast_idle_temp_c=45,fast_idle_hysteresis_c=6)
  c.update(coolant_c=[-30,5,25,45,75,120],run_pct=[70,55,40,30,15,10],crank_pct=[80,70,60,50,40,30],target_add_rpm=[500,350,250,150,50,0])
  r=EngineRuntime(t);canonical=r.tune;r.close();self.assertEqual(import_msq(export_msq(canonical)),canonical)
  p=pages(canonical);decoded=decode_pages(p,canonical);self.assertEqual(pages(decoded),p);self.assertEqual(decoded['idle_control']['algorithm'],canonical['idle_control']['algorithm']);self.assertAlmostEqual(decoded['idle_control']['kd'],canonical['idle_control']['kd']);self.assertEqual(decoded['idle_control']['crank_pct'],canonical['idle_control']['crank_pct'])
 def test_invalid_disabled_idle_configuration_is_rejected_without_partial_burn(self):
  with tempfile.TemporaryDirectory() as d:
   store=EngineStore(Path(d)/'tune.json');s=Session(store)
   try:
    for key,value in [('frequency_hz',49),('control_period_ms',0),('min_pct',100),('exit_rpm_above',1),('kd',float('nan'))]:
     s.feed(b'\xf0F',100000+100000*list(SCALAR_OFFSETS).index(key));offset=SCALAR_OFFSETS[key];body=struct.pack('<f',value)
     self.assertEqual(s.command(b'M'+struct.pack('<BBHH',0,1,offset,4)+body),b'\0');self.assertEqual(s.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['revision'],1);self.assertFalse(store.path.exists())
   finally:s.close()
 def test_idle_observation_and_logs_keep_unavailable_distinct(self):
  from engine_observability import EngineRecorder
  r=EngineRuntime();r.step(dict(rpm=900,synced=True,tps_pct=0),1000,use_decoder=False);sample=r.data();self.assertTrue(sample['idle']['available']);self.assertEqual(sample['idle']['state'],'disabled')
  rec=EngineRecorder();rec.command(dict(action='start',period_ms=20,duration_s=1),1000);self.assertTrue(rec.append(sample,1000));rec.command(dict(action='stop',log_id=1),2000)
  rows=list(csv.reader(io.StringIO(rec.msl(1)),delimiter='\t'));self.assertEqual([len(x) for x in rows[2:]],[265,265,265]);self.assertEqual(dict(zip(rows[2],rows[4]))['IdleAvailable'],'1');rec.close();r.close()
 def test_full_duty_boundary_is_progress_and_not_a_fabricated_gpio_edge(self):
  t=copy.deepcopy(DEFAULT);t['settings']['idle_enabled']=True;t['idle_control']['algorithm']='on_off'
  r=TargetRuntime(t)
  try:
   r.step(dict(rpm=300,synced=True,tps_pct=0,clt_c=0),0,use_decoder=False)
   self.assertEqual(r.pop_event()[0:2],(8,True))
   for now in range(1000,20001,1000):
    r.progress(now)
    if now<20000:r.step(dict(rpm=300,synced=True,tps_pct=0,clt_c=0),now,use_decoder=False)
    while r.next_event_us()<=now:
     event=r.pop_event();self.assertIsNotNone(event)
     if event[0] not in (-1,None):self.assertNotEqual(event[:2],(8,True))
   self.assertEqual(r.idle_status()['rises'],'1')
  finally:r.close()
 def test_independent_coil_ledger_and_finite_nc_closure(self):
  valve=IdleValve();valve.edge(True)
  for _ in range(1000):valve.step(.0001,14)
  before=valve.snapshot();self.assertGreater(before['current_a'],1.7);self.assertGreater(before['opening_pct'],70)
  valve.cut();valve.step(.0001,14);after=valve.snapshot();self.assertGreater(after['current_a'],0);self.assertGreater(after['opening_pct'],0)
  for _ in range(10000):valve.step(.0001,14)
  final=valve.snapshot();self.assertEqual(final['current_a'],0);self.assertLess(final['opening_pct'],.001);self.assertLess(abs(final['electrical_residual_j']),1e-9)
 def test_stuck_and_disconnected_are_actuator_failures_not_fake_ecu_faults(self):
  for mode,expected in [('stuck_closed',0),('stuck_open',100),('disconnected',0)]:
   valve=IdleValve(mode);valve.edge(True)
   for _ in range(1000):valve.step(.0001,14)
   self.assertAlmostEqual(valve.opening_pct,expected);self.assertLess(abs(valve.snapshot()['electrical_residual_j']),1e-9)
   if mode=='disconnected':self.assertEqual(valve.current,0)
 def test_sil_integrates_to_cut_timestamp_before_removing_electrical_drive(self):
  from unittest.mock import patch
  from engine_sil import Simulation
  class EventReplay:
   def __init__(self,tune):self.tune=copy.deepcopy(tune);self.events=[(0,8,True,0,0),(150,None,False,0,0)]
   def wheel(self):pass
   def step(self,*a,**k):return dict(faults=0,state='running',synced=True,advance_deg=10)
   def next_event_us(self):return self.events[0][0] if self.events else 2**64-1
   def pop_event(self):return self.events.pop(0)[1:]
   def cut(self):pass
   def data(self):return {}
   def idle_status(self):return {}
   def trigger(self,*a):return 0
   def close(self):pass
  t=copy.deepcopy(DEFAULT);t['settings']['idle_enabled']=True
  with patch('target_runtime.TargetRuntime',EventReplay):result=Simulation(t,duration_s=1).run()
  valve=result['summary']['idle_valve'];expected=IdleValve();expected.edge(True);expected.step(.00015,13.8)
  self.assertAlmostEqual(valve['energized_s'],.00015);self.assertAlmostEqual(valve['source_j'],expected.source_j,places=12)
 def test_005_offsets_and_tunerstudio_pages_are_frozen(self):
  from idle_config import SCALARS,ARRAYS
  self.assertEqual(SCALAR_OFFSETS['frequency_hz'],4772);self.assertEqual(SCALAR_OFFSETS['fast_idle_hysteresis_c'],4840)
  self.assertEqual(ARRAY_OFFSETS,dict(coolant_c=4844,run_pct=4868,crank_pct=4892,target_add_rpm=4916))
  self.assertEqual(len(SCALARS),18);self.assertEqual(ARRAYS,(('coolant_c',6),('run_pct',6),('crank_pct',6),('target_add_rpm',6)))
  ini=(R/'tuning/esp32-ecu-semi.ini').read_text();tables=[line for line in ini.splitlines() if line.strip().startswith('table =')]
  self.assertEqual(len(tables),7);self.assertTrue(all(line.rstrip().endswith(', 1') for line in tables))
  for field in ('iacAvailable','dataSource','snapshotAgeMs'):self.assertIn('entry = '+field,ini.split('[Datalog]')[1])
 def test_sil_msl_contains_proposals_dispatcher_and_model_without_invented_measurements(self):
  from engine_sil import Simulation
  from engine_log import export_msl
  t=copy.deepcopy(DEFAULT);t['settings']['idle_enabled']=True;run=Simulation(t,duration_s=1).run()
  rows=list(csv.reader(io.StringIO(export_msl(run['trace'],'warm_start')),delimiter='\t'));self.assertEqual(len(rows[2]),245);self.assertTrue(all(len(r)==245 for r in rows[3:]))
  last=dict(zip(rows[2],rows[-1]));source=run['trace'][-1]
  self.assertEqual(last['IdleAvailable'],'1');self.assertEqual(last['IdlePwmAvailable'],'1');self.assertEqual(last['ValveModelAvailable'],'1')
  self.assertAlmostEqual(float(last['ValveCurrent']),source['idle_valve']['current_a'],places=7)
  self.assertEqual(last['IdlePwmSequence'],source['idle_pwm']['sequence'])
 def test_idle_availability_requires_boolean_and_unknown_values_require_null(self):
  from engine_observability import load_bridge,encoded
  r=EngineRuntime();r.step(dict(rpm=900,synced=True,tps_pct=0),1000,use_decoder=False);sample=r.data();r.close();bridge=load_bridge()
  for flag in (0,None,'false'):
   candidate=copy.deepcopy(sample);candidate['idle']['available']=flag
   self.assertFalse(bridge.data_validate(encoded(candidate)))
  candidate=copy.deepcopy(sample);candidate['idle'].pop('available');self.assertFalse(bridge.data_validate(encoded(candidate)))
  candidate=copy.deepcopy(sample);candidate['idle']['available']=False;self.assertFalse(bridge.data_validate(encoded(candidate)))
  for field in ('target_rpm','duty_pct','feedforward_pct','p_term','i_term','d_term'):candidate['idle'][field]=None
  self.assertTrue(bridge.data_validate(encoded(candidate)))
 def test_actual_tunerstudio005_saved_mode_frequency_and_curve_point(self):
  t=import_msq((R/'tuning/examples/tunerstudio-idle-roundtrip.msq').read_bytes());self.assertTrue(t['settings']['idle_enabled'])
  self.assertEqual(t['idle_control']['algorithm'],'open_loop');self.assertEqual(t['idle_control']['frequency_hz'],90);self.assertEqual(t['idle_control']['run_pct'],[65,50,38,30,17.01,17])
  self.assertEqual(len(pages(t)[1]),12288)

if __name__=='__main__':unittest.main(verbosity=2)
