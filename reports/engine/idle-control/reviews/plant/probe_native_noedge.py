from pathlib import Path
import sys,json,hashlib
base=Path(__file__).resolve().parent;snapshot=base/'sources';sys.path.insert(0,str(snapshot/'tools'))
from target_runtime import TargetRuntime
cfg=json.loads((snapshot/'config/engine/defaults.json').read_text());cfg['settings']['idle_enabled']=True
cfg['idle_control']['algorithm']='open_loop';cfg['idle_control']['run_pct']=[100]*6;cfg['idle_control']['crank_pct']=[100]*6
r=TargetRuntime(cfg)
rows=[]
try:
 s=r.step(dict(rpm=200,synced=True,tps_pct=0),0,use_decoder=False)
 for now in range(0,30001,1000):
  while r.next_event_us()<=now:
   when=r.next_event_us();event=r.pop_event();rows.append({'when_us':when,'event':event,'next_us':r.next_event_us(),'stats':r.idle_status()})
  if now:r.step(dict(rpm=200,synced=True,tps_pct=0),now,use_decoder=False)
 result={'sample':s,'events':rows,'final':r.idle_status()}
 lib=snapshot/'.cache/engine/target-native/libtarget_engine.so';result['bridge_sha256']=hashlib.sha256(lib.read_bytes()).hexdigest()
 (base/'native-noedge-probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
finally:r.close()
