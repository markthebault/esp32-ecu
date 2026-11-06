#!/usr/bin/env python3
"""Freeze the exact reviewed project scope without changing project files."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);a=p.parse_args()
root=a.project.resolve();out=a.destination.resolve();assert not out.exists();(out/'sources').mkdir(parents=True)
names=['hardware/switch-inputs','hardware/a5-idle-interface','scripts/build_switch_inputs.py','scripts/route_switch_inputs.py','scripts/build_hardware.py','scripts/design.py','scripts/kicad9_carrier_copy.py','tools/run_switch_circuit.py','firmware/include/ecu/switch_acquisition.hpp','firmware/main/switch_service.cpp','firmware/include/ecu/pins.hpp','docs/web-configuration.md','docs/engine-usb-tuning.md','docs/engine-secondary-tables.md','docs/engine-feature-coverage.md','tuning/README.md']
paths=[]
for name in names:
 path=root/name;paths+=list(path.rglob('*'))if path.is_dir()else[path]
rows=[];archive_checks=0
for path in sorted(set(paths)):
 if not path.is_file()or path.name.endswith(('.kicad_prl','.lck')):continue
 rel=path.relative_to(root);data=path.read_bytes();dest=out/'sources'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
 if str(rel).startswith('hardware/a5-idle-interface/'):
  original=subprocess.run(['git','show','HEAD:'+str(rel)],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
  assert original==data,('archived A5 source changed',rel);archive_checks+=1
 rows.append(dict(path=str(rel),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
for row in rows:assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256'],('scope changed during copy',row['path'])
(out/'source-bindings.json').write_text(json.dumps(rows,indent=2)+'\n')
(out/'freeze.json').write_text(json.dumps(dict(files=len(rows),archive_files_byte_equal_to_HEAD=archive_checks,head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),mutated_project_files=False),indent=2)+'\n')
print(json.dumps(dict(frozen_files=len(rows),archive_files_byte_equal_to_HEAD=archive_checks)))
