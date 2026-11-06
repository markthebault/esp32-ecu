from pathlib import Path
import csv,gzip,hashlib,io,json,shutil,subprocess,tarfile

ROOT=Path(__file__).resolve().parents[3]
CACHE=Path(__file__).resolve().parent
OUT=ROOT/'reports/engine/secondary-integration'
assert not OUT.exists(),'Choose a new packet; do not overwrite published evidence'
OUT.mkdir(parents=True)
def digest(body):return hashlib.sha256(body).hexdigest()
def copy(source,relative):
 destination=OUT/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(Path(source).read_bytes());return destination
def write(relative,value):
 p=OUT/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2)+'\n')
def review(name,source):
 original=source/'artifact-manifest.json';manifest=json.loads(original.read_text())
 entries={e['path']:e for e in manifest['artifacts']} if 'artifacts' in manifest else manifest['files']
 copy(original,f'reviews/{name}/original-artifact-manifest.json');selected=[];excluded=[];stream=io.BytesIO()
 with gzip.GzipFile(fileobj=stream,mode='wb',filename='',mtime=0) as compressed:
  with tarfile.open(fileobj=compressed,mode='w|') as archive:
   for rel,entry in sorted(entries.items()):
    body=(source/rel).read_bytes();assert len(body)==entry['bytes'] and digest(body)==entry['sha256'],rel
    if body.startswith(b'\x7fELF'):
     excluded.append(dict(original_path=rel,reason='Compiled local ELF/object; source/build receipts retained'));continue
    member=tarfile.TarInfo(rel);member.size=len(body);member.mode=0o644;member.mtime=0;archive.addfile(member,io.BytesIO(body));selected.append(dict(original_path=rel,bytes=len(body),sha256=digest(body)))
 (OUT/f'reviews/{name}/inputs-and-probes.tar.gz').write_bytes(stream.getvalue())
 write(f'reviews/{name}/selection.json',dict(included=selected,excluded=excluded))
 for filename in ('review.json','review.md','assessment.md','final-source-bindings.json','source-bindings.json','software-readme-delta.json','receipt-probe.json'):
  if (source/filename).is_file():copy(source/filename,f'reviews/{name}/{filename}')
 return dict(name=name,manifest_sha256=digest(original.read_bytes()),included_artifacts=len(selected),excluded_local_elf_objects=len(excluded),implementation_acceptance=name=='software')

reviews=[review('contract',ROOT/'.cache/engine/secondary-integration-contract-review'),review('software',ROOT/'.cache/engine/secondary-software-review'),review('documentation',ROOT/'.cache/engine/secondary-documentation-review')]
binding=json.loads((ROOT/'.cache/engine/secondary-software-review/final-source-bindings.json').read_text())['files']
doc_binding=json.loads((ROOT/'.cache/engine/secondary-documentation-review/source-bindings.json').read_text())
assert doc_binding['all_software_source_deltas']==['tuning/README.md']
paths=set(binding)
paths.update(subprocess.check_output(['git','ls-files','--','firmware/tests'],cwd=ROOT,text=True).splitlines())
paths.add('tuning/README.md')
paths.update(['.gitattributes','tools/verify_secondary_integration_evidence.py','docs/engine-development.md','docs/engine-feature-coverage.md','docs/engine-load-model.md','docs/engine-observability.md','docs/engine-secondary-tables.md','docs/engine-usb-tuning.md','docs/espnow-engine.md'])
sources=[]
for rel in sorted(paths):
 body=(ROOT/rel).read_bytes()
 if rel=='tuning/README.md':assert digest(body)==doc_binding['software_source_delta']['new_sha256'] and binding[rel]['sha256']==doc_binding['software_source_delta']['old_sha256']
 elif rel in binding:assert digest(body)==binding[rel]['sha256'],('Reviewed live source differs',rel)
 snapshot='source-metadata/root.gitattributes' if rel=='.gitattributes' else 'sources/'+rel
 copy(ROOT/rel,snapshot);sources.append(dict(path=rel,snapshot=snapshot,bytes=len(body),sha256=digest(body)))

