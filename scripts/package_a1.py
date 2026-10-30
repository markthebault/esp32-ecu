#!/usr/bin/env python3
"""Package the checked A1 carrier, source firmware and printable enclosure."""
import hashlib,json,zipfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'build';O.mkdir(exist_ok=True)
s=json.loads((R/'reports/a1/validation-summary.json').read_text());assert s['drc_violations']==s['unconnected']==s['schematic_parity_issues']==s['erc_violations']==0
assert '[SUCCESS]' in (R/'reports/a1/firmware-build.txt').read_text()
c=R/'hardware/a1-hand-solder/net_contract.json';d=json.loads(c.read_text());d['status']='routed_bench_prototype_not_vehicle_qualified';c.write_text(json.dumps(d,indent=2))
files={}
for folder in ['hardware/a1-hand-solder','enclosure','reports/a1']:
 for f in (R/folder).rglob('*'):
  if f.is_file() and f.suffix not in ['.lck','.kicad_prl','.FCStd1','.blend1'] and '-backups' not in str(f):files[str(f.relative_to(R))]=f.read_bytes()
for folder in ['firmware/main','firmware/include','firmware/tests','scripts']:
 for f in (R/folder).rglob('*'):
  if f.is_file() and '__pycache__' not in str(f):files[str(f.relative_to(R))]=f.read_bytes()
for name in ['firmware/platformio.ini','firmware/CMakeLists.txt','firmware/sdkconfig.defaults','docs/hand-solder.md']:
 files[name]=(R/name).read_bytes()
for name in ['firmware.bin','bootloader.bin','partitions.bin']:
 files['monitor-firmware/'+name]=(R/'firmware/.pio/build/hand_solder_a1'/name).read_bytes()
files['README.txt']=b'A1 home assembly carrier and printable enclosure. Start with docs/hand-solder.md. KiCad project: hardware/a1-hand-solder/esp32-ecu.kicad_pro. Firmware is an inhibited bench monitor, not a complete engine ECU. Physical fit and vehicle qualification are untested. Generic passive component BOM lines still require exact component selection and review. Do not manufacture from a clean DRC report alone. See reports/a1 and enclosure/validation.json for the checks actually performed.\n'
files['SHA256SUMS.txt']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
p=O/'esp32-ecu-a1-home-assembly.zip'
with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
 for name,data in sorted(files.items()):z.writestr(name,data)
with zipfile.ZipFile(p) as z:
 assert z.testzip() is None
 for name,data in files.items():assert z.read(name)==data
print(str(p),len(files),'files; ZIP integrity and content hashes verified')
