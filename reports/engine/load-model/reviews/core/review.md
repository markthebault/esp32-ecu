# Independent load/AFR core implementation review

Baseline HEAD: `1d6a9acb34838ea175f2dfa7ccd9786e96d2d11b`.
Reviewed uncommitted source was frozen before probing. Initial, boundary-fixed, binding/lambda-fixed, and final AFR-epoch bytes remain in separate snapshot directories and manifests. Final reviewed core bytes are under `epoch-snapshot/`. All reviewer writes and builds are confined to this cache directory.

## Result

Two concrete findings were reported and fixed by root. A separate restart-epoch edge was resolved through an explicit conservative AFR-only policy. Re-probes pass. No remaining medium/high core blocker was identified in the reviewed bytes and exercised paths. This is a scoped core/native JSON review, not approval of the full ECU or the concurrently changing tuning/UI/radio/simulator integrations.

### Fixed finding1: valid lambda boundary can cut fuel and spark

Original location: `load_model.hpp:afr_factor`, strict double range check against the exact F32 endpoint. A flat valid lambda table containing1.2f at MAP71.355kPa and RPM3250.95 produces interpolated1.200000047683716, slightly above the stored endpoint1.2000000476837158. Measured or Off mode returnedNaN and then Capacity64, cutting all proposed fuel/spark. Target mode continued legacy fuel arithmetic but incorrectly reported invalid_configuration and cleared ArithmeticValid.

The independent99,999-coordinate sweep found1,997 such residues/failures before the fix. Root now qualifies finite bounded target values at the declared F32 precision while preserving the original double value for all actual fuel math. Off mode no longer requires an unused target. The same sweep still observes1,997 harmless interpolation residues and now has0 faults or invalid load reasons. Root's exact fractional-coordinate regression covers all3 AFR modes. Evidence: `boundary_probe.cpp`, `boundary-probe-before.txt`, `boundary-probe-after.txt`, `boundary-probe-final.txt`. Initial/fixed snapshots retain both versions. Severity: high functional correctness for the proposed engine core; physical outputs remain inhibited.

### Fixed finding2: required J16 failure still advertised qualified inputs

Original location: `engine_binding.hpp:bind_inputs` omitted active required auxiliary conversion/confirmation/unit from `in.sensors_valid`. The core correctly produced BadSensor4 and required_emap_unavailable, but the target's RuntimeSample InputsQualified flag remained true and binding text still said physical inputs converted. Confirmed unconfirmed calibration, wrong unit, Voltage mode and open input as4 independent negatives.

Root now includes required J16 conversion/unit/confirmation/range and a specific EMAP/baro reason in binding qualification. The same4 cases have sensors_valid0, aux_qualified0, BadSensor4, and InputsQualified0 after the fix; valid EMAP remains accepted. Unused aux is nonblocking. Evidence: `binding_probe.cpp`, `binding-probe.csv` and `binding-probe-after.csv`. Severity: medium debugging/integration correctness; no actuator-cut bypass was observed.

### Resolved edge: restart during an unrelated sensor fault

The initial shared ASE/AFR epoch remained old after500ms of fresh decoded RPM0 with a sensor fault, followed by recovery at1000RPM without an accepted qualified stopped sample. Measured AFR resumed immediately. This inherited existing ASE state behavior rather than changing historical default fueling. RPM0 alone is also not physical stop proof, so blindly resetting the historical engine epoch on every fault would be wrong.

Root added separate `afr_running_`/`afr_started_`. A fresh possible stopped/cranking observation invalidates only the measured-AFR epoch, even during an unrelated fault; the next qualified noncranking step starts its delay. Continuous-rotation faults retain the epoch. Stale/future acquisition timestamps cannot request this reset. This policy deliberately treats low/zero decoded RPM as a possible restart; it does not authorize baro capture, executor-latch recovery, or claim raw-quiet/physical rest. Historical ASE fields and arithmetic remain unchanged.

Independent ASan/UBSan probe covers6 variants: fresh RPM0, ADCage20001µs, continuous1000RPM fault, fresh cranking200RPM, future timestamp, and age20000µs boundary. Only the fresh possible restart variants restart AFR delay. ASE value is identical across all6. Evidence: initial `restart_probe.cpp`/text, final `epoch_policy_probe.cpp`/text and source manifests. Holding exactly the cranking threshold can conservatively keep measured AFR neutral even if the main state hysteresis still says running; this follows the stated possible-cranking policy.

