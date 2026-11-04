#!/usr/bin/env python3
"""Verify this packet and replay the accepted frozen prototype source.

uv run --with numpy python run_review.py --ngspice /path/to/ngspice --output NEW_DIRECTORY_OUTSIDE_THIS_PACKET
All generated replay files go into the new output directory. Never flashes,
routes, changes live CAD, or treats models/native checks as qualification.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
base=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify-only',action='store_true');p.add_argument('--ngspice',type=Path);p.add_argument('--output',type=Path);p.add_argument('--check-live-root',type=Path);a=p.parse_args()
manifest=json.loads((base/'artifact-manifest.json').read_text())
for r in manifest['files']:
 path=base/r['path'];data=path.read_bytes();assert len(data)==r['bytes']and hashlib.sha256(data).hexdigest()==r['sha256'],r['path']
source=base/'reviewed-revision/sources';bindings=json.loads((base/'reviewed-revision/source-bindings.json').read_text())
for r in bindings:
 assert hashlib.sha256((source/r['path']).read_bytes()).hexdigest()==r['sha256'],r['path']
 if a.check_live_root:assert hashlib.sha256((a.check_live_root/r['path']).read_bytes()).hexdigest()==r['sha256'],('live scope changed',r['path'])
if a.verify_only:
 print(json.dumps(dict(passed=True,artifacts=len(manifest['files']),frozen_sources=len(bindings),physical_qualification=False)));sys.exit()
assert a.ngspice and a.output,'Provide --ngspice and --output for a replay'
out=a.output.resolve();assert out!=base and base not in out.parents,'Replay output must be outside the immutable packet';out.mkdir(parents=True,exist_ok=False)
native=out/'native';native.mkdir();board=source/'hardware/switch-inputs/switches.kicad_pcb';sch=source/'hardware/switch-inputs/switches.kicad_sch'
def run(name,command):
 result=subprocess.run([str(x)for x in command],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
 (out/(name+'.log')).write_text(result.stdout);assert result.returncode==0,(name,result.stdout[-1000:])
run('netlist',['kicad-cli','sch','export','netlist',sch,'--format','kicadxml','--output',native/'netlist.xml'])
run('erc',['kicad-cli','sch','erc',sch,'--format','json','--severity-all','--output',native/'erc.json'])
run('drc',['kicad-cli','pcb','drc',board,'--format','json','--severity-all','--schematic-parity','--output',native/'drc.json'])
erc=json.loads((native/'erc.json').read_text());assert all(not sheet['violations']for sheet in erc['sheets']),erc
drc=json.loads((native/'drc.json').read_text());assert all(not drc[k]for k in ('violations','unconnected_items','schematic_parity')),drc
run('cad',['/usr/bin/python3',base/'cad_probe.py',source,native])
run('arithmetic',[sys.executable,base/'electrical_probe.py','--report-dir',out/'arithmetic'])
run('independent-spice',[sys.executable,base/'independent_spice_probe.py','--ngspice',a.ngspice,'--report-dir',out/'independent-spice'])
run('model',[sys.executable,source/'tools/run_switch_circuit.py','--ngspice',a.ngspice,'--report-dir',out/'model-replay'])
run('raw-model',[sys.executable,base/'verify_model_results.py',out/'model-replay','--frozen-root',source,'--output',out/'raw-model-verification.json'])
for r in bindings:assert hashlib.sha256((source/r['path']).read_bytes()).hexdigest()==r['sha256'],('replay modified frozen source',r['path'])
summary=dict(passed=True,artifacts_verified=len(manifest['files']),frozen_sources=len(bindings),cad=json.loads((native/'cad-probe.json').read_text()),raw_model=json.loads((out/'raw-model-verification.json').read_text()),physical_qualification=False)
(out/'replay-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
