#!/usr/bin/env python3
"""Assemble a new immutable SW2 checkpoint, preserving all earlier packets."""
import gzip,hashlib,json,os,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'.cache/engine/switch-inputs';STAGE=C/'publish-stage';OUT=R/'reports/engine/switch-inputs'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')
def cp(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a,b)
def review_projection(source,target):
 omitted=[];included=[]
 for p in sorted(source.rglob('*')):
  if not p.is_file():continue
  rel=p.relative_to(source);data=p.read_bytes()
  skip='__pycache__'in rel.parts or rel.parts[0]=='references' or p.suffix.lower()in('.pdf','.o','.jar','.class') or data.startswith(b'\x7fELF')
  if skip:omitted.append(dict(path=str(rel),sha256=sha(p),bytes=len(data)));continue
  cp(p,target/rel);included.append(str(rel))
 write(target/'publication-projection.json',dict(scope='Projection of original local review; full research cache retained locally',included=included,omitted=omitted,reason='Manufacturer document/page copies and compiled objects/executables are not redistributed; source probes and immutable source bindings remain'))
if OUT.exists()or STAGE.exists():raise SystemExit('Preserve existing output/staging; choose a new explicit assembly path')
# The circuit reviewer supplies a self-contained publication packet.
review_cache=R/'.cache/engine/switch-input-circuit-review'
publication=R/'.cache/engine/switch-input-circuit-review-publication'
if not(publication/'artifact-manifest.json').is_file():raise SystemExit('Wait for the final standalone circuit-review publication packet')
STAGE.mkdir(parents=True)
review_projection(R/'.cache/engine/switch-input-implementation-review',STAGE/'reviews/software')
review_projection(R/'.cache/engine/switch-input-architecture-review',STAGE/'reviews/architecture')
shutil.copytree(publication,STAGE/'reviews/circuit')
paths=set()
for prefix in ('firmware/include','firmware/main','firmware/tests','firmware/components','firmware/boards','web','config','tuning','hardware/switch-inputs'):
 for p in (R/prefix).rglob('*'):
  if p.is_file()and (p.name in ('fp-lib-table','sym-lib-table','LICENSE','NOTICE')or p.suffix in ('.hpp','.h','.cpp','.c','.py','.js','.cjs','.json','.md','.ini','.csv','.sh','.kicad_mod','.kicad_sch','.kicad_pcb','.kicad_pro','.kicad_sym','.html','.txt','.msq'))and '__pycache__'not in p.parts:paths.add(p.relative_to(R))
for prefix in ('scripts','tools'):
 for p in (R/prefix).glob('*'):
  if p.is_file()and p.suffix in ('.py','.cpp','.hpp','.sh','.mjs','.cjs'):paths.add(p.relative_to(R))
for name in ('README.md','firmware/CMakeLists.txt','firmware/platformio.ini','firmware/partitions.csv','firmware/sdkconfig.defaults','firmware/sdkconfig.n16r8.defaults','docs/engine-secondary-tables.md','docs/engine-feature-coverage.md','docs/engine-usb-tuning.md','docs/web-configuration.md','hardware/a5-idle-interface/net_contract.json','hardware/a5-idle-interface/esp32-ecu.kicad_pcb'):
 paths.add(Path(name))
for entry in json.loads((R/'hardware/switch-inputs/footprint-provenance.json').read_text()).values():
 if entry.get('source'):paths.add(Path(entry['source']))
records=[]
for rel in sorted(paths):
 p=R/rel
 if p.is_symlink():raise ValueError('Unexpected source symlink: '+str(rel))
 cp(p,STAGE/'sources'/rel);records.append(dict(path=str(rel),bytes=p.stat().st_size,sha256=sha(p)))
write(STAGE/'source-bindings.json',dict(baseline_commit='b0c39a9daf3334f9ddec0e181ade62aecb10e2f9',scope='SW2 development checkpoint source snapshot; no secondary-enabled engine-plant acceptance',sources=records))
validation=STAGE/'validation'
for a,b in [('cad/final-pour-erc.json','cad/erc.json'),('cad/final-pour-drc.json','cad/drc.json'),('cad/final-copper.svg','cad/copper.svg'),('cad/final-copper.png','cad/copper.png'),('cad/final-schematic/switches.svg','cad/schematic.svg'),('cad/final-schematic/switches.png','cad/schematic.png'),('native-tests.log','native-tests.log'),('python-tests.log','python-tests.log'),('circuit-binding-tests.log','circuit-binding-tests.log'),('ui-run.log','ui-run.log'),('n16r8-final-build.log','n16r8-build.log'),('other-target-builds.log','other-target-builds.log'),('target-policy.log','target-policy.log'),('other-policy.log','other-policy.log'),('other-isr.log','other-isr.log')]:cp(C/a,validation/b)
for a,b in [('ui','ui'),('target','target'),('reference-locator','reference-locator'),('routing-release','routing')]:shutil.copytree(C/a,validation/b)
for environment in ('compact_n16r8_web','compact_a3_web','compact_a3_timing_bench'):
 cp(R/f'firmware/sdkconfig.{environment}',validation/f'target/sdkconfigs/{environment}.txt')
# Retain exact custom circuit vectors compressed, with no proprietary binary.
for p in sorted((C/'circuit-pour-final').rglob('*')):
 if not p.is_file():continue
 rel=p.relative_to(C/'circuit-pour-final');dest=validation/'circuit'/rel
 if p.name=='values.txt':
  dest=dest.with_suffix('.txt.gz');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(gzip.compress(p.read_bytes(),mtime=0))
 else:cp(p,dest)