## Independent verification

`verify_review.py` rebuilds from `epoch-snapshot/`, never from moving production files. Exact compiler commands and results are in `verify-review-result.json`. Compiler: Ubuntu GCC15.2.0. Sanitized builds use C++17, O1, debug information, frame pointers, ASan+UBSan, and `-fno-pie -no-pie`; no clang assumption is required.

| Probe | Result and scope |
| --- | --- |
| Frozen default computation oracle | All324 rows byte-identical to frozen1d6a9ac, including nonflat maps, physical cylinder trims and all3 strategies. SHA256 `ebd0b027addb18b8f975643be0ef116a72b3c03081428a6dcdf72c21126cac8c`. |
| Fractional lambda boundary |99,999 coordinates,0 post-fix unexpected cases; harmless F64 residues remain unrounded in fuel math. |
| Independent composition oracle |5,184 affine-surface combinations under ASan/UBSan: independent fuel/spark/lambda/trim sources, all3 pressure and AFR modes, trims on/off, EGO requirement on/off. Expectations derive from physical coordinate/factor equations, not production lookup. |
| Root's focused tests from frozen bytes | load_model_test and engine_load_test both pass under ASan/UBSan. Includes zero/reference-adder fuel, independent source coordinates, optional MAP, known NA overpressure, role conflict, boundary and AFR start transitions. |
| Required J16 binding | Valid profile passes; unconfirmed, wrong unit, Voltage and open input all correctly cut and clear overall target qualification after fix. |
| AFR possible-restart policy |6 independent freshness/fault/ASE cases pass under ASan/UBSan. |
| Native JSON and adapters |96 cases pass across host engine_bridge and target_timing_bridge: frozen parser fixtures, schemas1..6 valid/VE0/VE120.001, canonical migration, new metadata rejection, MAP-less Alpha-N, optional inactive lambda source, EGO dependency,125% pressure-ratio coordinate, missing EMAP, coefficient0, and warm/not-ready/out-of-range measured AFR behavior. |

AFRoff+EGOdisabled can now leave an unavailable independent lambda coordinate unknown and still apply factor1. EGOenabled retains its lambda-table source dependency. MAP remains required for physical pressure multiplication, ratio coordinates, MAP transient enrichment, and active MAP-indexed tables. Native JSON probes confirm unavailable MAP/target fields serialize as null and clear appropriate input availability; no invented100kPa sensor input was observed.

A direct native caller can still send contradictory quality assertions, for example sensors_valid=true alongside aux_pressure_qualified=false. The native core cuts correctly and load_reason identifies the missing required EMAP, while the synthetic global InputsQualified flag echoes the caller's sensors_valid assertion. The real target binding now resolves this correctly. Treat this as a low-priority host diagnostic contract issue if global qualification is expected to be derived in every adapter; it is not a remaining target binding/cut bypass. The probe result records this distinction rather than treating that flag alone as proof of qualification.

Native sizes are recorded in `native-memory.json`. These do not prove ESP32 heap, task stack, radio coexistence, allocation-failure handling, or flash persistence behavior. The112KiB recorder budget is an explicit change and requires the root's final target allocation/frame audit.

## Review boundaries

Read: load_model.hpp, load_json.hpp, engine.hpp, engine_json.hpp, engine_binding.hpp, optional-MAP transient change, RuntimeSample/JSON propagation, native engine and target-dispatcher bridges, and the relevant target observe/binding call. Snapshots include transitive headers for reproducible builds, not an implied fresh review of every unrelated header.

No new external reference contact, hardware operation, service restart, source modification, or child agent was performed. Pending own008 tuning, full logging, UI, ESP-NOW schema3 and new simulator adapter work are excluded from this core verdict. Native adapter tests exercise supplied inputs/command observations, not a new closed-loop reference-versus-ours plant comparison or actual electrical execution. No engine, boost, car, EMI/surge, thermal, splash, fit or physical qualification claim is made.

Before final publication, obtain integration review and actual app/simulation acceptance for the completed increment. Keep secondary fuel/spark tables, separate baro correction and simultaneous extra pressure hardware support explicitly open as already agreed.
