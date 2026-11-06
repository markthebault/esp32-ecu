#!/usr/bin/env python3
"""Freeze current application interoperability evidence without vendor binaries."""
import argparse,gzip,hashlib,io,json,shutil,subprocess,tarfile,zipfile
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'.cache/engine/tuning-apps-011-001'
REVIEW=ROOT/'.cache/engine/tuning-app-review-011-001'

def sha(body):return hashlib.sha256(body).hexdigest()
def read(path):return json.loads(path.read_text())
def safe(name):
 path=PurePosixPath(name)
 assert not path.is_absolute() and '..' not in path.parts
 return path.as_posix()

def verify(output,repo=None):
 m=read(output/'artifact-manifest.json');expected={x['path']:x for x in m['files']}
 assert len(expected)==len(m['files'])
 assert not any(p.is_symlink() for p in output.rglob('*'))
 assert {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}==set(expected)|{'artifact-manifest.json'}
 for name,row in expected.items():
  body=(output/safe(name)).read_bytes();assert len(body)==row['bytes'] and sha(body)==row['sha256'],name
 count=0
 for archive in m['archives']:
  rows={x['path']:x for x in archive['payloads']};assert len(rows)==len(archive['payloads'])
  with tarfile.open(output/safe(archive['path']),'r:gz') as stream:
   members=stream.getmembers();assert len(members)==len(rows) and {p.name for p in members}==set(rows)
   for member in members:
    assert member.isfile() and safe(member.name)==member.name
    body=stream.extractfile(member).read();row=rows[member.name]
    assert len(body)==row['bytes'] and sha(body)==row['sha256'],member.name
  count+=len(rows)
 s=read(output/'summary.json');assert s['offline_accepted'] and not s['online_accepted'] and not s['physical_operation_verified'] and not s['goal_complete']
 if repo:
  for name,digest in s['source_hashes'].items():assert sha((repo/safe(name)).read_bytes())==digest,name
 return dict(passed=True,archives=len(m['archives']),payloads=count,live_sources_checked=bool(repo))

