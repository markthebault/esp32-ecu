#!/usr/bin/env python3
"""Publish a fresh source-bound load/pressure/AFR evidence packet."""
import argparse,base64,gzip,hashlib,io,json,subprocess,tarfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache/engine/load'
TEXT={'.hpp','.cpp','.h','.c','.py','.json','.md','.ini','.msq','.js','.log','.csv','.txt','.su','.xml','.sh','.html','.css','.cmake','.mo'}
UI=('ui-bound','ui-logger','ui-tuning-final','ui-transient-final','ui-semi','ui-idle','ui-cylinder-final','ui-sequential','ui-engine')
sha=lambda b:hashlib.sha256(b).hexdigest()

def publish(out):
 if out.exists():raise RuntimeError('Evidence destination exists; preserve it and choose a fresh path')
 matrix=json.loads((CACHE/'matrix-final/summary.json').read_text());legacy=json.loads((CACHE/'legacy/summary.json').read_text());apps=json.loads((CACHE/'application-checks.json').read_text())
 assert matrix['passed'] and len(matrix['runs'])==64 and all(r['passed'] for r in matrix['refinements'])
 assert legacy['passed'] and len(legacy['cases'])==8 and apps['passed'] and apps['owned_applications_closed']
 assert 'Ran 173 tests' in (CACHE/'python-final.log').read_text() and '\nOK\n' in (CACHE/'python-final.log').read_text()
 assert 'Actual task logger:' in (CACHE/'native-final.log').read_text() and '6168 rejected' in (CACHE/'native-final.log').read_text()
 assert '3 succeeded' in (CACHE/'build-all-final.log').read_text() and 'Ran 20 tests' in (CACHE/'radio-http-final.log').read_text()
 for folder in UI:assert json.loads((CACHE/folder/('sequential-ui-tests.json' if folder=='ui-sequential' else 'ui-tests.json')).read_text())['passed']
 sim=ROOT/'.cache/engine/load-simulator-review';initial=json.loads((sim/'snapshot.json').read_text())['files'];closure=json.loads((sim/'closure/snapshot.json').read_text())
 bindings={r['path']:r['sha256'] for r in initial};bindings.update({r['path']:r['sha256'] for r in closure})
 # The independent reviewer froze execution inputs before probing, then
 # separately froze the endpoint closure and replayed all final traces.
 # Later GUI test refinements are not represented as reviewed control code.
 bindings={p:h for p,h in bindings.items() if not Path(p).name.startswith('test_')}
 for p,h in bindings.items():assert sha((ROOT/p).read_bytes())==h,'Execution source differs from independent snapshot: '+p
 review_metadata={}
 for name in ('architecture','core','integration','simulator'):
  base=ROOT/'.cache/engine'/('load-'+name+'-review');manifest=base/('manifest.json' if name in ('integration','simulator') else 'artifact-manifest.json');m=json.loads(manifest.read_text());rows=next(m[k] for k in ('files','items','artifacts') if k in m)
  for row in rows:assert sha((base/row['path']).read_bytes())==row['sha256'],'Reviewed artifact changed: '+str(base/row['path'])
  review_metadata[name]=dict(verified_cache_artifacts=len(rows),manifest_sha256=sha(manifest.read_bytes()))
 out.mkdir(parents=True)
 def write(name,data):
  p=out/name;p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists();p.write_bytes(data)
 def copy(p,name):write(name,p.read_bytes())
 for p in sorted((CACHE/'matrix-final').glob('*')):
  if p.is_file():copy(p,'matrix/'+p.name)
 for p in sorted((CACHE/'legacy').glob('*.json')):
  if p.name=='summary.json':copy(p,'legacy/'+p.name)
  else:write('legacy/'+p.name+'.gz',gzip.compress(p.read_bytes(),mtime=0))
 for filename in ('calibration-alpha.json','generator-check.json','application-checks.json'):copy(CACHE/filename,'validation/'+filename)
 logs=('python-final.log','native-final.log','build-all-final.log','build-reference32-final.log','build-reference16-final.log','radio-http-final.log','matrix-final.log','legacy.log','calibration-alpha-ramped.log','ui-bound.log')
 for filename in logs:copy(CACHE/filename,'validation/'+filename)
 for folder in UI:
  for p in sorted((CACHE/folder).iterdir()):
   if p.is_file():copy(p,'browser/'+folder+'/'+p.name)
 for name in ('selected','a3','bench'):
  for p in sorted((CACHE/('policy-'+name+'-final')).iterdir()):copy(p,'static/policy-'+name+'/'+p.name)
 copy(CACHE/'tuning-usb-final.json','static/tuning-usb.json')
 for p in sorted((CACHE/'isr-final').iterdir()):
  if p.is_file():copy(p,'static/isr/'+p.name)
 for name in ('ts/load-edited.png','ts/load-app008.msq','ts/msq-check.json','ts/application.log','mlv/engine126.png','mlv/sil83.png','mlv/application.log','start-ts.py','start-mlv.py'):copy(CACHE/name,'applications/'+name)
 sys.path.insert(0,str(ROOT/'tools'))
 from run_load_scenarios import configuration
 from engine_protocol import pages
 from engine_msq import import_msq
 expected=configuration('alpha',json.loads((CACHE/'calibration-alpha.json').read_text()))['tune'];expected['load_model'].update(afr='measured',fixed_baro_kpa=99.5,afr_delay_s=2.5)
 expected_page=pages(expected)[1];actual_page=pages(import_msq((CACHE/'ts/load-app008.msq').read_bytes()))[1];assert actual_page==expected_page
 write('applications/expected-page.bin',expected_page);write('applications/application-page.bin',actual_page)
 for p in ('tuning/esp32-ecu-load.ini','tuning/examples/tunerstudio-load-roundtrip.msq'):copy(ROOT/p,'applications/'+Path(p).name)
 copy(CACHE/'ui-logger/browser-collected.msl','applications/engine126.msl');copy(CACHE/'ui-transient/transient-browser.msl','applications/sil83.msl')
 for p in sorted((CACHE/'plots').iterdir()):copy(p,p.name)
 encoded=base64.b64encode((CACHE/'plots/load-comparison.png').read_bytes()).decode()
 write('comparison.html',('<!doctype html><html><meta charset="utf-8"><style>figure{margin:0}img{display:block;width:100%;height:auto}figcaption{font:13px var(--font-sans);color:var(--muted-foreground)}</style><figure><img alt="Synthetic load-source, baro and calibration-control comparisons" src="data:image/png;base64,'+encoded+'"><figcaption>64 declared software comparisons. Independent steady-airflow Alpha-N fixture; empirical combustion. Not engine or electrical qualification.</figcaption></figure></html>').encode())
 for name in ('architecture','core','integration','simulator'):
  base=ROOT/'.cache/engine'/('load-'+name+'-review');archive=io.BytesIO();archived=0
  with tarfile.open(fileobj=archive,mode='w') as packed:
   for p in sorted(base.rglob('*')):
    if not p.is_file() or not(p.suffix in TEXT or p.suffix=='.gz' or p.name=='SHA256SUMS'):continue
    data=p.read_bytes();member=tarfile.TarInfo(str(p.relative_to(base)));member.size=len(data);member.mode=0o644;member.mtime=0;packed.addfile(member,io.BytesIO(data));archived+=1
  write('reviews/'+name+'/inputs-and-probes.tar.gz',gzip.compress(archive.getvalue(),mtime=0));review_metadata[name]['archived_text_trace_inputs']=archived
  for filename in ('architecture-assessment.md','review.md','review.json','artifact-manifest.json','manifest.json'):
   if (base/filename).exists():copy(base/filename,'reviews/'+name+'/'+filename)
 copy(sim/'snapshot.json','reviews/simulator/initial-source-snapshot.json');copy(sim/'closure/snapshot.json','reviews/simulator/closure-source-snapshot.json')
 write('reviews/simulator/executed-source-binding.json',(json.dumps(dict(basis='Independent initial/closure source freezes, production-build consistency and replay of all64 final traces; GUI test files excluded',source_sha256=bindings),indent=2)+'\n').encode())
 arch=ROOT/'.cache/engine/load-architecture-review';copy(arch/'baseline-msq-oracle.json','reviews/architecture/baseline-msq-oracle.json')
 for p in sorted((arch/'legacy-msq-oracles').glob('*.msq')):copy(p,'reviews/architecture/legacy-msq-oracles/'+p.name)
 for bits,folder in ((32,'speeduino-sim'),(16,'speeduino-sim16')):
  copy(ROOT/'.cache/engine'/folder/'build-manifest.json','reference/build-'+str(bits)+'.json');copy(CACHE/'reference-before'/str(bits)/'build-manifest.json','reference/before-'+str(bits)+'.json')
 copy(ROOT/'.cache/engine/modelica-mvem/airpath/manifest.json','plant/fmu-manifest.json')
 sources=set()
 for folder in ('firmware/include','firmware/main','firmware/tests','firmware/components','tools','scripts','config','tuning','web','simulation/modelica'):
  sources.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in TEXT)
 sources.update(ROOT/p for p in ('.gitattributes','firmware/platformio.ini','firmware/partitions.csv','firmware/sdkconfig.defaults','firmware/sdkconfig.n16r8.defaults','README.md','docs/espnow-engine.md','hardware/a3-compact/net_contract.json'))
 sources.update((ROOT/'docs').glob('engine*.md'));source_hashes={}
 for p in sorted(sources):
  name=str(p.relative_to(ROOT));source_hashes[name]=sha(p.read_bytes());copy(p,'source-metadata/root.gitattributes' if name=='.gitattributes' else 'sources/'+name)
 for p,h in bindings.items():assert source_hashes[p]==h
 images={}
 for env in ('compact_a3_web','compact_n16r8_web','compact_a3_timing_bench'):
  b=ROOT/'firmware/.pio/build'/env;images[env]={p.name:sha(p.read_bytes()) for p in (b/'firmware.elf',b/'firmware.bin')};copy(ROOT/'firmware'/('sdkconfig.'+env),'build-config/sdkconfig.'+env)
 summary=dict(passed=True,scope='Load/pressure/AFR software, configuration, UI, debugging and simulation increment only',baseline_commit='1d6a9acb34838ea175f2dfa7ccd9786e96d2d11b',
  python_tests=173,native_sanitizers=True,browser_workflows=len(UI),radio_http_tests=20,primary_runs=56,refinement_runs=8,legacy_exact_runs=8,independent_reviews=review_metadata,
  applications=apps,images_sha256=images,source_sha256=source_hashes,execution_source_binding='Independent simulator initial/closure freezes with production-build consistency and all64 final trace replays, not a fabricated run-captured source manifest',
  remaining='Secondary tables, separate baro correction, wider Speeduino features, online vendor acceptance, physical HIL/engine/electrical/EMI/surge/thermal/splash/fit qualification remain open')
 write('validation-summary.json',(json.dumps(summary,indent=2)+'\n').encode())
 readme='''# Load, pressure and AFR evidence

Schema7/own008 adds independent MAP/TPS/IMAP-EMAP table coordinates, explicit table bases, pressure normalization, AFR incorporation and calibrated optional J16 roles. Selected web builds retain inhibited engine/idle output policy.

`matrix/` contains56 primary plus8 selected half-step runs across project portable/target dispatchers and pinned production Speeduino32/16 timer models. `legacy/` retains8 exact executed-event and plant-ledger replays. Alpha-N calibration has244 independently settled cells and12 unqualified pressure-corridor cells; none of the latter were weighted by the tested trajectories. Outcomes include failed calibration, differing guard/AFR policies and rich reference operation; passed audits do not mean ideal tunes.

Four independent scoped reviews are under `reviews/`. Initial/corrected source bytes, text probes and compressed trace inputs are archived. Native probe executables/objects remain in the local cache; their hashes in reviewer manifests are records, not bundled binaries. The simulator review binds the execution sources separately from the publication snapshot and independently replays the final64 traces. Live source checks verify that binding. There is no claim of a run-captured manifest that the runner did not produce.

`applications/` includes actual offline TunerStudio008 edits, exact5376-byte F32/enum-page roundtrip,126/83-field MegaLogViewer files and screens. Nine Chrome workflows cover unit review, CAS, imports, logging and existing controls. `static/` contains actual linked policy, ISR and USB/source audits, not measured runtime/electrical qualification. Current source copies are under `sources/`; root attributes are retained inertly under `source-metadata/` so they cannot change copied-file storage. All packet artifacts are hash listed.

Run `python3 tools/verify_load_evidence.py`; add `--check-live-sources --check-index` before committing this revision. Historical source/manufacturing/case/manual/report bytes are retained. Full feature parity, online application identity acceptance and physical qualification remain open.
'''
 write('README.md',readme.encode());manifest={str(p.relative_to(out)):sha(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file()};write('artifact-manifest.json',(json.dumps(dict(files_sha256=manifest),indent=2)+'\n').encode())
 print(json.dumps(dict(artifacts=len(manifest),sources=len(source_hashes),output=str(out)),indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=ROOT/'reports/engine/load-model');a=p.parse_args();publish(a.output_dir)
