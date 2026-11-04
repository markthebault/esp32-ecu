from pathlib import Path
import ast,datetime,hashlib,json,subprocess,shutil
R=Path('/home/mark/persospace/esp32-ecu');S=R.parent/'speeduino';O=Path(__file__).resolve().parent;F=O/'final-freeze-003';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((F/'.cache/engine/speeduino-flex-sim/build-manifest.json').read_text());matrix=json.loads((F/'parent-matrix/summary.json').read_text());execution=json.loads((O/'execution-003/independent-execution-review.json').read_text());parentchecker=json.loads((O/'frozen-parent-checker-review-003.json').read_text());initial=json.loads((O/'source-review-binding.json').read_text());side=json.loads((O/'coverage-side-effect.json').read_text())
source_paths=[*matrix['sources'],'docs/engine-flex-fuel.md','docs/engine-feature-coverage.md','scripts/test_firmware.sh','tools/verify_flex_core_evidence.py'];source_hashes={p:sha(F/p) for p in source_paths};assert len(source_hashes)==10 and all(sha(R/p)==h for p,h in source_hashes.items())
ast.parse((F/'tools/verify_flex_core_evidence.py').read_text());syntax=subprocess.run(['sh','-n',str(F/'scripts/test_firmware.sh')],capture_output=True,text=True);assert syntax.returncode==0 and not syntax.stderr
original_stable=all(sha(Path(p))==h for p,h in m['locked_original_input_hashes'].items());object_stable=all(sha(Path(p))==h for p,h in m['object_hashes'].items());reference={p:sha(S/p)==h for p,h in initial['source_sha256'].items()};numerical={p:sha(R/p)==h for p,h in initial['numerical_fixtures'].items()};tracked_clean=subprocess.run(['git','diff','--quiet','HEAD','--','speeduino','lib'],cwd=S).returncode==0
assert original_stable and object_stable and all(reference.values()) and all(numerical.values()) and tracked_clean
assert sha(R/'.cache/engine/speeduino-flex-sim/numerical-reference-relink')==m['base_binary_sha256']
shutil.copy2(O/'execution-003/independent-execution-review.json',O/'execution-review-003.json')
log=R/'.cache/engine/flex-core/firmware-tests-gcc-001.log';text=log.read_text();assert 'flex_fuel_checks 509' in text and '"actual_service_checks":243' in text
result={
 'accepted':True,'open_findings':[],
 'scope':'Portable raw-edge acquisition/window/filter/fault-ACK and separate six-bin correction groundwork, plus genuine pinned native production raw-edge fixture and saved-capture audit only',
 'source_hashes':source_hashes,'reviewed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'core_review':{
  'parent_checks':509,'independent_checks':2101,'boundary_checks':21382,'strict_CXX14_ASan_UBSan':True,'test_results_sha256':sha(O/'core-test-results-002.json'),
  'stale_completed_sample_ready_defect':'Found independently before freeze001, fixed and regression verified.',
  'query_reversal_precedence':'Single TimeReversed classification verified.',
  'reviewed_contracts':['coherent unequal rolling windows2/8/32','timestamp0,32-bit crossing and nearUINT64_MAX','source/config and filter history reset','malformed/unavailable edges and full reacquisition','hidden faults remain pending until exact observed generation ACK','unobserved/superseded ACK tickets denied','query-independent filtering and freshness','whole-us frequency-boundary uncertainty and conservative sensor-fault threshold','neutral defaults/Off, enabled fresh sample and six-bin factor bounds'],
  'not_dynamically_exhausted':'2^64 event/fault/config counters; guards reviewed in source.'},
 'production_execution_review':{
  'accepted':True,'actual_cases_reexecuted':25,'actual_snapshots_replayed':sum(x['snapshots'] for x in execution['cases']),'all_parent_stdout_byte_identical':True,
  'independent_assertion_checks_including_expected_negative_rejections':execution['independent_assertions'],'independently_generated_raw_stimulus_bytes_match_all25':True,
  'independent_expected_oracles':['changed raw levels/callback counts','one-second window plus modulo256 counter','reference low-pass filters and nearest-integer temperature conversion','source tags, completed-cycle windows and start/end/age timestamps','normalized ethanol and low-width temperature','six-bin correction factors and disabled neutrality','explicit invalid reason/pending/inhibition','startup cache,356Hz alias,40..160Hz span, dropout deadline and exact generation ACK'],
  'no_production_ethanol_RPM_or_sync_status_injection':True,'all_execution_sources_stable':True,'raw_fixture_binary_sha256':m['binary_sha256'],
  'owned_ELF_copy':str(F/'.cache/engine/speeduino-flex-sim/speeduino-flex-sim'),'owned_GCOV_PREFIX_before_startup':execution['GCOV_PREFIX_before_startup'],'GCOV_PREFIX_STRIP':'0',
  'execution_result_sha256':sha(O/'execution-review-003.json'),'execution_script_sha256':sha(O/'execute-review-003.py')},
 'controls':{'neutral_vs_ramp_same_stimulus_causal':True,'query_refinement':True,'phase1us':True,'parent_frozen_checker_replayed':True,'parent_corruptions_rejected':len(parentchecker['mutations']),'additional_independent_corruptions_rejected':execution['independent_rejected_corruptions']},
 'observed_native_differences':{
  'startup':'At synced2000RPM before1s, neutral production E0 cache reports fuel0/spark-40/advance-30/pulse0; at1s fuel100/spark0/advance10/pulse5445. Own core ready160ms yields neutral100/0. Native fixture finding only.',
  'counter_wrap':'Raw356Hz gives production one-second uint8 count100 and plausible E50; own correction remains invalid with sensor_fault_frequency.',
  'custom_span':'40..160Hz endpoints with100Hz input yield productionE60 and ownE50.',
  'temperature':'3ms low width yields own42.5C and production43C via DIV_ROUND_NEAREST. Earlier reviewer truncation wording was corrected, original note retained.',
  'invalid_policy':'Own pending-fault inhibition intentionally differs from production filtered-zero/range/temperature clamping.'},
 'provenance':{
  'speeduino_sha':m['speeduino_sha'],'unit_test':False,'original_inputs_before_after_verified':565,'original_objects_reused':108,'final_objects_verified':109,
  'exact109_object_numerical_relink_sha256':m['numerical_relink_sha256'],'original_inputs_stable_after_review':original_stable,'final_objects_stable_after_review':object_stable,
  'reviewed_reference_source_hashes_unchanged':reference,'original_numerical_binary_manifest_hashes_unchanged':numerical,'external_tracked_speeduino_lib_clean':tracked_clean,
  'native_limitations':['32-bit native software timers with single-thread virtual HAL','tick-before-input then loop convention','zero CPU cost; no AVR/ESP32 register/vector/ISR timing emulation','original60s virtual clock bound','synthetic raw pin transitions; no physical sensor or output execution'],
  'generated_coverage_excluded_from_unchanged_cache_claims':True},
 'documentation_and_harness':{
  'accepted_in_scope':True,'no_claim_objections':True,'harness_change':'Only appends flex_fuel to existing native sanitizer loop.','sh_syntax_checked':True,
  'guide_final_delta_reviewed':'Explicitly labels virtual pin2/pin19 as fake-board fixture mapping, not ESP32 wiring.',
  'parent_full_harness_log_reviewed':str(log.relative_to(R)),'parent_full_harness_log_sha256':sha(log),'parent_full_harness_execution_independently_repeated':False,
  'reason_no_repeat':'Parent supplied complete passed CXX=g++ harness log; this review independently executed scoped core/boundary and all25 raw cases.',
  'verifier_static_audit_accepted':True,'verifier_python_syntax_checked':True,'assembled_archive_replay_performed':False,
  'packaging_note':'Parent will run final assembled artifact/source/saved-audit/sanitizer verifier before publishing; this is a separate packaging check.'},
 'coverage_side_effect_disclosure':{
  'occurred':True,'cause':'Earlier reviewer table-cache probe linked upstream instrumented archives and unintentionally flushed16 preexisting generated .gcda counters at exit before prefix isolation was applied.',
  'exact_record':'coverage-side-effect.json','exact_record_sha256':sha(O/'coverage-side-effect.json'),'generated_file_count':len(side['generated_files_touched']),'generated_files':side['generated_files_touched'],
  'restoration_or_reset_attempted':False,'tracked_production_sources_changed':False,'original_numerical_binaries_manifests_changed':False,
  'excluded_from_all_unchanged_generated_cache_claims':True,'subsequent_production_runs_owned_ELF_and_prefix_before_startup':True,
  'external_and_parent_generated_coverage_unchanged_during_final25_replays':execution['generated_coverage_unchanged_by_these_replays']},
 'out_of_scope_open_work':['engine Tune and correction ordering integration','target GPIO/timer/ISR/bounded queue/consumer ACK integration','config/schema/default/import migration and whole-tune persistence','browser/TunerStudio/runtime/log/radio/debug integration','pin ownership/protected input/BOOT-reset-download behavior and PCB/connector/enclosure','coupled own running-engine plant/fuel chemistry/calibration','physical HIL/electrical/environmental/vehicle qualification','supported online TunerStudio and full Speeduino parity'],
 'physical_qualification':False,'full_flex_integration':False,'full_speeduino_parity':False}
assert all(sha(R/p)==h for p,h in source_hashes.items())
(O/'independent-review.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'accepted':True,'open_findings':[],'source_files':len(source_hashes),'cases_reexecuted':25,'snapshots':result['production_execution_review']['actual_snapshots_replayed'],'assertion_checks':execution['independent_assertions'],'independent_review':str(O/'independent-review.json')},indent=2))
