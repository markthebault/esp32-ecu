from helpers import *
import copy,json,runpy,subprocess,types,threading,struct
from unittest import mock
from engine_protocol import DEFAULT,live_block
captured={};original=Path.write_text

def capture(path,data,*a,**kw):captured[str(path.resolve())]=data;return len(data)
Path.write_text=capture
try:
 runpy.run_path(str(R/'scripts/generate_tuning_wire.py'),run_name='readonly_generator')
 runpy.run_path(str(R/'scripts/generate_tunerstudio_ini.py'),run_name='readonly_generator')
finally:Path.write_text=original
assert len(captured)==3
for name,expected in captured.items():assert Path(name).read_text()==expected,name
old=types.ModuleType('old005');exec(subprocess.check_output(['git','show','HEAD:tools/engine_protocol.py']).decode(),old.__dict__)
trace=dict(time=3,rpm=1234,map_kpa=52,tps=5,lambda_measured=.98,pulse_ms=3,advance_deg=12,dwell_ms=2.75,ve_pct=88,target_lambda=1,ego=1.02,faults=64,synced=True,crank_synced=True,phase_synced=True,phase_required=True,phase_losses=4,cam_rejected=6,cylinders={'available':True,'enabled':False,'capacity_mask':2,'spark_clamp_mask':4,'retard_floor_mask':8,'proposals':[dict(pulse_ms=3+i,advance_deg=12-i,fuel_pct=101+i,duty_pct=5+i) for i in range(4)]})
view=types.SimpleNamespace(lock=threading.RLock(),tune=copy.deepcopy(DEFAULT),last_run={'trace':[trace],'summary':{'tune_revision':37}},completed_monotonic=10,coherent_sample=lambda:{'flags':1,'input_valid_mask':255,'idle':dict(available=True,target_rpm=950,feedforward_pct=30,p_term=1,i_term=2,d_term=3,duty_pct=36,flags=5,state_code=6,reason_code=2,algorithm_code=2)})
for mode in ('batch_wasted_4cyl','sequential_4cyl'):
 view.tune['strategy']=mode
 with mock.patch('time.monotonic',return_value=25):assert live_block(view)==old.live_block(view)
view.tune['strategy']='semi_sequential_4cyl'
with mock.patch('time.monotonic',return_value=25):new=live_block(view)
view.tune['strategy']='batch_wasted_4cyl'
with mock.patch('time.monotonic',return_value=25):expected=bytearray(old.live_block(view))
struct.pack_into('<I',expected,92,2);assert new==expected and len(new)==256
result={'generated_files_match':[str(Path(name).relative_to(R)) for name in captured],'generator_writes_intercepted':True,'populated_old_mode_live256_bytes_equal':True,'semi_populated_live_only_strategy92_changes':True}
(OUT/'generator-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
