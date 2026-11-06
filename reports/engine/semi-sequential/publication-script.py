from pathlib import Path
import datetime,gzip,hashlib,json,shutil,subprocess
R=Path('/home/mark/persospace/esp32-ecu');C=R/'.cache/engine/semi';O=C/'publication'
assert not O.exists(),'Use a new publication path'
O.mkdir()
sha=lambda b:hashlib.sha256(b).hexdigest()
def copy(src,dst):
 src=Path(src);dst=O/dst;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
def trace(src,dst):
 dst=O/dst;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(gzip.compress(Path(src).read_bytes(),mtime=0))
for p in (C/'matrix-current').glob('*.json'):
 if p.name=='summary.json':copy(p,'matrix/summary.json')
 else:trace(p,'matrix/'+p.name+'.gz')
copy(C/'matrix-initial/summary.json','initial-audit/summary.json')
for label,case in [('portable','load_step'),('portable','trigger_dropout'),('portable','stall_restart'),('target','load_step'),('target','trigger_dropout'),('target','stall_restart')]:
 trace(C/f'matrix-initial/{label}-{case}-250.json',f'initial-audit/{label}-{case}-250.json.gz')
copy(C/'legacy-regression.json','legacy/summary.json')
for p in C.glob('legacy-*.json'):trace(p,'legacy/'+p.name+'.gz')
logs=['native-regression.log','all-python-publish-final.log','semi-tests-final.log','target-builds-final.log','reference-build32.log','reference-build16.log','legacy-regression-final.log','previous-evidence-verification.json','applications.json']
for name in logs:copy(C/name,'validation/'+name)
for folder,name in [('ui-final','ui-semi'),('ui-tuning','ui-tuning'),('ui-sequential','ui-sequential'),('ui-idle','ui-idle')]:
 src=C/folder/('sequential-ui-tests.json' if folder=='ui-sequential' else 'ui-tests.json');copy(src,f'browser/{name}.json')
 for p in (C/folder).glob('*.png'):copy(p,'browser/'+name+'-'+p.name)
for name in ('comparison.png','comparison.svg','comparison.html','metrics.csv'):copy(C/'plot'/name,name)
copy(C/'ui-final/semi-browser.msl','applications/semi-browser.msl')
copy(C/'ui-final/semi-browser.msq','applications/browser006.msq')
copy(R/'tuning/examples/tunerstudio-semi-roundtrip.msq','applications/tunerstudio-semi-roundtrip.msq')
for name in ('semi-dialog-before.png','semi-dialog-after.png','semi-saved.png'):copy(C/'ts'/name,'applications/'+name)
copy(C/'mlv/semi-log-viewer.png','applications/megalogviewer.png')
for label in ('n16r8','a3','bench'):
 for p in (C/f'isr-final-{label}').iterdir():
  if p.is_file():copy(p,f'target/isr-{label}/{p.name}')
for label in ('n16r8','a3'):copy(C/f'usb-final-{label}.json',f'target/usb-{label}.json')
for folder,label in [('speeduino-sim','native32'),('speeduino-sim16','timer16')]:
 copy(R/'.cache/engine'/folder/'build-manifest.json',f'reference/{label}.json')
 copy(C/'reference-before'/folder/'build-manifest.json',f'reference/historical-{label}.json')
for folder,label in [('semi-storage-review','storage'),('semi-telemetry-review','telemetry'),('semi-architecture-final-review','execution')]:
 base=R/'.cache/engine'/folder
 for p in base.rglob('*'):
  if p.is_file() and p.suffix in ('.json','.py','.cpp','.log','.txt','.hpp','.h') and '__pycache__' not in p.parts:
   copy(p,Path('reviews')/label/p.relative_to(base))
patterns=['firmware/include/**/*.hpp','firmware/main/*.cpp','firmware/main/*.hpp','firmware/main/*.h','firmware/tests/**/*.cpp','firmware/tests/**/*.hpp','firmware/tests/**/*.h','firmware/platformio.ini','firmware/partitions.csv','firmware/boards/*.json','firmware/sdkconfig.*','firmware/components/esp_driver_usb_serial_jtag/**/*','scripts/*.py','scripts/*.sh','tools/*.py','tools/*.cpp','tools/*.hpp','config/engine/*.json','config/interface-guide*.json','config/defaults.json','config/manual.json','web/*.html','web/*.js','tuning/*.json','tuning/*.ini','tuning/examples/*.msq','docs/engine*.md','docs/espnow-engine.md','simulation/modelica/EngineAirPath.mo']
paths=set()
for pattern in patterns:
 for p in R.glob(pattern):
  if p.is_file() and not any(part in ('__pycache__','.pio') for part in p.parts):paths.add(p)
sources={str(p.relative_to(R)):sha(p.read_bytes()) for p in sorted(paths)}
for p in sorted(paths):copy(p,Path('sources')/p.relative_to(R))
# Freeze source hashes before publishing. Validation scripts themselves are part
# of this closure. No private application binaries or copied licenses are bundled.
summary=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),branch='feature/engine-development-sil',scope='Selectable four-cylinder timed semi-sequential software increment; broader feature goal remains active',physical_qualification=False,source_sha256=sources,validation=dict(python_tests=147,semi_tests=12,sanitized_pair_cases=252,coupled_cases=28,step_refinement_cases=8,legacy_warm_runs=8,browser_workflows=['semi','tuning','sequential','idle'],firmware_builds=['compact_n16r8_web','compact_a3_web','compact_a3_timing_bench']),limits=['Uncalibrated hybrid MVEM/empirical plant; zero CPU/IRQ cost','35Nm load not sustained; exact bounded dwell/plan stop retained','Predicted starts can follow last crank before actual20..150ms watchdog expiry','Own006 offline files verified; online TunerStudio identity acceptance unresolved','All hardware, RF, engine, timing, power, thermal and fit holds remain','Initial audit files are retained diagnostic history; final matrix and final source closure are authoritative'])
(O/'validation-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
copy(Path(__file__),'publication-script.py')
print(json.dumps(dict(files=sum(p.is_file() for p in O.rglob('*')),source_files=len(sources),bytes=sum(p.stat().st_size for p in O.rglob('*') if p.is_file()))))