historical=[]
for before,after in [('config/engine/defaults.json','config/engine/defaults-v7.json'),('firmware/include/ecu/tuning_layout.hpp','tuning/archive/own008_tuning_layout.hpp'),('tuning/protocol-layout.json','tuning/protocol-layout-load.json'),('tuning/esp32-ecu-load.ini','tuning/esp32-ecu-load.ini')]:
 body=subprocess.check_output(['git','show','f3b049eb695dadbadc7ff382547e572ecf03e695:'+before],cwd=ROOT);assert body==(ROOT/after).read_bytes();rel='before/'+before;p=OUT/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body);historical.append(dict(before=rel,after=after,baseline_path=before,baseline_commit='f3b049eb695dadbadc7ff382547e572ecf03e695',sha256=digest(body)))
write('validation/historical-records.json',historical)
logs={'native-tests-final.log':'native-tests-final.log','python-tests-final-rerun.log':'python-tests-final.log','target-build-final.log':'target-build-final.log','ui-final.log':'secondary-ui-final.log','browser-regressions-final.log':'browser-diagnostics/first-regression.log','browser-regressions-final-rerun.log':'browser-diagnostics/second-regression.log','browser-regressions-final-remaining.log':'browser-regressions-final-remaining.log'}
for src,dst in logs.items():copy(CACHE/src,'validation/'+dst)
for name in ('application-checks.json','browser-summary.json','generator-check.json','legacy-disabled-check.json','legacy-disabled-observations.csv.gz'):copy(CACHE/name,'validation/'+name)
browser_reports=[]
for name in ('secondary','tuning','load','transient','semi','cylinder','engine_observability'):
 folder=CACHE/('ui' if name=='secondary' else 'browser-'+name)
 for p in sorted(folder.rglob('*')):
  if p.is_file():copy(p,'browser/'+name+'/'+str(p.relative_to(folder)))
 browser_reports.append('browser/'+name+'/ui-tests.json')
for p in sorted((CACHE/'target').rglob('*')):
 if p.is_file() and not p.read_bytes().startswith(b'\x7fELF'):
  copy(p,'target/'+str(p.relative_to(CACHE/'target')))
for env in ('compact_n16r8_web','compact_a3_web','compact_a3_timing_bench'):
 for name,source in [('sdkconfig',ROOT/'firmware'/('sdkconfig.'+env)),('partitions.bin',ROOT/'firmware/.pio/build'/env/'partitions.bin')]:copy(source,'target/environment/'+env+'/'+name)
