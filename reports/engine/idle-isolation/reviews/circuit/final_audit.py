"""Bind final full-precision ngspice vectors after review corrections.

This audits data/source fidelity and conditional summaries, not device behavior.
The independently mutated electrical probes retain their original decks.
"""
import gzip,hashlib,importlib.util,io,json,shutil
from pathlib import Path
import numpy as np
H=Path(__file__).resolve().parent;R=H.parents[2]
D=R/'.cache/engine/idle-isolation/circuit-precision'
P=R/'.cache/engine/idle-isolation/circuit-published'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return np.loadtxt(io.BytesIO(gzip.decompress(Path(p).read_bytes())),skiprows=1)
def average(a,col,width):
 m=a[:,0]>a[-1,0]-width;t=a[m,0];return float(np.trapezoid(a[m,col],t)/(t[-1]-t[0]))
def main():
 data=json.loads((D/'results.json').read_text());assert data['validation']['passed'] and len(data['results'])==25
 src=data['source_sha256'];assert all(sha(R/p)==v for p,v in src.items())
 assert sha(R/'.cache/tools/ngspice-package/payload/usr/bin/ngspice')==data['binary_sha256']
 source_list=[*src,'docs/engine-idle-isolation.md','hardware/idle-isolated/README.md','hardware/a5-idle-interface/README.md']
 snapshot=H/'final-snapshot';snapshot.mkdir(exist_ok=False)
 for p in source_list:
  dest=snapshot/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/p,dest)
 rows=[]
 for row in data['results']:
  c=row['case'];name=c['name'];a=read(D/name/'trace.tsv.gz');t=a[:,0];dt=np.diff(t)
  assert a.shape==(row['rows'],13) and np.all(np.isfinite(a)) and np.all(dt>0),name
  target=.8 if c['cold'] else .0022 if c['pulse_us'] else .008
  start=.0019 if c['pulse_us'] else 0
  assert abs(t[-1]-target)<1e-12 and start<=t[0]<=start+c['maximum_step_us']*1e-6+1e-12
  width=.00005 if c['pulse_us'] else .0005
  for col,key in [(8,'final_current_a'),(1,'final_rail_v'),(2,'final_gate_v')]:assert abs(average(a,col,width)-row[key])<1e-12,(name,key)
  assert np.max(a[:,8])==row['maximum_coil_current_a']
  high=float(np.trapezoid((a[:,2]>4).astype(float),t)*1e6)
  assert abs(high-row['observed_gate_high_us'])<1e-8
  assert row['duplicate_exported_times']==0 and row['time_order']=='strict'
  assert row['minimum_positive_exported_step_s']==float(dt.min())
  old_deck=(P/name/'circuit.cir').read_text();new_deck=(D/name/'circuit.cir').read_text()
  assert old_deck.replace('set wr_vecnames\n','set wr_vecnames\nset numdgt=17\n')==new_deck,name
  b=read(P/name/'trace.tsv.gz')
  assert a.shape==b.shape
  max_numeric_delta=float(np.max(np.abs(a-b)))
  assert max_numeric_delta<1e-6,(name,max_numeric_delta)
  old_max=float(np.max(b[:,8]));rel=abs(old_max-row['maximum_coil_current_a'])/max(old_max,row['maximum_coil_current_a'],1e-30)
  rows.append(dict(name=name,rows=len(a),saved_first_s=float(t[0]),saved_last_s=float(t[-1]),strict_time_order=True,
    model_deck_unchanged_except_export_precision=True,prior_maximum_numeric_rounding_delta=max_numeric_delta,peak_current_relative_rounding_delta=rel))
 # Two direct precision-deck reruns supplement the eight independent electrical
 # probes. The underlying model did not change during the export correction.
 spec=importlib.util.spec_from_file_location('independent_probe',H/'probe.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.DATA=D
 final_probes=dict(m.one(x) for x in [('baseline_final_precision','warm_continuous',''),('supervisor_final_precision','warm_continuous','supervisor_block')])
 assert final_probes['baseline_final_precision']['metrics']['final_coil_a']>1.4
 assert final_probes['supervisor_final_precision']['metrics']['final_coil_a']<.001
 assert all(sha(R/p)==sha(snapshot/p) for p in source_list)
 artifacts={str(p.relative_to(D)):sha(p) for p in sorted(D.rglob('*')) if p.is_file()}
 (H/'reviewed-data-sha256.json').write_text(json.dumps(dict(input_directory=str(D.relative_to(R)),sha256=artifacts),indent=2)+'\n')
 result=dict(scope=__doc__,reviewed_sources_sha256={p:sha(snapshot/p) for p in source_list},source_unchanged_at_end=True,
   input_directory=str(D.relative_to(R)),input_results_sha256=sha(D/'results.json'),ngspice_binary_sha256=data['binary_sha256'],
   full_precision_trace_audit=rows,exported_time_duplicates_total=0,final_precision_reruns=final_probes,
   prior_independent_probe_results_sha256=sha(H/'results.json'),all_input_artifacts_sha256_file='reviewed-data-sha256.json',
   qualification='Conditional lumped circuit/source/trace review only. No actual GPIO/RUN, semiconductor timing/temperature, regulator transient, PCB parasitic, valve, engine or physical isolation acceptance.')
 (H/'final-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(cases=len(rows),exported_time_duplicates=0,input_files=len(artifacts),final_source_sha256=src,final_precision_probe_metrics={k:v['metrics'] for k,v in final_probes.items()}),indent=2))
if __name__=='__main__':main()
