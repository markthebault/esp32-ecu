#!/usr/bin/env python3
"""Publish a fresh, immutable transient software-evidence packet."""
import argparse,base64,gzip,hashlib,io,json,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache/engine/transient'
sha=lambda b:hashlib.sha256(b).hexdigest()
TEXT={'.hpp','.cpp','.h','.c','.py','.json','.md','.ini','.msq','.js','.log','.csv','.txt','.su','.xml','.sh','.html','.css','.cmake','.mo'}

def publish(out):
 if out.exists():raise RuntimeError('Evidence destination exists; publish a new packet instead of overwriting it')
 matrix=json.loads((CACHE/'matrix-qualified/summary.json').read_text());legacy=json.loads((CACHE/'legacy/summary.json').read_text());apps=json.loads((CACHE/'application-checks.json').read_text())
 assert matrix['passed'] and len(matrix['runs'])==64 and legacy['passed'] and apps['passed']
 assert 'Ran 155 tests' in (CACHE/'python-final.log').read_text() and '\nOK\n' in (CACHE/'python-final.log').read_text()
 assert 'Engine observation, bounded log' in (CACHE/'native-after-expiry.log').read_text() and 'Actual task logger:' in (CACHE/'native-after-expiry.log').read_text()
 assert '3 succeeded' in (CACHE/'target-builds-final.log').read_text()
 for folder in ('ui-app-final','ui-logger-final','ui-tuning','ui-semi','ui-idle','ui-cylinder','ui-sequential-fixed'):
  report='sequential-ui-tests.json' if folder=='ui-sequential-fixed' else 'ui-tests.json'
  assert json.loads((CACHE/folder/report).read_text())['passed']
 out.mkdir(parents=True)
 def write(name,data):
  p=out/name;p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists();p.write_bytes(data)
 def copy(source,name):write(name,source.read_bytes())
 for folder,dest in (('matrix-qualified','matrix'),('matrix','initial-matrix'),('legacy','legacy')):
  for p in sorted((CACHE/folder).glob('*.json')):
   if p.name=='summary.json':copy(p,dest+'/'+p.name)
   else:write(dest+'/'+p.name+'.gz',gzip.compress(p.read_bytes(),mtime=0))
 initial=json.loads((CACHE/'matrix/summary.json').read_text());initial_runner=ROOT/'.cache/engine/transient-execution-review/runner-reviewed-initial.py'
 assert sha(initial_runner.read_bytes())==initial['source_hashes']['tools/run_transient_scenarios.py']
 copy(initial_runner,'initial-matrix/run_transient_scenarios.py')
 for name in ('python-final.log','native-after-expiry.log','target-builds-final.log','build-reference32.log','build-reference16.log','legacy.log','matrix.log','matrix-qualified.log','application-checks.json','generator-check.json','radio-final.log'):
  copy(CACHE/name,'validation/'+name)
 for folder in ('ui-app-final','ui-logger-final','ui-tuning','ui-semi','ui-idle','ui-cylinder','ui-sequential-fixed'):
  for p in sorted((CACHE/folder).iterdir()):
   if p.is_file():copy(p,'browser/'+folder+'/'+p.name)
 for path in ('ts/transient-edited.png','ts/transient-curve.png','ts/transient-app.msq','ts/application.log','mlv/engine105-ae.png','mlv/sil62-ae.png','mlv/application.log'):
  copy(CACHE/path,'applications/'+path)
 copy(CACHE/'ui-observability-fixed/browser-collected.msl','applications/engine105.msl')
 copy(CACHE/'ui-app-final/transient-browser.msl','applications/sil62.msl')
 for p in (ROOT/'tuning/esp32-ecu-transient.ini',ROOT/'tuning/examples/tunerstudio-transient-roundtrip.msq'):copy(p,'applications/'+p.name)
 for name in ('transient-comparison.png','transient-comparison.svg'):copy(CACHE/name,name)
 figure=base64.b64encode((CACHE/'transient-comparison.png').read_bytes()).decode()
 html='<!doctype html><html><head><meta charset="utf-8"><style>figure{margin:0}img{display:block;width:100%;height:auto}figcaption{font:13px var(--font-sans);color:var(--muted-foreground);margin-top:8px}</style></head><body><figure><img alt="Transient rate, correction and warm/cold lambda-error comparisons" src="data:image/png;base64,'+figure+'"><figcaption>64 declared native comparison runs passed. Calibration-dependent results from an uncalibrated plant; no physical qualification.</figcaption></figure></body></html>'
 write('comparison.html',html.encode())
 for bits,folder in ((32,'speeduino-sim'),(16,'speeduino-sim16')):
  base=ROOT/'.cache/engine'/folder
  copy(base/'build-manifest.json','reference/build-'+str(bits)+'.json')
  copy(CACHE/'reference-before'/str(bits)/'build-manifest.json','reference/before-'+str(bits)+'.json')
 copy(ROOT/'.cache/engine/modelica-mvem/airpath/manifest.json','plant/fmu-manifest.json')
 review_names=('architecture','core','storage','execution')
 for name in review_names:
  base=ROOT/'.cache/engine'/('transient-'+name+'-review')
  for filename in ('review.json','review.md','assessment.md','results.json','manifest.json'):
   if (base/filename).exists():copy(base/filename,'reviews/'+name+'/'+filename)
  archive=io.BytesIO()
  with tarfile.open(fileobj=archive,mode='w') as packed:
   for p in sorted(base.rglob('*')):
    if not p.is_file() or p.suffix not in TEXT:continue
    data=p.read_bytes();member=tarfile.TarInfo(str(p.relative_to(base)));member.size=len(data);member.mode=0o644;member.mtime=0;packed.addfile(member,io.BytesIO(data))
  write('reviews/'+name+'/inputs-and-probes.tar.gz',gzip.compress(archive.getvalue(),mtime=0))
 sources=set()
 for folder in ('firmware/include','firmware/main','firmware/tests','firmware/components','tools','scripts','config','tuning','web','simulation/modelica'):
  sources.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in TEXT)
 sources.update(ROOT/p for p in ('.gitattributes','firmware/platformio.ini','firmware/partitions.csv','firmware/sdkconfig.defaults','firmware/sdkconfig.n16r8.defaults','README.md'))
 sources.update((ROOT/'docs').glob('engine*.md'));source_hashes={}
 for p in sorted(sources):
  if not p.exists():continue
  name=str(p.relative_to(ROOT));source_hashes[name]=sha(p.read_bytes());copy(p,'sources/'+name)
 for name,digest in matrix['source_hashes'].items():assert source_hashes[name]==digest,'Matrix source changed: '+name
 images={}
 for env in ('compact_a3_web','compact_n16r8_web','compact_a3_timing_bench'):
  b=ROOT/'firmware/.pio/build'/env
  images[env]={p.name:sha(p.read_bytes()) for p in (b/'firmware.elf',b/'firmware.bin')}
  config=ROOT/'firmware'/('sdkconfig.'+env)
  if config.exists():copy(config,'build-config/'+config.name)
 summary=dict(passed=True,scope='Transient software/configuration/UI/debugging increment; no physical, vendor-online or full-feature-parity qualification',baseline_commit='64c21ed29d5bf5b5a44c471bcc321b88c8ac5d38',
  python_tests=155,native_sanitizers=True,browser_workflows=7,radio_http_tests=20,controller_runs=48,refinement_runs=8,neutral_controls=8,legacy_exact_runs=8,
  initial_matrix='Preserved failed coverage/audit assumptions; superseded by explicit profiles and correction-neutral reference assertions in matrix/',
  independent_reviews=list(review_names),applications=apps,images_sha256=images,source_sha256=source_hashes,
  remaining='Full Speeduino feature parity, engine calibration, online application identity acceptance, physical ECU/HIL/electrical/EMI/thermal/splash/fit acceptance remain open')
 write('validation-summary.json',(json.dumps(summary,indent=2)+'\n').encode())
 readme='''# Transient fueling evidence

Schema6/own007 adds acquisition-window TPS/MAP curves, multiplier/reference-adder, latched tapers, finite holds and deceleration fuel reduction/cut. Selected web builds remain physically inhibited.

`matrix/` contains64 qualified runs, including48 primary,8 refinements and8 fuel-neutral controls. `initial-matrix/` preserves the earlier coverage failures and exact initial runner. Its other source bytes match `sources/`. `legacy/` compares exact executed events and plant ledgers with immutable pre-transient evidence.

Independent source snapshots/probes and corrected findings are under `reviews/`. Text inputs are archived; native executables/objects remain in the local cache and their reported hashes are records, not bundled binaries. Actual offline TunerStudio and MegaLogViewer files/screens are under `applications/`. Browser collected/native105-field exports agree. The unchanged232-byte radio does not carry the new detailed transient fields.

Source snapshots and raw traces are hash bound. Run `python3 tools/verify_transient_evidence.py`; use `--check-live-sources --check-index` for this revision before committing. Static/source/simulator evidence does not establish physical engine operation or full feature parity.
'''
 write('README.md',readme.encode())
 manifest={str(p.relative_to(out)):sha(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file()}
 write('artifact-manifest.json',(json.dumps(dict(files_sha256=manifest),indent=2)+'\n').encode())
 print(json.dumps(dict(artifacts=len(manifest),sources=len(source_hashes),output=str(out)),indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=ROOT/'reports/engine/transient-enrichment');a=p.parse_args();publish(a.output_dir)
