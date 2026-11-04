#!/usr/bin/env python3
"""Package the checked A2 through-hole PCB and shield-ready printed enclosure."""
from pathlib import Path
import hashlib,json,zipfile
R=Path(__file__).resolve().parents[1];O=R/'build';O.mkdir(exist_ok=True)
s=json.loads((R/'reports/a2/validation-summary.json').read_text());assert all(s[k]==0 for k in ['user_soldered_smd_pads','erc_violations','drc_violations','unconnected','schematic_parity_issues'])
fit=json.loads((R/'enclosure/a2/fit-check.json').read_text());assert fit['revision']=='A2-R2' and fit['nominal_solid_collisions']==0 and fit['blind_mount_floor_check']=='pass' and fit['continuous_gasket_ring']
assert '[SUCCESS]' in (R/'reports/a2/firmware-build.txt').read_text();assert '116 control scenarios passed' in (R/'reports/a2/firmware-tests.txt').read_text()
c=R/'hardware/a2-through-hole/net_contract.json';data=json.loads(c.read_text());data['status']='routed_through_hole_bench_prototype_not_vehicle_qualified';c.write_text(json.dumps(data,indent=2))
files={}
for folder in ['hardware/a2-through-hole','enclosure/a2','reports/a2','firmware/main','firmware/include','firmware/tests']:
 for p in (R/folder).rglob('*'):
  if p.is_file() and '__pycache__' not in str(p) and '-backups' not in str(p) and p.suffix not in ['.kicad_prl','.lck','.blend1','.FCStd1','.FCBak']:files[str(p.relative_to(R))]=p.read_bytes()
for name in ['scripts/build_through_hole.py','scripts/a2-seed.json','scripts/build_hardware.py','scripts/design.py','scripts/route_board.py','scripts/finish_routes.py','scripts/finish_a2_routes.py','scripts/route_a2_sensitive.py','scripts/remove_a2_dip_sockets.py','scripts/add_a2_models.py','scripts/add_a2_shield.py','scripts/build_a2_module_envelopes.py','scripts/build_a2_enclosure.py','scripts/check_a2_enclosure.py','scripts/render_a2_enclosure.py','scripts/render_a2_mounting_plan.py','scripts/verify_a2.py','scripts/kicad.sh','scripts/test_firmware.sh','scripts/package_a2.py','docs/through-hole.md','docs/a2-preview.html','firmware/platformio.ini','firmware/CMakeLists.txt','firmware/sdkconfig.defaults','enclosure/base.step','enclosure/lid.step']:
 files[name]=(R/name).read_bytes()
# Baseline footprint datums used by the A2 generator, not an alternate board design.
for name in ['ESP32_S3_DevKitC_1_socket','Pololu_D36V6F5_vertical']:
 key='hardware/a1-hand-solder/lib/ecu.pretty/'+name+'.kicad_mod';files[key]=(R/key).read_bytes()
for name in ['firmware.bin','bootloader.bin','partitions.bin']:files['monitor-firmware/'+name]=(R/'firmware/.pio/build/through_hole_a2'/name).read_bytes()
files['README.txt']=b'A2 THROUGH-HOLE CARRIER. Open hardware/a2-through-hole/esp32-ecu.kicad_pro and read docs/through-hole.md. All carrier component solder pads are through hole. Small parts on purchased ESP32-S3/Pololu modules are factory soldered. Only A2 is the current board in this package; the two A1 module footprint files and base enclosure STEP parts are generator inputs. Firmware is an inhibited bench monitor, not a complete engine controller. Enclosure A2-R2 adds PCB insert mounts and a gasketed splash-resistant design. Read enclosure/a2/README.md; glands, gasket and inserts must be fitted. No physical splash test or ingress rating. EMI design measures, not measured immunity. Physical fit, thermal, transient and vehicle qualification remain untested. Generic passive BOM entries need exact component selection and review before fabrication. Current CAD/software checks are under reports/a2; printed mesh and nominal fit checks are under enclosure/a2.\n'
files['SHA256SUMS.txt']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
out=O/'esp32-ecu-a2-r2-splash-enclosure.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for name,data in sorted(files.items()):z.writestr(name,data)
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 for name,data in files.items():assert z.read(name)==data
(O/'esp32-ecu-a2-through-hole.zip').write_bytes(out.read_bytes())
print(out,len(files),'files, ZIP and SHA256 manifest verified')
