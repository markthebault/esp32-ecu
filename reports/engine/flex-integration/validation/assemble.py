"""One-shot assembly of this software evidence; refuses an existing output."""
from pathlib import Path
import argparse,datetime,gzip,hashlib,json,shutil,subprocess

ROOT=Path(__file__).resolve().parents[3]
# This helper is recorded in the packet. Its live location is .cache/engine/flex-integration.
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'.git').exists())
CACHE=ROOT/'.cache/engine/flex-integration';REVIEW=ROOT/'.cache/engine/flex-integration-review'
def sha(body):return hashlib.sha256(body).hexdigest()
def read(p):return json.loads(p.read_text())
def main(out,host):
 if out.exists():raise ValueError('Output exists; choose a new publication path')
 reviews=[('kernel',REVIEW/'kernel-independent-review.json'),('host',host)]
 for name,p in reviews:
  r=read(p)
  if not r['accepted']or r['open_findings']:raise ValueError('Review is not closed: '+name)
 out.mkdir(parents=True)
 def copy(src,rel):
  target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
 def tree(src,rel):
  for p in sorted(src.rglob('*')):
   if p.is_file()and not p.is_symlink():copy(p,str(Path(rel)/p.relative_to(src)))
 prefixes=['firmware','tools','scripts','web','config','tuning','docs']
 names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard',*prefixes],cwd=ROOT).decode().splitlines()
 suffixes={'.hpp','.h','.c','.cpp','.py','.js','.html','.json','.ini','.sh','.md','.msq','.csv','.txt','.defaults'}
 names=sorted({n for n in names if Path(n).suffix in suffixes and '/.pio/'not in n and (ROOT/n).is_file()and not (ROOT/n).is_symlink()})
 sources={}
 for name in names:
  copy(ROOT/name,'sources/'+name);sources[name]=dict(snapshot='sources/'+name,sha256=sha((ROOT/name).read_bytes()))
 matrix=CACHE/'plant-002';index=read(matrix/'index.json')
 for name,digest in index['source_sha256'].items():
  if sources[name]['sha256']!=digest:raise ValueError('Matrix source changed: '+name)
 tree(matrix,'plant')
 for name,p in reviews:
  r=read(p);bound=r['source_hashes']
  for source,digest in bound.items():
   if sources[source]['sha256']!=digest:raise ValueError('Reviewed source changed: '+source)
  copy(p,'reviews/'+p.name)
 copy(REVIEW/'kernel-review.md','reviews/kernel-review.md')
 # Keep source/commands, early findings and final closures, but never ELFs.
 for p in sorted(REVIEW.iterdir()):
  if not p.is_file()or p.suffix not in {'.cpp','.py','.js','.json','.log','.md'}:continue
  if p.stat().st_size>2*1024*1024:
   target=out/'reviews'/(p.name+'.gz');target.parent.mkdir(exist_ok=True);target.write_bytes(gzip.compress(p.read_bytes(),mtime=0))
  else:copy(p,'reviews/'+p.name)
 tree(REVIEW/'baseline-8c589a4','reviews/baseline')
 for folder in sorted(REVIEW.glob('kernel-freeze-*')):
  tree(folder,'reviews/'+folder.name)
 for folder in sorted(REVIEW.glob('host-freeze-*')):
  # Only initial/final changed UI/stimulus files and freeze inventory. The final
  # reviewed implementation/dependencies are already bound under sources/.
  for rel in ('web/flex_fuel_logic.js','web/flex_fuel.js','tools/flex_stimulus.py'):
   if (folder/rel).exists():copy(folder/rel,'reviews/'+folder.name+'/'+rel)
  for p in folder.glob('*manifest*.json'):copy(p,'reviews/'+folder.name+'/'+p.name)
 for name,src in [('flex','ui-flex-005'),('tuning','ui-tuning-002'),('secondary','ui-secondary-002'),('observability','ui-observability-002')]:tree(CACHE/src,'browser/'+name)
 tree(CACHE/'build-final','build')
 for rel in ('native-004.log','python-006.log','firmware-004.log','flex-tests-003.log','native-sizes.json','sizes.cpp','selected-symbol-sizes.txt'):
  target={'native-004.log':'native.log','python-006.log':'python.log','firmware-004.log':'firmware.log'}.get(rel,rel);copy(CACHE/rel,'validation/'+target)
 # Preserve failed linker and browser/native attempts as records, separately.
 for rel in ('firmware-001.log','native-001.log','native-002.log','python-001.log','python-002.log','python-003.log','ui-flex-001.log','ui-tuning-001.log'):
  copy(CACHE/rel,'validation/earlier-attempts/'+rel)
 for name in ('compact_n16r8_web','compact_a3_web','compact_a3_timing_bench'):copy(ROOT/('firmware/sdkconfig.'+name),'build/sdkconfig.'+name)
 app=CACHE/'applications'
 for rel in ('application-tune.json','application010.msq','application-edited010.msq','application-edited010-002.msq','application-edited010-003.msq','application-roundtrip.json','application-page.bin','application-tune-roundtrip.json','mlv-check.json','mlv-ethanol-plot.png','ts-final-save.png','flex-waveform007.msl','flex-waveform-metadata.json','flex-qualified-window007.msl','flex-qualified-window-metadata.json','start-ts.py','start-mlv.py'):
  copy(app/rel,'applications/'+rel)
 copy(app/'ts/user/TunerStudioProjects/TunerStudioAppDebug.txt','applications/tunerstudio-debug.txt')
 copy(app/'ts/application.log','applications/tunerstudio-stdout.log')
 copy(app/'mlv/application.log','applications/mlv-stdout.log')
 copy(Path(__file__),'validation/assemble.py')
 summary=dict(scope='flex_development_software_integration',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks_passed=True,
  target_capture_implemented=False,pcb_input_released=False,flex_radio_implemented=False,physical_qualification=False,online_tuner_accepted=False,ethanol_combustion_validated=False,full_speeduino_parity=False,
  controller_integrated=True,configuration_schema=9,tuning_identity='ESP32ECU DEV 010 INHIBITED',page_bytes=8192,live_bytes=832,engine_msl_columns=229,direct_sil_columns=186,recorder_rows=128,
  parent_kernel_checks=296,parent_python_tests=132,plant_cases=27,off_baseline_rows=14400,sources=sources,
  reviews=[dict(name=name,path='reviews/'+p.name,bound_sources=read(p)['source_hashes'])for name,p in reviews],
  prior_reference=dict(path='reports/engine/flex-core',manifest_sha256=sha((ROOT/'reports/engine/flex-core/artifact-manifest.json').read_bytes()),scope='Separate25-case pinned production raw-edge groundwork, unchanged. No production executable was run for this integration matrix.'),
  qualification='Development software only. Fixed-gasoline empirical SIL, offline vendor application files, static target builds and independent source/host review. No flashing, target capture hardware, GPIO measurement, ethanol combustion, USB/HIL or vehicle/environment/fit qualification. Prepared vendor email/ZIP remain unsent.')
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 (out/'README.md').write_text('''# Flex software integration evidence

This checkpoint connects raw flex capture to the shared controller, schema9 persistence, own010 tuning, browser controls and source/age/fault diagnostics. **Protected target acquisition and a released PCB input are still missing.** Enabled target flex inhibits control. Selected physical engine outputs remain inhibited. Screen schemas1..4 suppress engine telemetry whenever flex is required; a negotiated flex extension remains open.

Validated behavior includes fuel/temperature factors before reference acceleration fuel, zero-factor suppression of all fuel/deadtime, cranking spark bypass, secondary/cylinder ordering and coherent sample/calibration/revision/fault ownership. Historical schema1..8 imports initialize flex disabled and neutral; edited schema8 secondary maps survive. Explicit scalar synthetic ETH cannot qualify for corrections.

Evidence includes296 parent kernel checks and the full sanitizer suite;132 Python integration tests; actual Chrome flex/tuning/secondary/logger checks; independent kernel and host reviews;14,400 bit-exact Off-baseline rows; and27 saved own-controller fixed-gasoline plant cases. Neutral controls retain identical virtual edges, fuel totals and final RPM. Missing/stale inputs and zero factors cut as declared. The independent review records its own ordering, corruption, ownership, CAS, runtime and saved-plant checks.

The plant matrix is not a new production Speeduino comparison or an ethanol chemistry model. The separate earlier25-case production raw-edge packet remains at ../flex-core with its own immutable sources and disclosed historical generated-coverage side effect. No production ELF was executed for this integration checkpoint.

Actual unmodified TunerStudio MS Lite3.3.01 opens own010 offline, edits filter125.5 to130.5 and saves an MSQ matching all8192 expected bytes on native import. Earlier automation saves without a committed edit are retained separately. MegaLogViewer HD Lite4.6.14 loads the original121-row,229-column native waveform log and plots ethanol, including preserved startup unknowns. These are file workflows. Own010 online acceptance remains unverified; earlier own009 online rejection and vendor integration remain unresolved. No support message was sent.

The full runtime block is832 bytes, preserving the640-byte prefix. MSL007 has229 engine /186 direct SIL columns. ExactU64 values remain strings in JSON and decimal integers in files; viewer displays can round them. Record136B, RuntimeSample664B and Recorder87,128B are native ABI measurements. Device retention is128 rows, with gap/overwrite accounting. Keeping256 expanded rows overflowed linked internal DRAM; failed builds are retained. Three fresh firmware builds and static output-policy/ISR/USB audits pass. This does not measure target minimum heap, stack, latency, USB, sensor or electrical behavior.

Verify from the repository with `python3 -B tools/verify_flex_integration_evidence.py`; add `--check-live-sources` to bind the current workspace or `--replay` to rerun saved-case checks,296 sanitizer checks and the14,400-row exact Off comparison. Snapshots are immutable; replay uses temporary output paths. `summary.json` and `artifact-manifest.json` bind all files. Vendor application binaries and proprietary PDFs are excluded.
''')
 entries=[]
 for p in sorted(out.rglob('*')):
  if p.is_file():body=p.read_bytes();entries.append(dict(path=str(p.relative_to(out)),bytes=len(body),sha256=sha(body)))
 (out/'artifact-manifest.json').write_text(json.dumps(dict(schema=1,artifacts=entries),indent=2)+'\n')
 print(json.dumps(dict(artifacts=len(entries),sources=len(sources),manifest_sha256=sha((out/'artifact-manifest.json').read_bytes()))))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--host-review',required=True,type=Path);a=p.parse_args();main(a.output.resolve(),a.host_review.resolve())
