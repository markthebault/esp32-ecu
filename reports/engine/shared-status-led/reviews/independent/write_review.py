from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
root=Path('/home/mark/persospace/esp32-ecu');own=root/'.cache/engine/shared-led-review';freeze=own/'freeze-005'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((freeze/'manifest.json').read_text());inventory=manifest['sources']
assert all((root/p).is_file()and sha(root/p)==v['sha256']and sha(freeze/p)==v['sha256']for p,v in inventory.items())
functional='''
.gitignore
firmware/include/ecu/status_led.hpp
firmware/include/ecu/board_status.hpp
firmware/include/ecu/flex_hardware.hpp
firmware/include/ecu/switch_acquisition.hpp
firmware/include/ecu/switch_transport.hpp
firmware/include/ecu/switch_service.hpp
firmware/main/switch_service.cpp
firmware/main/espnow.cpp
firmware/main/engine_target.cpp
firmware/main/web_assets.hpp
firmware/platformio.ini
firmware/boards/esp32-s3-44pin-n16r8.json
firmware/sdkconfig.n16r8.defaults
firmware/tests/status_led_test.cpp
firmware/tests/shared_i2c_service_test.cpp
firmware/tests/switch_service_test.cpp
scripts/test_firmware.sh
scripts/tuning_sdkconfig.py
scripts/build_firmware_preserved.py
scripts/check_flex_ingress.py
scripts/embed_web.py
web/index.html
tools/radio_simulator.py
tools/test_status_led_ui.py
hardware/flex-input/architecture.json
hardware/flex-input/README.md
docs/engine-flex-fuel.md
docs/engine-feature-coverage.md
'''.split()
sources={p:inventory[p]['sha256']for p in sorted(functional)}
context={p:v['sha256']for p,v in inventory.items()if p not in sources}
for label in ('portable','legacy','parent-shared','independent'):
 x=json.loads((own/(label+'-003.json')).read_text());assert x['compile']['returncode']==0 and all(r['returncode']==0 and not r['stderr']for r in x['runs'])
for p in ['ui-probe-004.json','build-config-probe-004.json','wrapper-generation-001.json','shared-led-build-004-audit/review.json']:
 assert json.loads((own/p).read_text())['passed'] is True
