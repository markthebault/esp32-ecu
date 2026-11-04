#!/usr/bin/env python3
"""Freeze the independent source audit alongside actual production-loop probes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
UPSTREAM=ROOT.parent/'speeduino'

source_paths={
 'reference':['speeduino/secondaryTables.cpp','speeduino/load_source.h','speeduino/units.h','speeduino/init.cpp','speeduino/speeduino.ino','speeduino/sensors.cpp','speeduino/sensors.h','speeduino/config_pages.h','speeduino/statuses.h','speeduino/fuel_calcs.cpp','speeduino/scheduler_fuel_controller.cpp','speeduino/scheduler_ignition_controller.cpp','speeduino/corrections.cpp','speeduino/board_native.h','speeduino/board_native.cpp','speeduino/table3d.h','speeduino/table3d_axes.h','speeduino/src/pins/pinMapping.cpp'],
 'project':['firmware/include/ecu/secondary_tables.hpp','firmware/include/ecu/load_model.hpp','firmware/include/ecu/engine.hpp','firmware/include/ecu/switch_acquisition.hpp','firmware/include/ecu/switch_transport.hpp','firmware/main/switch_service.cpp','firmware/main/app.cpp','tools/compare_engine_controllers.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp','tools/speeduino_runtime.py','scripts/build_speeduino_sim.py'],
}
hashes={}
for owner,paths in source_paths.items():
 for name in paths:
  src=(UPSTREAM if owner=='reference' else ROOT)/name
  dest=OUT/'sources'/owner/name
  dest.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(src,dest)
  hashes[owner+'/'+name]=hashlib.sha256(src.read_bytes()).hexdigest()

review={
 'scope':'Independent design/source contract review and native production-loop diagnostic probes. Fresh secondary-enabled coupled external-plant implementation has not yet been reviewed or accepted in this packet.',
 'project_head':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
 'speeduino_head':subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip(),
 'historical_evidence_not_new_acceptance':['342 isolated function/interpolation/corrections checks','7776 secondary-disabled regression rows'],
 'source_hashes':hashes,
 'production_contract':[
  {'id':'selection','source':'reference/speeduino/secondaryTables.cpp:15-146','detail':'Fuel and spark use independent config10 modes, source, condition and digitalRead pins. Conditions use strict greater-than. Native input mode reads raw GPIO on every production main-loop secondary evaluation; no debounce, validity, acquisition timestamp or stale-input policy exists here.'},
  {'id':'units','source':'reference/speeduino/load_source.h:35-50; reference/speeduino/sensors.cpp:523-550; reference/speeduino/table3d_axes.h','detail':'TPS status is physical percent*2, TPS table lookup getLoad is status*2, and common load table domain factor is2. Map/ratio raw table axes=physical coordinate/2; TPS raw table axes=physical percent*2. Conditional TPS threshold=physical percent*2, not percent*4. RPM raw axis=RPM/100. Ratio coordinate=floor(100*MAP/EMAP) before upstream table interpolation.'},
  {'id':'spark_order','source':'reference/speeduino/speeduino.ino:95-102,361-368; reference/speeduino/secondaryTables.cpp:105-146; reference/speeduino/corrections.cpp:1319-1346','detail':'Primary advance is already correctionsIgn(primary lookup). Multiply/add compose that corrected advance. Switched production spark invokes correctionsIgn on the secondary lookup again; UNIT_TEST suppresses that second correction invocation and is unsuitable for acceptance.'},
  {'id':'spark_bounds','source':'reference/speeduino/units.h:150; reference/speeduino/secondaryTables.cpp:77-89,117-133','detail':'Secondary spark cells are byte raw=physical value+40, so representable multiplier interval is0..215%. Project216..255% multipliers have no raw reference equivalent. Reference final advance is int8 -128..127; project domain is -5..40. Spark multiplier diagnostic advance2 is percent-127 clipped to int8, not multiplier percent or a direct advance.'},
  {'id':'cranking','source':'reference/speeduino/speeduino.ino:361-387; reference/speeduino/secondaryTables.cpp:101-114','detail':'Fixed timing or rotationStatus Cranking bypasses secondary spark. Secondary evaluation occurs before loop refreshes rotationStatus from RPM, so crank/run transitions may carry the previous loop rotation state. Project hysteresis/order differs; compare stable crank/run states and characterize crossings.'},
  {'id':'fuel_rounding','source':'reference/speeduino/secondaryTables.cpp:46-75; reference/speeduino/maths.h:143-164,318-321','detail':'Reference VE is u8; multiply uses rounded integer percentage and clamps255, addition clamps255. Project F64 interpolation/composition is intentionally retained. Example actual loop VE85*150%=128 versus project127.5 is expected quantization, not failed parity.'},
  {'id':'zero_and_capacity','source':'reference/speeduino/fuel_calcs.cpp:124-159,161-169,247-261; project/firmware/include/ecu/engine.hpp:275-305','detail':'Reference includes opening time when VE=0 and corrections nonzero, and limits running pulse to configured PW duty cap. Project ordinary zero fuel suppresses openings; transient add_reference may separately deliver fuel. Project one-channel capacity excess inhibits all engine channels. These policies must be characterized independently rather than forced equal.'},
  {'id':'trims','source':'reference/speeduino/scheduler_fuel_controller.cpp:296-304; reference/speeduino/scheduler_ignition_controller.cpp:590-638; project/firmware/include/ecu/engine.hpp:284-302','detail':'Reference fuel trims apply to the full limited pulse including injector opening time. Project trims fuel mass before opening split/deadtime/capacity. Reference individual spark trims follow composed current.advance; project offsets precede base bounds/retard/multiply/add. Multiply+nonzero spark trim is not equivalent. Trim load continues to follow primary fuel source in both ECUs when representable.'},
  {'id':'native_pin_limit','source':'reference/speeduino/board_native.h:39-42; reference/speeduino/init.cpp:271-272; probe-results.json:unrepresentable_native_pins,input_independence','detail':'Actual native BOARD_MAX_IO_PINS is20 despite Mega GPIO mappings elsewhere. Raw secondary pins30/31 persist but fail production mapping and both resolve0; raw14/15 resolve distinctly in the pinned production setup. Exact raw/resolved/mode/polarity readback and pin uniqueness are mandatory.'},
  {'id':'reference_cadence','source':'project/tools/speeduino_sim.cpp:220-232,252; project/tools/compare_engine_controllers.py:151-175,189-209','detail':'sensors only writes virtual ADC; it does not run loop. Production loop runs every adaptive advance and tooth/input command. With250/125us plant steps, reference main-loop opportunities differ from project1ms sample/update cadence. A status queried immediately after writing sensors reflects prior production sensor processing. Report sampled stimulus and actual status separately.'},
 ],
 'asynchronous_acquisition_invariants':[
  'Use actual portable Acquisition state machine with Synthetic provenance. No JSON or fixture setting may claim TargetProtected.',
  'Split plant integration at operation issue/completion and independent GPIO-stimulus times. Expose a transaction only at ended_us; observed_us remains started_us and cannot be refreshed by write-only operations.',
  'Do not call Acquisition.next while an operation is pending: that latches fatal Internal. Complete the owned token first, with monotonic same-epoch times.',
  'Declare the GPIO sampling instant within each read. A sample may be latched at read start and conservatively timestamped there; do not silently label completion-time data with an earlier timestamp.',
  'Drive reference GPIO from the independent physical-level schedule. Never feed project qualified/active/pending state into digitalRead.',
  'ACK only the exact pending fault_id from the invalid snapshot passed to a completed core observation. Good recovery reads cannot clear a skipped fault; ACK invalidates readiness until a new guarded read.',
  'Assert injected transport faults actually overlap issued operations and increment the expected fault counters. A fault window between operations is otherwise vacuous.',
  'During producer pause the core must invalidate age>20ms independently of resumed acquisition. Resume must expose PollGap/retry/invalid-observation ACK/new read/debounce before control recovery.',
  'Target app synchronously executes switch_service::tick then observe in its5ms task. An async producer with1ms core sampling is a synthetic timing fixture, not measured target task blocking/RTOS timing.'
 ],
 'minimum_fresh_matrix':[
  'Secondary Off replay with nondefault stored metadata/cells: identical project actuator sequence and plant state against baseline for both project dispatchers.',
  'Neutral Multiply100 and Add0 with active flags checked, plus nonneutral perturbations that change delivered fuel/spark and external plant ledgers; do not accept flags alone.',
  'Independent fuel and spark Off/Multiply/Add/Conditional/Input; at least one meaningful fuel-only, spark-only and simultaneous case; both native32 and native16 timer models.',
  'Nonconstant independent secondary MAP/TPS/ratio maps and axes, with exact raw write/readback and represented physical axes. Include independent fuel-vs-spark source choices.',
  'Conditional RPM/MAP/TPS threshold crossing both directions, plateau at representable threshold and selection status. Independent free-shaft trajectories may cross at different times; do not compare against a shared active-state timeline.',
  'Input channels: all four raw GPIO pairs, independent fuel/spark timing, opposite polarity, shared channel with separate debounce, initial qualification, stable switch, bounce and slow transitions.',
  'Acquisition unavailable/error, stale/producer pause, recovery, fault-ID skipped-observer protection, no source timestamp refresh on writes; all-output-low/cut and source age/reason observations.',
  'Sequential trimmed cases with source-bound known fuel/spark ordering differences; primary trim-source preservation under secondary source changes.',
  'Zero fuel, saturated VE, valid high-demand and capacity fault/recovery with explicit divergent reference/project policies and executed actuator-edge assertions.',
  'Selected half-step250->125us runs preserve qualitative selection/fault behavior and show convergence in physical timing/plant metrics; disclose native loop-cadence change.',
  'Negative controls: wrong represented units, polarity/channel, table perturbation, suppressed acquisition completion/ACK or direct commanded-fuel shortcut must fail targeted assertions.'
 ],
 'unsupported_or_characterized':[
  'Production-reference ethanol acquisition unless actual flex sensor GPIO interrupt and timer update path is implemented; direct currentStatus assignment is not producer validation.',
  'Physical MCP23008/I2C accessory behavior, electrical protection, target CPU/IRQ/RTOS timing or real-engine calibration.',
  'Exact cross-ECU plant trajectory equality under independent quantization, control cadence, scheduler phase acquisition, trim/capacity/fault policy differences.',
  'Spark switch-transition error against last sampled production advance: current harness reference error is not event-latched demand. Treat those spikes as observer limitation or add a truthful schedule/event-latched observer.',
  'TPS/ratio cylinder-trim mapping through existing wrapper unless it translates source units; current cylinder_trims maps raw load asMAP/2.',
 ],
 'fair_acceptance':[
  'Only executed actuator GPIO edges deliver plant fuel and sparks. Never use commanded VE, PW, advance or expected selection to drive the plant.',
  'Each ECU owns its ResearchPlant, shaft/trigger/sensor history and control/scheduler state. Equal exogenous load/throttle/GPIO schedule is allowed; shared endogenous traces are not.',
  'Use each ECU own reported production/core values to check its declared semantic bounds and selection; do not call copied secondary math as the passing oracle.',
  'Require finite physical ledgers, channel bounds, no duplicate/misordered edges, no post-cut scheduled rises, explicit bounded trailing in-flight pulses where policy allows, and all outputs low after termination.',
  'State whether an assertion proves equivalence, project safety policy, reference behavior, negative-control sensitivity or numerical convergence. Passing counts cannot combine historical isolated checks with fresh coupled scenarios.',
  'Bind reports to project/source hashes, unchanged pinned upstream SHA, no UNIT_TEST, exact writer/readbacks, timer HAL details and immutable scenario/tune fixtures.'
 ],
 'probe_summary':{
  'scope':'Independent native32 actual production setup/loop diagnostics with fixed tooth input; not coupled plant evidence',
  'results_file':'probe-results.json','build_file':'probe-build.json','runner':'run_contract_probes.py',
  'results':['pins14/15 independent; pins30/31 collapse to0 because native max20','TPS raw20 equals threshold20: primary; TPS raw21: secondary','running1000rpm: VE85*150 ->128; spark10*150 ->15; advance2 diagnostic23','running1000rpm zeroVE: actual reference900us openings','cranking200rpm: secondary fuel active, secondary spark bypassed at5deg','running1000rpm fuel85+250 clamps255; spark10-40=-30 (wider than project domain)']
 }
}
(OUT/'assessment.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps(dict(path=str(OUT/'assessment.json'),sources=len(hashes),scope=review['scope']),indent=2))
