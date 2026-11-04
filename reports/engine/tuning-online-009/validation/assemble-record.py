from pathlib import Path
import gzip,hashlib,json,shutil,subprocess,zipfile

ROOT=Path('/home/mark/persospace/esp32-ecu')
CACHE=ROOT/'.cache/engine/tuning-online-009'
REVIEW=ROOT/'.cache/engine/tuning-online-protocol-review'
OUT=ROOT/'reports/engine/tuning-online-009'
sha=lambda body:hashlib.sha256(body).hexdigest()

def write(name,body):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb')as stream:stream.write(body)

def copy(source,name,compress=False):
 body=Path(source).read_bytes()
 write(name,gzip.compress(body,mtime=0)if compress else body)

def doc(name,value):write(name,(json.dumps(value,indent=2)+'\n').encode())

sources=set(str(p.relative_to(ROOT))for p in(ROOT/'firmware/include/ecu').glob('*.hpp'))
sources.update('''scripts/build_speeduino_serial.py
scripts/build_speeduino_sim.py
tools/speeduino_serial_sim.cpp
tools/speeduino_serial_runtime.py
tools/test_speeduino_serial.py
tools/analyze_tuning_wire.py
tools/test_tuning_wire_analysis.py
tools/verify_tuning_online_evidence.py
tools/speeduino_sim.cpp
tools/speeduino_sim_hal.cpp
tools/speeduino_sim_native.hpp
tools/tuning_bridge.cpp
tools/tuning_runtime.py
tools/tuning_server.py
tools/engine_runtime.py
tools/engine_msq.py
tools/engine_protocol.py
firmware/main/engine_service.cpp
firmware/main/engine_tuning.cpp
firmware/tests/tuning_test.cpp
tuning/esp32-ecu-secondary.ini
tuning/protocol-layout.json
tuning/README.md
tuning/vendor-integration-request.md
tuning/vendor-integration-email.txt
docs/engine-tuning-application.md
docs/engine-development.md
docs/engine-feature-coverage.md
docs/engine-observability.md
docs/engine-usb-tuning.md'''.splitlines())
source_index={}
for name in sorted(sources):
 body=(ROOT/name).read_bytes();snapshot='sources/'+name;write(snapshot,body)
 source_index[name]=dict(snapshot=snapshot,sha256=sha(body))

for label,original,project in [('own','own009','ESP32ECU-ONLINE-009'),('reference','reference-public-003','SPEEDUINO-PRODUCTION')]:
 base=CACHE/original
 for name in('session.json','application.log','screen.png'):
  copy(base/name,label+'/'+name)
 for name in('wire.log','stream-analysis.json'):
  copy(base/name,label+'/'+name+'.gz',True)
 copy(base/'user/TunerStudioProjects/TunerStudioAppDebug.txt',label+'/application-debug.log.gz',True)
 copy(base/project/'projectCfg/mainController.ini',label+'/mainController.ini')
 copy(base/project/'projectCfg/project.properties',label+'/project.properties')
 if label=='reference':
  for name in('native-build-manifest.json','reference-app-edited.msq','ve-edited-burned.png'):
   copy(base/name,label+'/'+name)
  copy(base/'native/closure.json',label+'/closure.json')
  copy(base/'native/native-events.log',label+'/native-events.log.gz',True)
  copy(base/'native/native-stderr.log',label+'/native-stderr.log')

for revision in range(1,6):
 base=REVIEW/('revision%03d'%revision)
 for p in sorted(base.iterdir()):
  if p.is_file()and p.suffix in('.json','.py','.cpp','.log','.stdout','.stderr','.bin'):
   copy(p,'reviews/'+base.name+'/'+p.name)
copy(REVIEW/'reference-control-baseline.json','reviews/reference-control-baseline.json')
copy(REVIEW/'revision001/own-source/docs/engine-usb-tuning.md','reviews/revision001/historical-engine-usb-tuning.md')

upstream={}
for name in('LICENSE','reference/speeduino.ini','speeduino/comms.cpp','speeduino/comms.h','speeduino/comms_legacy.cpp','speeduino/speeduino.ino','lib/ArduinoFake/FakeMega.cpp'):
 body=(ROOT.parent/'speeduino'/name).read_bytes();snapshot='upstream/'+name;write(snapshot,body)
 upstream[name]=dict(snapshot=snapshot,sha256=sha(body))

for source,name in [('formal-build-003.log','serial-build.log'),('python-full-final.log','python-full.log'),('serial-and-analysis-tests-003.log','serial-capture-tests.log'),('start_own.py','launch-own-record.py'),('start_reference_public.py','launch-reference-record.py'),('assemble_packet.py','assemble-record.py')]:
 copy(CACHE/source,'validation/'+name)
