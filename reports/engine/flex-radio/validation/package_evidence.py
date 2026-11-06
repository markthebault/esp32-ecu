import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path.cwd();P=ROOT/'.cache/engine/flex-radio-parent';BUILD=ROOT/'.cache/engine/flex-radio-build-001';REVIEW=ROOT/'.cache/engine/flex-radio-review';OUT=ROOT/'reports/engine/flex-radio'
OUT.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2)+'\n')
def cp(source,dest):
 dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
def tree(source,dest,exclude=lambda p:False):
 for path in sorted(source.rglob('*')):
  assert not path.is_symlink(),path
  if path.is_file() and not exclude(path):cp(path,dest/path.relative_to(source))
source_names=set(json.loads((BUILD/'sources-before.json').read_text()))
source_names.update(str(p.relative_to(ROOT)) for p in (ROOT/'tools').rglob('*') if p.is_file() and p.suffix in ('.py','.cpp','.hpp','.h') and '__pycache__' not in p.parts)
source_names.update(('docs/espnow-engine.md','docs/espnow.md','docs/engine-flex-fuel.md','docs/engine-feature-coverage.md','hardware/flex-input/architecture.json'))
hashes={name:sha(ROOT/name) for name in sorted(source_names)}
for name,digest in hashes.items():
 cp(ROOT/name,OUT/'sources'/name);assert sha(OUT/'sources'/name)==digest
for name,digest in json.loads((BUILD/'sources-before.json').read_text()).items():assert hashes[name]==digest
for path in BUILD.iterdir():
 if path.is_file() and path.suffix in ('.json','.log'):cp(path,OUT/'build'/path.name)
for name in ('elf-archives','sdkconfigs-after','retained-sdkconfigs'):tree(BUILD/name,OUT/'build'/name)
for env in json.loads((BUILD/'summary.json').read_text())['environments']:
 cp(BUILD/'build'/env/'firmware.bin',OUT/'build/images'/(env+'.bin'))
 # Compile database is retained for provenance; no object cache is published.
 cp(BUILD/'build'/env/'compile_commands.json',OUT/'build/compile-databases'/(env+'.json'))
tree(P/'audits',OUT/'audits')
omitted=[]
for path in sorted(REVIEW.rglob('*')):
 if not path.is_file():continue
 assert not path.is_symlink()
 name=str(path.relative_to(REVIEW))
 if path.suffix=='.o' or path.read_bytes()[:4]==b'\x7fELF':
  omitted.append(dict(path=name,bytes=path.stat().st_size,sha256=sha(path)));continue
 cp(path,OUT/'reviews/independent'/name)
save(OUT/'reviews/omitted-generated-binaries.json',dict(scope='Generated native executables/object omitted from curated report; exact originals remain in owned cache. Sources, receipts, dependency lists and all bound evidence retained.',artifacts=omitted))
service=P/'service-004'
tree(service,OUT/'native',lambda p:p.name in ('test','cjson.o'))
cp(P/'service-004-interop.json',OUT/'validation/sender-receiver.json')
for source,name in (('ui-003','radio'),('semi-ui-001','semi'),('flex-ui-001','flex'),('led-ui-001','led')):tree(P/source,OUT/'browser'/name)
tree(ROOT/'reports/engine/shared-status-led/fixtures',OUT/'dependencies/led-fixtures')
tree(P/'plant-001',OUT/'plant')
sdk=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
for name in ('cJSON.c','cJSON.h'):cp(sdk/name,OUT/'dependencies/cJSON'/name)
for path in sorted(P.glob('*.log')):cp(path,OUT/'validation/parent-logs'/path.name)
cp(P/'run_audits.py',OUT/'validation/run_audits.py')
cp(Path(__file__),OUT/'validation/package_evidence.py')
# Record independently accepted implementation hashes with a specific UI overlay.
review=json.loads((REVIEW/'review.json').read_text());update=json.loads((REVIEW/'review-ui-recheck.json').read_text())
effective={**review['source_hashes'],**update['source_hashes']}
assert all(hashes[name]==digest for name,digest in effective.items())
versions={}
for tool,args in [('python3',['--version']),('g++',['--version']),('cc',['--version']),('openssl',['version']),('google-chrome',['--version']),('pio',['--version'])]:
 r=subprocess.run([tool,*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);versions[tool]=dict(returncode=r.returncode,output=r.stdout.strip())
save(OUT/'validation/tool-versions.json',versions)
save(OUT/'summary.json',dict(scope='coherent_flex_radio_software',checks_passed=True,flashed=False,target_execution=False,actual_RF=False,screen_application=False,physical_qualification=False,ethanol_chemistry_validated=False,new_production_speeduino_comparison=False,full_speeduino_parity=False,source_hashes=hashes,independent_review_sha256=sha(REVIEW/'review.json'),independent_ui_recheck_sha256=sha(REVIEW/'review-ui-recheck.json'),independent_effective_paths=len(effective),parent_checks=dict(regression_test_cases=131,pair_policy_assertions=1049,actual_sender_service_assertions=81,new_receiver_test_cases=15,individual_tamper_positions=482,fixed_gasoline_plant_cases=27,firmware_builds=4,isr_policy_audits_each=4,usb_audits=3),qualification='Actual sender/handler source in native SDK API models, bounded pure receiver, owned Chrome and reduced-order fixed-gasoline plant; linked/static firmware audits. No actual ESP-IDF task, RF, physical screen/LED, target timing/HIL, ethanol chemistry or engine qualification. Parent packages evidence; independent review excludes packaging, final target builds and Chrome.',remaining_work=['Protected GPIO38 input circuit, PCB and case integration with physical reset/PAIR and electrical qualification','Actual ESP32/receiver RF, USB, timing/load and HIL execution','Ethanol-aware plant calibration, online tuning vendor support and wider Speeduino feature gaps']))
print(json.dumps(dict(output=str(OUT),sources=len(hashes),independent_paths=len(effective),omitted_native_binaries=len(omitted))))
