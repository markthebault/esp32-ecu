#!/usr/bin/env python3
"""Package reviewed native files, offline UI, matching PDF and inhibited firmware."""
from pathlib import Path
import hashlib,json,zipfile
R=Path(__file__).resolve().parents[1];files={};out=R/'build/esp32-ecu-a3-120-web-manual-case.zip';out.parent.mkdir(exist_ok=True)
a=json.loads((R/'reports/a3/validation-summary.json').read_text());assert a['pcb_outline_mm']==[120,120] and a['copper_layers']==6
assert all(a[k]==0 for k in ['user_soldered_smd_pads','erc_violations','drc_violations','unconnected','schematic_parity_issues'])
d=json.loads((R/'reports/a3/drc.json').read_text());assert not d['violations'] and not d['unconnected_items'] and not d['schematic_parity']
e=json.loads((R/'reports/a3/erc.json').read_text());assert all(not s.get('violations') for s in e['sheets'])
assert json.loads((R/'enclosure/a3/fit-check.json').read_text())['nominal_solid_collisions']==0
assert 'Ran 18 tests' in (R/'reports/web/config-tests.txt').read_text() and '\nOK' in (R/'reports/web/config-tests.txt').read_text()
assert '116 control scenarios passed' in (R/'reports/web/control-tests.txt').read_text()
assert '2 succeeded' in (R/'reports/web/firmware-build.txt').read_text()
contract=R/'hardware/a3-compact/net_contract.json';c=json.loads(contract.read_text());c['status']='routed_six_layer_bench_prototype_not_vehicle_qualified';contract.write_text(json.dumps(c,indent=2))
for folder in ['hardware/a3-compact','enclosure/a3','manufacturing/a3','reports/a3','reports/web','firmware/main','firmware/include','firmware/tests','config','web','tools','output/pdf']:
 for p in (R/folder).rglob('*'):
  if p.is_file() and '__pycache__' not in str(p) and '-backups' not in str(p) and p.suffix not in ['.kicad_prl','.lck','.FCBak','.blend1','.blend']:files[str(p.relative_to(R))]=p.read_bytes()
for name in ['hardware/KICAD-LIBRARY-NOTICE.md','docs/history.md','README.md','docs/compact.md','docs/web-configuration.md','docs/a3-preview.html','firmware/platformio.ini','firmware/partitions.csv','firmware/sdkconfig.defaults','firmware/CMakeLists.txt','scripts/build_bom.py','scripts/embed_web.py','scripts/build_shared_guides.py','scripts/build_instruction_pdf.py','scripts/build_connection_map.py','scripts/build_a3_enclosure.py','scripts/check_a3_enclosure.py','scripts/render_a3_enclosure.py','scripts/render_a3_mounting_plan.py','scripts/build_a3_connector_models.py','scripts/verify_a3.py','scripts/kicad.sh','scripts/test_firmware.sh','scripts/package_a3.py']:
 files[name]=(R/name).read_bytes()
for env in ['compact_a3_web','compact_a3']:
 build=R/'firmware/.pio/build'/env
 for name in ['firmware.bin','bootloader.bin','partitions.bin']:files[f'prebuilt/{env}/{name}']=(build/name).read_bytes()
 args=json.loads((build/'flasher_args.json').read_text());args['flash_files']={'0x0':'bootloader.bin','0x8000':'partitions.bin','0x10000':'firmware.bin'}
 for key,filename in [('bootloader','bootloader.bin'),('app','firmware.bin'),('partition-table','partitions.bin')]:args[key]['file']=filename
 files[f'prebuilt/{env}/flasher_args.json']=json.dumps(args,indent=2).encode()
files['START-HERE.txt']=b'''A3-120 / ESP32-S3 bench prototype
Read the PDF under output/pdf, then docs/web-configuration.md.
Open hardware/a3-compact/esp32-ecu.kicad_pro in KiCad 10.
The PCB is 120 x 120 mm with six copper layers. All carrier joints are through-hole; the S3 DevKit and buck module are purchased assembled.
The printable case is under enclosure/a3. Fit the specified gasket, glands, shield lining, dielectric covers and hardware. No physical splash or fit test is claimed.
Web firmware: compact_a3_web. Radio-off monitor: compact_a3. Both keep ARM and all actuator commands OFF. This package does not operate an engine or replace an OEM ECU.
Use PlatformIO to build/upload. Remove the DevKit from carrier power before powering USB. Open J3 and disconnect actuator harnesses before bench service. A new WPA2 AP password is printed on UART each boot; connect to ECU-Service-XXXX at http://192.168.4.1.
The complete offline UI is web/index.html. Desktop preview: python3 tools/web_server.py. Its measurements are simulated and labelled. Requires a C/C++ compiler and the pinned PlatformIO ESP-IDF cJSON source installed by building firmware.
Prebuilt flash images and their actual flash settings are in prebuilt/. Program on a dry bench with no actuators connected. Keep exported profiles before any partition/firmware recovery. No automatic NVS erase is performed by application code.
Check reports/a3 and reports/web. CAD and software checks do not establish vehicle, thermal, surge, EMC or emissions qualification.
'''
files['SHA256SUMS.txt']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 for name,data in sorted(files.items()):z.writestr(name,data)
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 for name,data in files.items():assert z.read(name)==data
print(f'{out}\n{len(files)} files; ZIP CRC, content and SHA256 manifest verified; {out.stat().st_size:,} bytes')
