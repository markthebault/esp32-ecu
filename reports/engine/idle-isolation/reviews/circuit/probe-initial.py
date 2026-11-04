"""Independent read-only review of the conditional ngspice experiment.

No manufacturer macro-model, physical qualification or complete fault coverage
is implied. Additional deck mutations are declared reviewer sensitivity controls.
"""
import concurrent.futures,gzip,hashlib,io,json,re,shutil,subprocess
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DATA=ROOT/'.cache/engine/idle-isolation/circuit-published'
OLD=ROOT/'.cache/engine/idle-isolation/circuit-reviewed'
NG=ROOT/'.cache/tools/ngspice-package/payload/usr/bin/ngspice'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return np.loadtxt(io.BytesIO(gzip.decompress(Path(p).read_bytes())),skiprows=1)
def avg(a,col,seconds=.0005):
 m=a[:,0]>a[-1,0]-seconds;t=a[m,0];return float(np.trapezoid(a[m,col],t)/(t[-1]-t[0]))
def metrics(a):
 return dict(rows=len(a),first_time_s=float(a[0,0]),last_time_s=float(a[-1,0]),
    final_coil_a=avg(a,8),final_gate_v=avg(a,2),final_carrier_return_a=avg(np.column_stack([a[:,:11],np.abs(a[:,11]),a[:,12:]]),11),
    maximum_carrier_return_a=float(np.max(np.abs(a[:,11]))),maximum_coil_a=float(np.max(a[:,8])),
    final_run_source_a=-avg(a,15) if a.shape[1]>15 else None,
    final_run_v=avg(a,13) if a.shape[1]>13 else None,
    final_main_input_v=avg(a,14) if a.shape[1]>14 else None,
    gate_high_us=float(np.trapezoid((a[:,2]>4).astype(float),a[:,0])*1e6))