for name in ('application-tune.json','application009.msq','expected-page.bin','application-page.bin','expected-edited-page.bin','engine188.msl','direct145.msl','prepare-log-fixtures.py','start-ts.py','start-ts-accepted.py','start-mlv.py'):copy(CACHE/name,'applications/'+name)
copy(ROOT/'tuning/examples/tunerstudio-secondary-roundtrip.msq','applications/tunerstudio-secondary-roundtrip.msq')
copy(ROOT/'tuning/esp32-ecu-secondary.ini','applications/esp32-ecu-secondary.ini')
copy(CACHE/'ts-accepted/msq-check.json','applications/ts/msq-check.json')
for name in ('fuel-rule-edited.png','spark-rule-edited.png','fuel-map-current.png','spark-map-current.png','application.log'):copy(CACHE/'ts-accepted'/name,'applications/ts/'+name)
copy(CACHE/'ts-accepted/user/TunerStudioProjects/TunerStudioAppDebug.txt','applications/ts/TunerStudioAppDebug.txt')
for name in ('engine188.png','direct145.png','application.log'):copy(CACHE/'mlv'/name,'applications/mlv/'+name)
copy(CACHE/'publish.py','validation/publish.py')
receipt=max((CACHE/'replays').glob('*/replay.json'),key=lambda p:p.stat().st_mtime)
copy(receipt,'validation/frozen-replay/replay.json')
for p in receipt.parent.glob('*.log'):copy(p,'validation/frozen-replay/'+p.name)
copy(CACHE/'frozen-replay-final.log','validation/frozen-replay/verification.log')
legacy=json.loads((CACHE/'legacy-disabled-check.json').read_text())
summary=dict(scope='secondary_software_integration',baseline_commit='f3b049eb695dadbadc7ff382547e572ecf03e695',speeduino_reference='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20',operator_configurable=True,secondary_feature_complete=False,protected_switch_target=False,secondary_enabled_external_plant=False,online_tunerstudio=False,physical_qualification=False,schema_version=8,identity='ESP32ECU DEV 009 INHIBITED',page_bytes=8192,runtime_bytes=640,radio_schema=4,radio_frame_bytes=250,engine_log_fields=188,direct_sil_log_fields=145,document_limit_bytes=49152,engine_nvs=dict(offset=0x210000,bytes=131072),tests=dict(python=189,secondary=738,engine_secondary=148,native_sanitizers=True,browser_workflows=57,independent_review_groups=14,independent_frozen_sources=299),disabled_observations_sha256=legacy['sha256'],browser_reports=browser_reports,reviews=reviews,sources=sources,remaining=['Protected J4 switch accessory, bounded acquisition/readback and physical electrical/fit validation','Fresh enabled-table external-plant comparison across project dispatchers and production Speeduino timer models','Own009 online vendor acceptance and physical target RAM/stack/storage/USB/RF/timing tests','Wider Speeduino feature parity and engine/vehicle qualification'])
write('summary.json',summary)
summary['tests']['frozen_native_replay']=True
write('summary.json',summary)
(OUT/'README.md').write_text('''# Secondary-table software integration

Schema8/own009 adds both secondary-table editors and strict whole-tune migration/staging/CAS,640-byte coherent runtime,188/145-field MSL006 and compact authenticated radio schema4. Physical engine/idle outputs remain inhibited in the selected web targets. Protected switch/ethanol acquisition and fresh secondary-enabled coupled plant acceptance remain open.

Validation includes the native ASan/UBSan suite,189 Python tests,57 Chrome workflows, three firmware builds and static policy/ISR/USB audits. The7776-row disabled probe exactly matches the earlier core packet. These regressions do not substitute for new enabled-table plant trajectories.

TunerStudio MS Lite3.3.01 opens the definition without parser/unit warnings; edits to both rules/maps match all8192 expected page bytes with the known revision37 explicitly supplied because the application omits its read-only origin. MegaLogViewer HD Lite4.6.14 opens/plots188/145-field synthetic probe files. NaN-bearing channel extrema may displayNaN; calculated vendor channels/large integers remain unqualified. No online vendor acceptance or physical board test is claimed.

The independent software review passes14 groups against299 frozen inputs, including7772 burn-allocation and5747 migration-allocation failures,324 old-prefix profiles,297 native/browser observations,193 exact runtime extensions,225 radio combinations,864 unit assertions and strict rejection/nonmutation checks. Its null-metadata finding and sensor-fallback wording recommendation are closed. The separate contract review is a proposed-layout/capacity assessment, not final implementation acceptance.

- [Software review](reviews/software/review.md) and [detailed checks](reviews/software/review.json).
- [Supplemental documentation review](reviews/documentation/review.md) binds the sole post-freeze tuning README correction and independently checks the operator guides/application receipts. The original503-artifact software packet remains unchanged; all production hashes still match it.
- [Contract assessment](reviews/contract/assessment.md).
- [Application receipts](validation/application-checks.json), [browser receipts](validation/browser-summary.json) and [source/limit summary](summary.json).
- [Current guide](../../../docs/engine-secondary-tables.md) and [coverage ledger](../../../docs/engine-feature-coverage.md).

The document bound grows to48KiB and engine NVS to128KiB at the same0x210000 offset. Startup detects an old partition layout without erasing it and blocks saves with a diagnostic. Physical flashing/migration, fragmentation and power-loss durability remain hardware work. No PCB, BOM, Gerber, case or manual release is changed by this packet.

The root artifact manifest binds every file except itself. Sources retain their exact bytes; root attributes are stored inertly outside the source tree. Each reviewer archive contains a selection of its original manifest entries, with sources/probes/commands/results and explicit local binary exclusions. Compiler ELF hashes and generated partition/config records are retained; local full ELF/application binaries remain in the ignored build workspace.

~~~sh
python3 tools/verify_secondary_integration_evidence.py
python3 tools/verify_secondary_integration_evidence.py --check-live-sources --check-index
python3 tools/verify_secondary_integration_evidence.py --replay
~~~

Default verification is archival. Live/index checks intentionally fail after later changes. Replay rebuilds the frozen core/allocation probes with sanitizers and repeats the exact disabled observations in a new ignored directory. Other reviewer/application checks retain their own source/command receipts. The broader goal remains active.
''')
artifacts=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file():body=p.read_bytes();artifacts.append(dict(path=str(p.relative_to(OUT)),bytes=len(body),sha256=digest(body)))
write('artifact-manifest.json',dict(scope=summary['scope'],artifacts=artifacts))
print(json.dumps(dict(artifacts=len(artifacts),sources=len(sources),bytes=sum(e['bytes'] for e in artifacts),reviews=reviews),indent=2))
