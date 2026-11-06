from pathlib import Path
import hashlib,json,shutil,subprocess
ROOT=Path('/home/mark/persospace/esp32-ecu');CACHE=ROOT/'.cache/engine/flex-core';REVIEW=ROOT/'.cache/engine/flex-acquisition-review';OUT=ROOT/'reports/engine/flex-core'
sha=lambda body:hashlib.sha256(body).hexdigest()
def write(name,body):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb')as out:out.write(body)
def copy(source,name):write(name,Path(source).read_bytes())
def doc(name,value):write(name,(json.dumps(value,indent=2)+'\n').encode())
names=['firmware/include/ecu/flex_fuel.hpp','firmware/tests/flex_fuel_test.cpp','scripts/build_speeduino_flex.py','tools/speeduino_flex_sim.cpp','tools/run_flex_scenarios.py','tools/check_flex_experiments.py','tools/verify_flex_core_evidence.py','scripts/test_firmware.sh','docs/engine-flex-fuel.md','docs/engine-feature-coverage.md','scripts/build_speeduino_sim.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp']
sources={}
for name in sorted(names):
 body=(ROOT/name).read_bytes();snapshot='sources/'+name;write(snapshot,body);sources[name]=dict(snapshot=snapshot,sha256=sha(body))
for p in sorted((CACHE/'matrix-002').iterdir()):
 if p.is_file():copy(p,'matrix/'+p.name)
copy(CACHE/'matrix-checks-002.json','checks.json')
for name in('core-independent-001.cpp','core-boundary-002.cpp','coverage-side-effect.json','core-test-results-002.json','source-review-binding.json'):
 copy(REVIEW/name,'reviews/'+name)
binding=json.loads((REVIEW/'source-review-binding.json').read_text());upstream={}
for name in sorted(set(binding['source_sha256'])|{'LICENSE'}):
 body=(ROOT.parent/'speeduino'/name).read_bytes();snapshot='upstream/'+name;write(snapshot,body);upstream[name]=dict(snapshot=snapshot,sha256=sha(body))
for source,name in [('reference-build-004.log','reference-build.log'),('firmware-tests-gcc-001.log','firmware-tests-gcc.log'),('firmware-tests-final.log','default-clang-unavailable.log'),('assemble_packet.py','assembly-record.py')]:copy(CACHE/source,'validation/'+name)
for stem in('speeduino-sim','speeduino-sim16'):copy(ROOT/'.cache/engine'/stem/'build-manifest.json','validation/'+stem+'-manifest.json')
summary=dict(schema=1,scope='flex_raw_edge_groundwork',checks_passed=True,baseline_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),full_flex_integration=False,target_capture_implemented=False,physical_qualification=False,online_tuner_accepted=False,full_speeduino_parity=False,sources=sources,upstream=upstream,
 tests=dict(parent_core=509,independent_core=2101,independent_boundaries=21382,declared_raw_cases=25,rejected_corruptions=11,full_native_firmware_harness_passed=True,toolchain='CXX=g++'),
 independent_review='reviews/independent-review.json',coverage_side_effect_count=16,
 limits=['Own helpers not connected to engine Tune/target/UI/config/PCB/logs/radio or running plant','No physical engine/USB/flash/electrical/boot/timing qualification or full parity','Genuine production fixture keeps deterministic native HAL and zero CPU cost; original benchmark changes are recorded in its saved manifest','Native startup cache finding is conditional; physical boot timing was not tested','356Hz is a synthetic robustness probe, not a qualified sensor fault or EMI waveform','Initial reviewer probe changed16 generated coverage counters; tracked production sources and numerical binaries/manifests are unchanged; generated counters excluded from unchanged-cache claims'])
doc('summary.json',summary)
artifacts=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file()and p!=OUT/'artifact-manifest.json':
  body=p.read_bytes();artifacts.append(dict(path=str(p.relative_to(OUT)),bytes=len(body),sha256=sha(body)))
doc('artifact-manifest.json',dict(schema=1,artifacts=artifacts))
print('Assembled draft packet',len(artifacts),'artifacts;',len(sources),'sources. Final independent record pending.')