for name in ('sources.json','dip18-source.json'):cp(C/'reference'/name,validation/'reference-metadata'/name)
cp(Path.home()/'.platformio/packages/framework-espidf/LICENSE',validation/'licenses/esp-idf-LICENSE')
# Record the independent software doc-only delta explicitly.
deltas=json.loads((C/'software-review-delta.json').read_text())
checks=dict(passed=True,physical_qualification=False,secondary_enabled_external_plant_accepted=False,
 new_root_native_checks=dict(acquisition=276,transport=1656,actual_service=243,service_json_allocation_cuts=69),
 python_existing_tests=189,python_circuit_binding_tests=3,secondary_browser_workflows=8,
 circuit_declared_cases=95,circuit_manufacturer_models=False,
 independent_software_assertions=12278,software_review_documentation_delta=deltas,
 target_builds=['compact_n16r8_web','compact_a3_web','compact_a3_timing_bench'],
 physical_policy='Selected/generic web engine outputs compile-time inhibited; separate gated dummy-load build only',
 cad=dict(erc=0,drc=0,unconnected=0,schematic_parity=0),
 open_gates=['Physical protection/reset/backfeed/temperature/supply/harness/fit and actual scheduler/I2C/USB/RF measurements','Fresh secondary-enabled coupled plant comparison against pinned production Speeduino','Wider Speeduino feature gaps and vendor online acceptance'])
write(STAGE/'checks.json',checks)
text="""# Guarded switch inputs: development checkpoint

Target firmware now acquires the two SW2-J4-DRAFT1 contacts, binds coherent source-tagged samples into the controller, latches faults across skipped control observations and exposes bus/wiring diagnostics in the UI. Defaults make no I2C device requests. Source timestamps, readback/challenge checks, measured acceptance budgets and requalification are explicit. Selected web-build engine outputs remain inhibited.

The separate80x60mm THT accessory has a native schematic/routed PCB, candidate BOM, incompatible internal/contact connectors and a reviewed ground-return pour. **HOLD: no fabrication, physical engine, electrical/environmental, thermal or enclosure-fit qualification.** The expander selftest cannot qualify an analog conditioner or prove two-wire continuity. Fresh secondary-enabled coupled engine acceptance remains open.

- [Current hardware/wiring/debug guide](../../../hardware/switch-inputs/README.md)
- [Source bindings](source-bindings.json), [checks](checks.json) and [artifact manifest](artifact-manifest.json)
- [Independent software assessment](reviews/software/assessment.txt) and [review](reviews/software/review.json):12,278 assertions, including actual engine/switch services, skipped observations, reset/budget/fault races and UI provenance.
- [Independent architecture assessment](reviews/architecture/assessment.txt). The circuit review packet is under `reviews/circuit/`, with its own source bindings, manifest and standalone replay.
- [Native schematic](validation/cad/schematic.svg), [copper](validation/cad/copper.svg), [reference locator](validation/reference-locator/assembly.svg). The locator uses an annotation-only export copy; all serialized non-reference tokens and geometry match the unchanged production PCB. It is not a fit/assembly qualification.
- [Circuit results](validation/circuit/results.json):95 conditional ngspice cases and retained custom decks/vectors. Generic transistor/diode/clamp/supervisor assumptions are not manufacturer models. Bus-feed and carrier3V3-feed currents are separate. Steady18V experiments are not input ratings or automotive surge tests.
- Native/full existing Python tests, three additional stale-binding tests, eight installed-Chrome workflows and three Linux target builds passed. Static output-policy/ISR/USB audits do not establish actual timing, heap, stack or physical behavior.

The immutable software review copied the earlier secondary feature guide as context. The sole declared difference is the updated guide describing this implemented path and its prototype/physical gates; accepted software remains byte-identical. Original local review manifests are retained. Their publication projections explicitly list omitted manufacturer document/page copies and compiled executables/objects. The full local research cache remains intact. The circuit review has a separate standalone publication manifest.

Verification is archival by default. Later project changes do not rewrite this checkpoint. From the repository root:

```sh
python3 tools/verify_switch_inputs_evidence.py
python3 tools/verify_switch_inputs_evidence.py --check-live-sources
uv run --with numpy python tools/verify_switch_inputs_evidence.py --replay --ngspice .cache/tools/ngspice-package/payload/usr/bin/ngspice
```

Replay rebuilds frozen portable/actual-service independent probes in a temporary directory. The optional circuit replay requires the recorded ngspice binary and compares all95 result rows. Native KiCad/target builds and hardware measurements are separate operations. Nothing was flashed and no vendor message was sent.
"""
(STAGE/'README.md').write_text(text)
# Keep this exact assembly recipe for review/reproduction.
cp(Path(__file__),STAGE/'validation/publication-recipe.py')
artifacts=[dict(path=str(p.relative_to(STAGE)),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(STAGE.rglob('*'))if p.is_file()]
write(STAGE/'artifact-manifest.json',dict(version=1,scope='Source-bound SW2 development checkpoint; physical and enabled-plant gates remain open',artifacts=artifacts))
subprocess.run(['python3',str(R/'tools/verify_switch_inputs_evidence.py'),'--directory',str(STAGE),'--check-live-sources'],check=True)
OUT.parent.mkdir(parents=True,exist_ok=True);os.rename(STAGE,OUT)
print(json.dumps(dict(published=str(OUT.relative_to(R)),sources=len(records),artifacts=len(artifacts),manifest_sha256=sha(OUT/'artifact-manifest.json'))))