def one(spec):
 name,base,mutation=spec;p=DATA/base/'circuit.cir';deck=p.read_text()
 if mutation=='optical_block':
  old='Bpwr rawpw ag V=(i(Vpwmled)>0.005 ? 1 : 0)';assert old in deck;deck=deck.replace(old,'Bpwr rawpw ag V=0')
  assert 'v(pwf)=1' in deck;deck=deck.replace('v(pwf)=1','v(pwf)=0').replace('v(pwmn)=0.3826','v(pwmn)=5.1645')
 elif mutation=='supervisor_block':
  old='Bpg pgout ag V=(v(pgstate,ag)>0.5 ? max(v(rail,ag),0) : 0)';assert old in deck;deck=deck.replace(old,'Bpg pgout ag V=0')
 elif mutation=='extra_main_load':
  # Only a conditional 500ohm sensitivity load:20mA at10V,not an actual
  # VNP35N07-E fault model or a physical loading acceptance result.
  deck=deck.replace('.control','Rreview_main_sensitivity mainin cg 500\n.control')
 elif mutation=='cold_half_step':
  deck=deck.replace('tran 1.9999999999999998e-05 0.8 0 1.9999999999999998e-05 uic','tran 10u 0.8 0 10u uic')
  if 'tran 10u 0.8 0 10u uic' not in deck:
   deck=re.sub(r'^tran .* 0.8 0 .* uic$', 'tran 10u 0.8 0 10u uic',deck,flags=re.M)
  assert 'tran 10u 0.8 0 10u uic' in deck
 elif mutation:raise ValueError(mutation)
 old='i(Vcarrier_return) i(Vactreturn)';assert old in deck
 deck=deck.replace(old,old+' v(run) v(mainin) i(Vrun) i(Vgpio) i(Vcarrier) i(Vbat)')
 d=HERE/'probes'/name;d.mkdir(parents=True,exist_ok=False);(d/'circuit.cir').write_text(deck)
 run=subprocess.run([str(NG),'-b','circuit.cir'],cwd=d,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
 (d/'ngspice.log').write_text(run.stdout);assert run.returncode==0,(name,run.stdout[-2000:])
 a=np.loadtxt(d/'trace.tsv',skiprows=1);assert a.shape[1]==19 and np.all(np.isfinite(a)) and np.all(np.diff(a[:,0])>0)
 target=.8 if base=='cold_start' else .008;assert abs(a[-1,0]-target)<1e-10
 raw=(d/'trace.tsv').read_bytes();(d/'trace.tsv.gz').write_bytes(gzip.compress(raw,mtime=0));(d/'trace.tsv').unlink()
 return name,dict(base_case=base,declared_mutation=mutation,base_deck_sha256=digest(p),metrics=metrics(a),
  artifacts={f:digest(d/f) for f in ['circuit.cir','ngspice.log','trace.tsv.gz']})
def main():
 data=json.loads((DATA/'results.json').read_text());frozen=data['source_sha256'];assert all(digest(ROOT/p)==h for p,h in frozen.items())
 assert digest(NG)==data['binary_sha256'];assert len(data['results'])==25 and data['validation']['passed']
 snapshot=HERE/'snapshot';snapshot.mkdir(exist_ok=True)
 for p in [*frozen,'docs/engine-idle-isolation.md','hardware/idle-isolated/README.md','hardware/a5-idle-interface/README.md']:
  dest=snapshot/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,dest)
 audits=[];pulse_comparison=[]
 for result in data['results']:
  c=result['case'];name=c['name'];p=DATA/name/'trace.tsv.gz';a=read(p);t=a[:,0]
  assert a.shape[1]==13 and np.all(np.isfinite(a)) and np.all(np.diff(t)>0)
  stop=.8 if c['cold'] else .0022 if c['pulse_us'] else .008
  start=.0019 if c['pulse_us'] else 0
  assert abs(t[-1]-stop)<1e-10 and start<=t[0]<=start+c['maximum_step_us']*1e-6+1e-10
  late_seconds=.00005 if c['pulse_us'] else .0005
  assert abs(avg(a,8,late_seconds)-result['final_current_a'])<1e-12
  assert abs(avg(a,2,late_seconds)-result['final_gate_v'])<1e-12
  high=float(np.trapezoid((a[:,2]>4).astype(float),t)*1e6)
  assert abs(high-result['observed_gate_high_us'])<1e-8
  assert float(np.max(a[:,8]))==result['maximum_coil_current_a']
  assert result['first_saved_time_s']==float(t[0]) and result['final_time_s']==float(t[-1])
  audits.append(dict(name=name,rows=len(a),first_time_s=float(t[0]),last_time_s=float(t[-1]),minimum_dt_s=float(np.min(np.diff(t))),maximum_coil_peak_time_s=float(t[np.argmax(a[:,8])]),
    artifacts={f:digest(DATA/name/f) for f in ['circuit.cir','ngspice.log','trace.tsv.gz']}))
  if c['pulse_us']:
   old=read(OLD/name/'trace.tsv.gz');mask=(old[:,0]>=.0019)&(old[:,0]<=.0022);old=old[mask]
   old_current=float(np.max(old[:,8]));rel=abs(old_current-result['maximum_coil_current_a'])/max(old_current,result['maximum_coil_current_a'],1e-30)
   old_high=float(np.trapezoid((old[:,2]>4).astype(float),old[:,0])*1e6)
   assert rel<.005 and abs(old_high-high)<.1,(name,rel,old_high,high)
   pulse_comparison.append(dict(name=name,old_complete_trace_sha256=digest(OLD/name/'trace.tsv.gz'),new_saved_window_max_current_relative_difference=rel,gate_width_abs_difference_us=abs(old_high-high)))
 specs=[('baseline_repeat','warm_continuous',''),('return_open_repeat','actuator_return_open',''),('bridge_repeat','return_open_deliberate_bridge',''),('drain_short_repeat','drain_short',''),('optical_block','warm_continuous','optical_block'),('supervisor_block','warm_continuous','supervisor_block'),('extra_main_load','warm_continuous','extra_main_load'),('cold_half_step','cold_start','cold_half_step')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:probes=dict(pool.map(one,specs))
 assert probes['return_open_repeat']['metrics']['final_carrier_return_a']<.05
 assert probes['bridge_repeat']['metrics']['final_carrier_return_a']>1
 assert probes['drain_short_repeat']['metrics']['final_gate_v']<.1 and probes['drain_short_repeat']['metrics']['final_coil_a']>1
 assert probes['optical_block']['metrics']['final_gate_v']<.1 and probes['optical_block']['metrics']['final_coil_a']<.001
 assert probes['supervisor_block']['metrics']['final_gate_v']<.1 and probes['supervisor_block']['metrics']['final_coil_a']<.001
 assert probes['extra_main_load']['metrics']['final_run_source_a']>.004
 assert all(digest(ROOT/p)==h for p,h in frozen.items())
 result=dict(scope=__doc__,reviewed_source_sha256={p:digest(snapshot/p) for p in [*frozen,'docs/engine-idle-isolation.md','hardware/idle-isolated/README.md','hardware/a5-idle-interface/README.md']},
  source_matches_at_end=True,binary_sha256=digest(NG),results_sha256=digest(DATA/'results.json'),input_folder=str(DATA.relative_to(ROOT)),
  raw_trace_audit=audits,pulse_window_comparison=pulse_comparison,probes=probes,
  qualification='Generic conditional electrical sensitivity only; no guarantee of GPIO/RUN levels, exact device timing/temperature, regulator behavior, PCB parasitics, physical or engine acceptance')
 (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v['metrics'] for k,v in probes.items()},indent=2))
if __name__=='__main__':main()