assert json.loads((own/'fixture-export-003.json').read_text())['returncode']==0
q=json.loads(json.loads((own/'query-clock-002.json').read_text())['stdout']);assert q['fresh']is False and q['ready']is False
build=json.loads((own/'shared-led-build-004-audit/review.json').read_text());assert build['source_receipts_equal']and not build['compiled_input_mismatches_now']
artifacts=['portable-003.json','legacy-003.json','parent-shared-003.json','independent-003.json','fixture-export-003.json','ui-probe-004.json','build-config-probe-004.json','wrapper-generation-001.json','query-clock-001.json','query-clock-002.json','byte-mode-001.json','shared-led-build-004-audit/review.json','side-effects/coverage-side-effect.json','side-effects/platformio-cache-side-effect.json','cjson/manifest.json','independent_shared_service.cpp','query_clock_probe.cpp','byte_mode_probe.cpp','ui_probe.js','build_config_probe.py','wrapper_generation_probe.py','build_receipt_probe.py','freeze-005/manifest.json']
for p in sorted((own/'ui-fixtures-owned-003').glob('*.json')):artifacts.append(str(p.relative_to(own)))
report={
 'accepted':True,'open_findings':[],
 'reviewer':'Independent flex_acquisition_review agent; no child agents',
 'created_utc':datetime.now(timezone.utc).isoformat(),
 'scope':'Shared-I2C MCP23008 status LED software increment, native fault models, source/build/UI evidence, and separate inhibited development profile. No acceptance of a flex target capture producer, protected circuit/CAD, physical timing, electrical/light/CPU-health qualification, or full feature parity.',
 'source_hashes':sources,
 'functional_review_scope':{
  'new_LED_and_shared_bus':'Acquisition/readback state machine, full legal IODIR/IOCON marker, reset/byte-mode checks, shared owner and deadline, SDK error separation, cleanup/retry, coalesced radio requests, cached advisory diagnostics.',
  'existing_switch_context':'Existing transport/acquisition contracts and legacy service behavior reviewed and replayed; no upstream reference execution.',
  'target':'Only new profile/flags, legacy RMT exclusion, GPIO38 input-only init delta and inhibited physical policy. Existing engine_target.cpp is source-bound but its full executor/plant is not requalified here.',
  'UI':'Pure extracted validator independently executed on own actual-service SDK-model captures; parent Chrome script/captures audited and one mobile screenshot inspected. No browser/service started by reviewer.',
  'tools':'Build preservation/SDK normalization and compile guards independently tested with owned fake PIO; final ELF bytes/sections/symbols read only from owned copies. check_flex_ingress.py review is its isolated-sdkconfig option/dependency-freeze delta; previous ingress packet remains historical.',
  'docs':'Final changed allocation, shared bus/advisory scope, unfinished gates and cache-disclosure text reviewed. Existing prior feature claims are not newly requalified.'},
 'freeze_inventory':{'manifest':'freeze-005/manifest.json','sha256':sha(freeze/'manifest.json'),'files':len(inventory),'functional_files':len(sources),'context_hashes':context,'context_is_not_additional_functional_acceptance':True,'originals_and_frozen_copies_match_at_seal':True},
 'independent_validation':{
  'portable_ASan_UBSan_checks':518,'legacy_service_ASan_UBSan_checks':243,
  'shared_service_ASan_UBSan_checks_with_6_exports':2366,'shared_cJSON_allocation_failure_positions':74,
  'independent_actual_service_cases':8,'independent_actual_service_assertions':2188,
  'independent_cases':['partial bus/device allocation','switch-first shared deadline/guard skipping/SDK overrun','cleanup handle retention/retry','LED address-local failure does not cut required switches','mid-read reset/underfill','stale/U64/no diagnostic refresh','10000 concurrent coalesced policy requests with no requester SDK access','Off byte-mode alias regression'],
  'pure_JS_checks':103,'fake_PIO_config_and_flag_checks':86,'generation_and_ELF_checker_controls':17,
  'read_only_final_build_audit_checks':51,
  'final_four_env_build_receipt':'.cache/engine/shared-led-build-004/summary.json',
  'native_commands_and_environment':'Compile/run argument arrays and pre-start GCOV_PREFIX/ASan/UBSan environments are recorded in the referenced *-003.json files; fake-tool commands in build-config-probe-004.json and wrapper-generation-001.json.',
  'reproduce_UI':'node .cache/engine/shared-led-review/ui_probe.js freeze-005 ui-fixtures-owned-003 NEW_ID',
  'reproduce_build_model':'PYTHONDONTWRITEBYTECODE=1 python3 -B .cache/engine/shared-led-review/build_config_probe.py freeze-005 NEW_ID',
  'no_production_or_target_ELF_execution':True,'no_services_started':True,'no_hardware_actions':True},
 'conclusions':{
  'ownership':'Only monitor/switch_service owner calls SDK for either device. Radio request only coalesces enum under publication lock; HTTP reads published caches. A required switch receives first opportunity every tick.',
  'budget':'One original 3ms origin per 5ms tick. LED has no second deadline, needs1ms write/2ms guarded-read slack; SDK timeouts floor remaining integer milliseconds and overrun/clock failure invalidates. Allocation/deletion and scheduling/lock overhead are not hard WCET bounded by this evidence.',
  'failure_isolation':'Address-local LED failure preserves required switch validity/control. A stuck shared bus invalidates required switches. Off monitors a verified zero latch and retains LED ownership; switch Off can release only its own handle without destroying LED bus state.',
  'GP7_and_reset':'LED IODIR is full-byte0; unused GP3..7 NC-low outputs. Switch IODIR0x7f and GP7-to-GP6 challenge remain. OLAT-off precedes output direction; nonzero legal IOCON.ODR=4 prevents all-zero Off/SEQOP alias; full configuration/GPIO/OLAT and trailing IODIR reject reset/mismatch.',
  'diagnostics':'Requested policy and serviced/verified historical latch are distinct; full-width source times/counters are decimal U64 strings. Cached values do not refresh on readers. Reversed query before read completion now cannot be fresh/ready. Strict UI types/own enum strings/U64 tuple/age/fault checks reject inconsistent ready payloads; failed poll clears verified wording. Light output and live CPU health remain unproven.',
  'build':'Final004 has all4 compiler successes, identical before/after compilation source inputs, retained unchanged current default cache, lossless gzip ELF archives and retained generated SDK configs. Own ELF copies verify current full HTML bytes at assets::index in flash rodata for3 web profiles; flex_dev omits legacy RMT symbols and both legacy web profiles retain them.',
  'provenance':'Final29 reviewed source hashes bind84-file owned freeze; no project/SDK/upstream implementation edits by reviewer. Native probes compile frozen source plus copied cJSON. Build evidence uses parent actual Linux compilation, independently audited; compiler/system environment is not claimed hermetic.'},
 'closed_findings':[
  {'id':'off_byte_mode_alias','proof':'byte-mode-001.json','resolution':'Nonuniform legal IOCON=4 marker and explicit init/readback; independent byte_mode case now passes.'},
  {'id':'UI_ready_prototype_and_health_wording','resolution':'Strict explicit enum membership, fault/ready and full-U64 tuple checks, advisory wording and failed-poll clearing;103 independent checks pass.'},
  {'id':'query_before_completed_read','proof_before':'query-clock-001.json','proof_after':'query-clock-002.json','resolution':'Both Acquisition snapshot and JSON publication require now>=completed_us.'},
  {'id':'embedded_UI_stale','resolution':'Regenerated header and current-index flash bytes verified in final004; old001/002 embedded UI is historical.'},
  {'id':'generation_attestation_order','resolution':'Build003 honestly retains source_inputs_unchanged=false (only pre-build generated header changed). Fixed wrapper records pre-generation inputs separately, allows only declared header generation, then captures stable compilation inputs. Final004 stable receipt and owned generator-negative controls pass.'}],
 'remaining_gates':[
  'Actual GPIO38 MCPWM callback/worker, lock/time sampling, post-pop context/generation/arm publication fence and completed-control ACK integration remain unimplemented.',
  'Protected flex input frontend, selected sensor/supply/harness, RGB transistor/LED/resistors, new circuit/CAD/carrier/enclosure fit remain unimplemented or unqualified.',
  'Actual target ISR/WCET/interference/heap/stack, reset/power/back-power/BOOT/PAIR/download, bus electrical and optical/CPU-health behavior require physical validation.',
  'New carrier development build is incompatible with old GPIO38 WS2812 wiring; historical/default profiles keep old ownership. Physical engine outputs remain inhibited; no flashing or physical operation accepted.'],
 'side_effect_disclosures':[
  {'event':'Earlier initial reference review updated16 generated upstream gcda counters before coverage redirection was applied. Exact original record preserved; no restoration attempted. Generated coverage is excluded from unchanged-cache claims. No upstream production executable ran in this increment.','record':'side-effects/coverage-side-effect.json','sha256':sha(own/'side-effects/coverage-side-effect.json')},
  {'event':'Parent first direct PlatformIO build after environment-list edit automatically removed prior generated default caches compact_n16r8_web/compact_a3_web/compact_a3_timing_bench. Prior selected ELF10c99de1593a9114f8ffb7346ba62165a55876599ffa19ce0fb268fcb2ca48c5 was not recovered. Source history/frozen reports retained. Later cache retention applies only to cache present after this deletion; no unchanged-old-cache or byte-identical legacy-ELF claim.','record':'side-effects/platformio-cache-side-effect.json','sha256':sha(own/'side-effects/platformio-cache-side-effect.json')}],
 'artifacts':{p:sha(own/p)for p in artifacts}
}
(own/'review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'accepted':True,'source_files':len(sources),'inventory_files':len(inventory),'sha256':sha(own/'review.json')}))