copy(REVIEW/'revision005/noninterference-final.json','validation/numerical-reference-unchanged.json')
copy(ROOT/'.cache/engine/speeduino-sim/build-manifest.json','validation/numerical32-build-manifest.json')
copy(ROOT/'.cache/engine/speeduino-sim16/build-manifest.json','validation/numerical16-build-manifest.json')

summary=dict(schema=1,scope='own009_discovery_and_production_reference_serial',date_utc='2026-11-04',baseline_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),checks_passed=True,own_online_accepted=False,physical_qualification=False,full_speeduino_parity=False,vendor_request_sent=False,
 application=dict(name='Unmodified TunerStudio MS Lite',version='3.3.01',jar_sha256='3ebafb867fef3722816e768879501845904f81bc5e13249c77d170e9adf61cf8'),
 own=dict(identity='ESP32ECU DEV 009 INHIBITED',complete_exchanges=1640,unsupported_warnings=328,page_reads=0,runtime_reads=0,writes=0,burns=0),
 reference=dict(identity='speeduino 202504-dev',speeduino_commit='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20',unit_test=False,complete_exchanges=10838,page_reads=22,runtime_reads=10790,writes=1,burns=1,edited_page=2,edited_offset=240,before=85,after=86,page_crc32='be04ef33',saved_msq_sha256=sha((CACHE/'reference-public-003/reference-app-edited.msq').read_bytes())),
 tests=dict(python=221,new_serial_capture=16,own_protocol_maximum_frame_splits=268,scope='Implementation tests before publication; archived capture/native replay is a separate check'),
 independent_implementation_review='reviews/revision005/review.json',independent_publication_review='reviews/publication-review.json',sources=source_index,upstream_sources=upstream,
 limits=['Stopped engine and synthetic static reference ADC; no running-plant or CPU timing claim','No physical ESP32 USB/GPIO, engine, flash/power-loss or vehicle qualification','Reference fake EEPROM is process-local; no restart-persistence proof','Reference parser unchecked length path is not qualified by queue bounds','Closure stats are last requested sample; full wire/native logs establish final byte counts','Own reconnect refresh/stale-client behavior still needs actual application validation','Vendor request is a local unsent draft; supported own-identity online integration remains open'])
doc('summary.json',summary)
doc('vendor/source-hashes.json',dict(baseline_commit=summary['baseline_commit'],sources=source_index,upstream=upstream))

members={
 'README.md':'vendor/README.md',
 'request.txt':'sources/tuning/vendor-integration-email.txt',
 'source-hashes.json':'vendor/source-hashes.json',
 'own/mainController.ini':'own/mainController.ini',
 'own/wire.log.gz':'own/wire.log.gz',
 'own/application-debug.log.gz':'own/application-debug.log.gz',
 'own/screen.png':'own/screen.png',
 'own/session.json':'own/session.json',
 'reference/mainController.ini':'reference/mainController.ini',
 'reference/wire.log.gz':'reference/wire.log.gz',
 'reference/application-debug.log.gz':'reference/application-debug.log.gz',
 'reference/ve-edited-burned.png':'reference/ve-edited-burned.png',
 'reference/reference-app-edited.msq':'reference/reference-app-edited.msq',
 'reference/session.json':'reference/session.json',
 'reference/native-build-manifest.json':'reference/native-build-manifest.json',
 'reference/closure.json':'reference/closure.json',
 'reference/LICENSE':'upstream/LICENSE',
 'reference/independent-write-burn-review.json':'reviews/revision005/public-application-write-burn-review.json',
}
checksums=''.join(sha((OUT/source).read_bytes())+'  '+name+'\n'for name,source in sorted(members.items()))
write('vendor/SHA256SUMS',checksums.encode());members['SHA256SUMS']='vendor/SHA256SUMS'
with zipfile.ZipFile(OUT/'vendor-support.zip','x',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as archive:
 for name,source in sorted(members.items()):
  info=zipfile.ZipInfo(name,(2026,11,4,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
  archive.writestr(info,(OUT/source).read_bytes())
doc('vendor/attachment-manifest.json',dict(files={name:dict(packet_source=source,sha256=sha((OUT/source).read_bytes()))for name,source in sorted(members.items())}))

manifest=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file()and p.name!='artifact-manifest.json':
  body=p.read_bytes();manifest.append(dict(path=str(p.relative_to(OUT)),bytes=len(body),sha256=sha(body)))
doc('artifact-manifest.json',dict(schema=1,artifacts=manifest))
print('Assembled',len(manifest),'artifacts;',len(source_index),'sources;',sum(p.stat().st_size for p in OUT.rglob('*')if p.is_file()),'bytes. Publication review pending.')