def package(output):
 assessment=read(REVIEW/'assessment.json')
 assert assessment['accepted_for_current_offline_native_and_raw_log_scope'] and not assessment['open_findings']
 direct_review=ROOT/'.cache/engine/tuning-app-direct-review-011-001'
 direct_assessment=read(direct_review/'assessment.json')
 assert direct_assessment['accepted'] and not direct_assessment['open_findings']
 roundtrip=read(WORK/'latest-definition-roundtrip.json');wire=read(WORK/'own011-wire-analysis.json')
 assert roundtrip['passed'] and roundtrip['no_unit_warnings'] and roundtrip['page_bytes']==12288
 assert wire['capture_complete'] and not wire['invalid_frames'] and wire['complete_transactions']==1685
 assert wire['signatures']==['ESP32ECU DEV 011 INHIBITED']
 assert not any(wire['command_counts'].get(name,0) for name in ('p','r','M','b','d'))
 assert read(WORK/'browser-final/ui-tests.json')['passed']
 for name in ('ts-offline','ts-offline-fixed','ts-online','ts-final-definition','mlv','mlv-direct-sil'):
  assert read(WORK/name/'closed.json')['all_owned_processes_terminal']
 assert sha((ROOT/'tuning/esp32-ecu-boost.ini').read_bytes())==roundtrip['ini_sha256']
 output.mkdir(parents=True,exist_ok=False);archives=[]
 def archive(filename,items):
  rows=[];seen=set()
  with (output/filename).open('xb') as raw,gzip.GzipFile(fileobj=raw,filename='',mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as stream:
   for name,path in sorted(items):
    name=safe(name);assert name not in seen and path.is_file() and not path.is_symlink();seen.add(name)
    body=path.read_bytes();info=tarfile.TarInfo(name);info.size=len(body);info.mode=0o644;info.mtime=0
    stream.addfile(info,io.BytesIO(body));rows.append(dict(path=name,bytes=len(body),sha256=sha(body)))
  archives.append(dict(path=filename,payloads=rows))
 names=['.gitattributes','tuning/README.md','tuning/esp32-ecu-boost.ini','tuning/protocol-layout.json','tuning/editor-limits.json','tuning/examples/tunerstudio-boost-roundtrip.msq','tuning/vendor-integration-request.md','tuning/vendor-integration-email.txt','docs/engine-usb-tuning.md','docs/engine-tuning-application.md','docs/engine-feature-coverage.md','docs/engine-observability.md','docs/engine-boost-development.md','scripts/generate_tunerstudio_ini.py','tools/engine_msq.py','tools/engine_protocol.py','tools/engine_runtime.py','tools/engine_sil.py','tools/tuning_runtime.py','tools/tuning_server.py','tools/analyze_tuning_wire.py','tools/test_tuning.py','tools/test_tuning_transport.py','tools/test_tuning_ui.py','tools/package_tuning_applications.py','web/index.html','web/boost_control_logic.js','web/boost_control.js']
 source_hashes={name:sha((ROOT/name).read_bytes()) for name in names}
 archive('sources.tar.gz',[(name,ROOT/name) for name in names])
 items=[];whitelist=read(REVIEW/'whitelist.json')
 for row in whitelist['files']:
  path=REVIEW/safe(row['path']);body=path.read_bytes();assert len(body)==row['bytes'] and sha(body)==row['sha256'],path
  assert path.suffix.lower() not in ('.jar','.pdf','.so','.class','.exe')
  items.append((row['path'],path))
 if not any(row['path']=='whitelist.json' for row in whitelist['files']):items.append(('whitelist.json',REVIEW/'whitelist.json'))
 archive('independent-review.tar.gz',items)
 items=[];whitelist=read(direct_review/'whitelist.json')
 for row in whitelist['files']:
  path=direct_review/safe(row['path']);body=path.read_bytes();assert len(body)==row['bytes'] and sha(body)==row['sha256'],path
  assert path.suffix.lower() not in ('.jar','.pdf','.so','.class','.exe')
  items.append((row['path'],path))
 if not any(row['path']=='whitelist.json' for row in whitelist['files']):items.append(('whitelist.json',direct_review/'whitelist.json'))
 archive('direct-sil-review.tar.gz',items)
 items=[]
 for path in sorted(WORK.iterdir()):
  if path.is_file() and path.suffix in ('.py','.json','.bin','.msq','.msl'):items.append((path.name,path))
 for name in ('ts-offline','ts-offline-fixed','ts-online','ts-final-definition','mlv','mlv-direct-sil'):
  folder=WORK/name
  for path in sorted(folder.iterdir()):
   if path.is_file() and path.suffix in ('.json','.jsonl','.png','.log'):items.append((name+'/'+path.name,path))
  debug=folder/'user/TunerStudioProjects/TunerStudioAppDebug.txt'
  if debug.exists():items.append((name+'/TunerStudioAppDebug.txt',debug))
  project=folder/'ESP32ECU-BOOST-011'
  for relative in ('projectCfg/project.properties','projectCfg/mainController.ini','CurrentTune.msq'):
   path=project/relative
   if path.exists():items.append((name+'/project/'+relative,path))
 for folder_name in ('browser-final','browser'):
  for path in sorted((WORK/folder_name).iterdir()):
   if path.is_file():items.append((folder_name+'/'+path.name,path))
 archive('application-validation.tar.gz',items)
 # A reviewable local handoff, deliberately never sent by this packager.
 with zipfile.ZipFile(output/'vendor-support.zip','w',compression=zipfile.ZIP_DEFLATED) as stream:
  for name,path in [('esp32-ecu-boost.ini',ROOT/'tuning/esp32-ecu-boost.ini'),('request.md',ROOT/'tuning/vendor-integration-request.md'),('wire.log',WORK/'ts-online/wire.log'),('wire-analysis.json',WORK/'own011-wire-analysis.json'),('application-roundtrip.json',WORK/'latest-definition-roundtrip.json'),('application-saved.msq',WORK/'application-latest-definition011.msq'),('application-debug.txt',WORK/'ts-online/user/TunerStudioProjects/TunerStudioAppDebug.txt')]:stream.writestr(name,path.read_bytes())
 summary=dict(offline_accepted=True,online_accepted=False,msl008_engine_app_accepted=True,direct_sil_202_app_tested=True,physical_operation_verified=False,goal_complete=False,
  base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_hashes=source_hashes,
  latest_roundtrip=roundtrip,edited_roundtrip=read(WORK/'edited-app-roundtrip.json'),wire={k:v for k,v in wire.items() if k!='transactions'},
  chrome=read(WORK/'browser-final/ui-tests.json'),independent_assessment=assessment,direct_sil_assessment=direct_assessment,
  vendor_message_sent=False,qualification='Real unmodified offline application and host/native format evidence only. Own011 online rejected; MLV calculated-AFR caveat, target USB throughput/physical operation and wider ECU goal remain open.')
 (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');shutil.copyfile(Path(__file__),output/'verify.py')
 for name in ('boost-protection-ready.png','boost-duty-plot.png'):
  shutil.copyfile(WORK/'mlv'/name,output/name)
 shutil.copyfile(WORK/'ts-final-definition/latest-definition-saved.png',output/'tunerstudio-offline.png')
 shutil.copyfile(WORK/'mlv-direct-sil/direct-sil-boost-reason.png',output/'direct-sil-mlv.png')
 (output/'README.md').write_text('''# Current own011 / MSL008 application checkpoint

Actual TunerStudio MS Lite3.3.01 loads/edits/saves own011 offline. Three intended table edits survive, and a fresh latest-definition reload/save reconstructs all12288 page bytes with an explicit known origin7. The202 saved constants omit the read-only origin. Ten Chrome checks include importing that real application file with CAS and preserving every calibration field.

The original Python MSQ gave percent units to three boost option fields. The actual application's warnings are retained alongside the corrected unitless export. Current general editor bounds now cover33 scalars, six curves and three timing fields, including four-cylinder support and5..45° cam window; whole-tune validation still handles coupled rules.

**Online remains unsupported:** the fresh own011 trace has1685 complete CRC-valid discovery exchanges and337 exact rejection warnings, with no calibration/runtime/read/write/burn operation. No other controller identity was used. The genuine production Speeduino positive control remains in the separate historical packet. The vendor request/ZIP are prepared locally and unsent.

MegaLogViewer HD Lite4.6.14 plots current245-column MSL008 BoostDuty/MAP and protection fields from120 synthetic controller observations. A separate trial opens300 rows of202-column direct-SIL008 and plots BoostReason6..8, matching the raw file. This is viewer file/field evidence from the existing unvalidated regression, not a new engine benchmark. Its calculated AFR* summary also reports a14,700,000 maximum when ten raw Lambda fields are unavailable. Raw JSON/MSL validity remains authoritative; huge-counter graphical arithmetic is unverified.

![Actual MSL008 boost/protection plots](boost-protection-ready.png)

[Current guide](../../../docs/engine-tuning-application.md) · [USB/layout and power restrictions](../../../docs/engine-usb-tuning.md) · [Summary](summary.json)

Archives preserve sources, actual files/logs/screenshots/actions, initial warning evidence and reviewer-selected probes. Vendor binaries, definition PDFs and personal registrations are excluded. All owned application/Xvfb processes are terminal. There was no physical serial connection, flashing or engine operation.

Verify immutable files/payloads:

```sh
python3 reports/engine/tuning-apps-011/verify.py --verify-only --output reports/engine/tuning-apps-011
```

Add `--repo .` only when current project source bytes still match this checkpoint. This is an integrity/scope check; it does not relaunch the proprietary applications or certify controller physics. Reproduction source/action scripts are archived with the installed versions' hashes. The full ECU goal remains active.
''')
 files=[dict(path=path.relative_to(output).as_posix(),bytes=path.stat().st_size,sha256=sha(path.read_bytes())) for path in sorted(output.rglob('*')) if path.is_file()]
 (output/'artifact-manifest.json').write_text(json.dumps(dict(files=files,archives=archives),indent=2)+'\n')
 print(json.dumps(verify(output,ROOT)))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify-only',action='store_true');p.add_argument('--repo',type=Path);a=p.parse_args()
 if a.verify_only:print(json.dumps(verify(a.output.resolve(),a.repo.resolve() if a.repo else None)))
 else:package(a.output.resolve())
