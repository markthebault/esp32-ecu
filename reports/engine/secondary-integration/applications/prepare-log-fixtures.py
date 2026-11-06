from pathlib import Path
import csv,io,json,sys
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'tools'))
from engine_runtime import EngineRuntime
from engine_observability import EngineRecorder
from engine_log import export_msl
from test_secondary_model import tune,configure,inputs
out=Path(__file__).resolve().parent
config=tune();configure(config,'fuel','input','tps');config['secondary_tables']['fuel']['debounce_ms']=20
configure(config,'spark','conditional','tps');config['secondary_tables']['spark']['threshold']=20
runtime=EngineRuntime(config);recorder=EngineRecorder();trace=[];sil=[]
try:
 assert recorder.command(dict(action='start',period_ms=20,duration_s=3),1000000)==200
 for n in range(120):
  now=1000000+n*20000;raw=inputs(now,20<=n<70);raw['tps_pct']=30 if 40<=n<90 else 10
  if n in (20,22,24):raw['table_switches'][0]['level']=False
  if n==50:raw['table_switches'][0]['valid']=False
  if n==80:raw['table_switches'][0]['observed_us']=str(now+1)
  output=runtime.step(raw,now,use_decoder=False);sample=runtime.data();assert recorder.append(sample,now)
  trace.append(dict(now_us=now,inputs=raw,sample=sample))
  sil.append(dict(time=n*.02,plant_rpm=raw['rpm'],map_kpa=raw['map_kpa'],tps=raw['tps_pct'],lambda_measured=1,pulse_ms=output['pulse_ms'],advance_deg=output['advance_deg'],dwell_ms=output['dwell_ms'],ve_pct=output['ve_pct'],target_lambda=output['target_lambda'],ego=output['ego'],faults=output['faults'],synced=True,engine_sample=sample,secondary_tables=sample['secondary_tables'],load_model=sample['load_model']))
 recorder.command(dict(action='stop',log_id=1),3380001)
 engine=recorder.msl(1);direct=export_msl(sil,'synthetic_native_controller_probe_NOT_COUPLED_PLANT',config['strategy']).replace('UNVALIDATED REDUCED-ORDER SIMULATION','SYNTHETIC NATIVE CONTROLLER PROBE; PREDETERMINED RPM; NO PLANT')
 for name,body,count in [('engine188.msl',engine,188),('direct145.msl',direct,145)]:
  rows=list(csv.reader(io.StringIO(body),delimiter='\t'));assert len(rows)==124 and all(len(row)==count for row in rows[2:]);(out/name).write_text(body)
 (out/'application-log-inputs.json').write_text(json.dumps(dict(scope='Synthetic fixed-input native controller probe, not coupled engine acceptance',tune=config,observations=trace),separators=(',',':'))+'\n')
 print(json.dumps(dict(passed=True,engine_fields=188,direct_fields=145,rows=120,coupled_plant=False)))
finally:runtime.close();recorder.close()
