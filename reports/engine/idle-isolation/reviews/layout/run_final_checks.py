#!/usr/bin/python3
"""Capture an author-declared ready PCB into immutable evidence; native checks only.
Never loads/edits the live PCB in KiCad, and never reroutes/generates it.
Usage: /usr/bin/python3 .../run_final_checks.py EXPECTED_PCB_SHA256
"""
from pathlib import Path
import hashlib,json,shutil,datetime,subprocess,sys
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
expected=sys.argv[1];assert len(expected)==64
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ROOT/'hardware/idle-isolated/isolated.kicad_pcb')==expected
files=[p for p in (ROOT/'hardware/idle-isolated').rglob('*') if p.is_file() and p.suffix!='.kicad_prl']
files += [ROOT/p for p in ['scripts/build_idle_isolated.py','scripts/route_idle_isolated.py','scripts/build_hardware.py','scripts/design.py','scripts/kicad9_carrier_copy.py','firmware/include/ecu/idle_hardware.hpp','firmware/include/ecu/idle_pwm.hpp','.cache/engine/idle-isolation-review/review.md','.cache/engine/idle-isolation-review/architecture_probe.py','.cache/engine/idle-isolation-review/architecture-probe.json','.cache/engine/idle-isolation-review/sources/manifest.json']]
files=sorted(set(files));hashes={str(p.relative_to(ROOT)):sha(p) for p in files}
bundle=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
snap=OUT/'snapshots'/bundle
assert not snap.exists(),snap
for p in files:
 q=snap/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
 assert sha(q)==hashes[str(p.relative_to(ROOT))]
assert hashes=={str(p.relative_to(ROOT)):sha(p) for p in files},'Author inputs changed during capture'
manifest=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_root=str(ROOT),git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),snapshot=str(snap),bundle_sha256=bundle,files=hashes)
(snap/'snapshot-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for p in sorted(snap.rglob('*'),reverse=True):p.chmod(0o555 if p.is_dir() else 0o444)
snap.chmod(0o555)
f=OUT/'final';f.mkdir(exist_ok=True)
assert not (f/'native-working-copy').exists(),'Preserve previous final pass before recapture'
(f/'snapshot-path.txt').write_text(str(snap)+'\n')
proj=snap/'hardware/idle-isolated';work=f/'native-working-copy';shutil.copytree(proj,work)
for p in work.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
work.chmod(0o755)
cmds=[['kicad-cli','sch','erc','--severity-all','--format','json','--exit-code-violations','--output',str(f/'native-working-erc.json'),str(work/'isolated.kicad_sch')],['kicad-cli','pcb','drc','--severity-all','--all-track-errors','--schematic-parity','--format','json','--exit-code-violations','--output',str(f/'native-working-drc.json'),str(work/'isolated.kicad_pcb')],['kicad-cli','sch','export','netlist','--format','kicadxml','--output',str(f/'schematic-netlist.xml'),str(work/'isolated.kicad_sch')]]
logs=[]
for argv in cmds:
 p=subprocess.run(argv,cwd=work,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);logs.append(dict(argv=argv,cwd=str(work),returncode=p.returncode,stdout=p.stdout))
 print(p.stdout,end='');assert p.returncode==0
(f/'native-command-log.json').write_text(json.dumps(logs,indent=2)+'\n')
assert all(sha(p)==sha(work/p.relative_to(proj)) for p in proj.rglob('*') if p.is_file())
assert all(sha(snap/path)==h for path,h in hashes.items())
p=subprocess.run(['/usr/bin/python3',str(OUT/'review_probe_final.py')],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(f/'probe.log').write_text(p.stdout);print(p.stdout,end='');assert p.returncode==0
print(json.dumps(dict(snapshot=str(snap),bundle_sha256=bundle,pcb_sha256=expected),indent=2))
