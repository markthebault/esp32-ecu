# Semi-sequential development strategy

Four-cylinder semi-sequential injection is now selectable alongside batch/wasted and full sequential. The controller, native and target dispatcher, JSON configuration, browser, own006 tuning page, offline MSQ and negotiated screen telemetry share the same mode. This closes one feature gap. [The coverage ledger](engine-feature-coverage.md) retains the other missing capabilities and physical acceptance work.

## Fuel, phase and channel contract

`semi_sequential_4cyl` is strategy code2. Each injector opens once per crank revolution, twice per four-stroke cycle. Each opening supplies half the effective four-stroke fuel, then adds the full battery-dependent deadtime. Duty is measured against one revolution. The existing15 ms injector,3.5 ms coil and whole-command capacity limits remain. No automatic fuel clipping or per-pair capacity exception was added.

Pairs come from firing-order slots1+3 and2+4. For1-3-4-2, physical cylinders1+4 and3+2 share exact scheduled rising/falling timestamps, while the groups are180° apart. Four smart coils run wasted COP. Four independent injector low-side drivers remain separate: J9 pins1–4 connect cylinders1–4, pins5–8 are returns, with J19 the dedicated power return. J10 pins1–4 remain smart-coil commands1–4 and pin5 ground. Never bridge outputs or put two injectors on one driver. Pairs can overlap above50% duty; peak supply/return current is not assumed to halve. No PCB revision is needed for this logical mode; actual electrical qualification is still missing.

The saved closing reference0..719° repeats modulo360 in this mode.540° therefore means180° each revolution. The browser derives pairs and normalized reference from editor settings, separately from the active configuration. Crank synchronization is required; compression phase and a cam signal are not. Stray cam edges do not create a cam-phase fault, while common capture age/overflow/quiet-input rules remain. Individual cylinder trims require full sequential. A mode change with trims enabled rejects atomically; explicitly disabling trims retains their stored values.

An initial pulse must fit at full width or skip to the next cycle. Once an injector opens, its low deadline is fixed; actual closing angle can move during acceleration/deceleration. Coil advance remains latched at dwell start, with bounded angle correction and high time. Saving fences plans and cuts virtual output state; selecting semi cannot erase an existing latched fault. Recovery still requires a fresh stopped command and quiet inputs.

## Configuration, debugging and files

JSON schema5 and signature `ESP32ECU DEV 006 INHIBITED` gate the new enum. The4992-byte complete tuning page,256-byte live block and all offsets remain; strategy is U32 at272 and live strategy at92. [Current INI](../tuning/esp32-ecu-semi.ini), [protocol layout](../tuning/protocol-layout.json) and [application-authored fixture](../tuning/examples/tunerstudio-semi-roundtrip.msq) are included. Historical defaults-v4, INI005 and older fixtures remain exact records. JSON4→5 preserves idle, trims, timing and revision in RAM, leaving stored bytes unchanged until Save. Earlier schemas keep their disabled-idle migration. Old MSQ identities reject enum2. Whole-tune validation, stable origin metadata and stale-editor CAS remain atomic.

Check active strategy, crank sync, phase-required status, proposed widths/duty, actual timing trace, current/last fault, revision and source age. The browser includes a J9/J10 strategy wiring/debug guide. Its host plant has independent fixed1-3-4-2 physical geometry; editing the tune does not alter that engine. Synthetic SIL logs now identify their strategy in metadata. Bounded engine logs already retain strategy code2 and timing fault17. The [screen protocol](espnow-engine.md) negotiates schema2; legacy schema1 peers continue receiving sensors; ECU peer diagnostics report upgrade-needed whenever the current mode or current/last fault is unrepresentable. The legacy sensor frames and capability-reply status do not gain a new upgrade status field. The232-byte radio frame still contains base scalar proposals, not executed edges or per-cylinder applied values.

TunerStudio MS Lite3.3.01 loaded own006, displayed semi-sequential, and saved a closing-reference edit540→535.5°. The native importer and browser accept the result. MegaLogViewer HD Lite4.6.14 opened/plotted the final48-field synthetic SIL log. These are offline file checks. TunerStudio online still rejects our own identity in the earlier test; no impersonation, vendor contact, physical USB connection or flashing was performed.

## Simulation and independent review

[Evidence](../reports/engine/semi-sequential/) contains28 coupled scenario runs plus8 step-refinement runs,8 legacy warm-start regressions, native/sanitizer tests, Chrome workflows, application files, three firmware build/audit records and independent storage, telemetry and execution reviews. Each real controller drives its own copy of the hash-verified external Modelica MVEM air path plus local empirical fuel/combustion/free shaft through executed electrical edges. It is uncalibrated, with zero CPU/IRQ execution cost. The16-bit reference is a4 µs equality timer model, not AVR emulation. Step refinement also changes production reference loop cadence, so it is not isolated solver convergence.

The pinned Speeduino production source is `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. Its new declared timed profile reads back configured/effective injection layout1/1, timing1, pairing0, two squirts,360° span, two primary schedules and wasted-COP2 after production setup. Previous untimed baseline evidence is preserved. Native Speeduino pairing1+3/2+4 maps through the explicit canonical adapter to physical1+4/3+2. [Production pairing source](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/scheduler_fuel_controller.cpp) and [fuel calculations](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/fuel_calcs.cpp) remain unchanged.

The neutral warm profile settles near919.5 RPM for our target and916.7 RPM for the reference; throttle-step final-second means are2869.7 and2868.9 RPM. These are model observations, not base tunes or a ranking of ECUs. Both injector pairs match exactly in each complete trace, ledgers close within declared tolerances, and all virtual outputs finish low. The largest selected refinement difference is0.033%. Constant-shaft sanitizer tests cover all6 firing orders,36/60/120 slots,1000/8000 RPM and7 closing references, with252 pair/width/phase cases. Integer tooth timestamps cause finite angular error; neither exact timing nor physical jitter is claimed.

Two limitations remain explicit. The35 Nm load step cannot be sustained and stalls. Abrupt deceleration would require excessive dwell, so our target cuts with `invalid_angle_plan`/`dwell_limit` and recovers only stopped. Separately, trigger-loss runs execute four already predicted rises before the watchdog, with the last edge16.38 ms after the last accepted crank. These particular runs have a20 ms timeout; the general decoder timeout is `clamp(period*(missing+2)*2,20ms,150ms)`. A200 RPM test covers the longer40 ms case. Loss detection is not instantaneous. Reference closing-angle error can grow sharply during stall; complete edge/angle traces retain that behavior.

The first audit incorrectly applied target-only fault expectations to the portable runtime and assumed no starts immediately after the last raw tooth. Initial results are retained. The corrected audit checks exact scenario/cause outcomes and actual accepted-crank deadlines, with no relaxation of output limits. Independent reviewers reproduced the conservative dwell cut and bounded post-loss behavior.

Selected N16R8 and generic web images retain inhibited physical engine/idle policy. The separate dummy-load bench environment remains explicitly gated and was not installed. Static IRAM/USB/source checks do not establish physical timing, minimum heap, stack margin, engine operation, vehicle electrical protection, EMI, temperature, splash resistance or fit. Existing A5/IAC driver, loaded RUN/GPIO, module/eFuse, passive-part, valve and enclosure holds remain open.

## Reproduction

Use new output directories to preserve published evidence:

```sh
CXX=g++ sh scripts/test_firmware.sh
uv run --with playwright --with fmpy==0.3.26 python -m unittest discover -s tools -p 'test_*.py'
uv run --with fmpy==0.3.26 python tools/run_semi_scenarios.py --output-dir NEW_MATRIX
uv run --with playwright python tools/test_semi_ui.py --report-dir NEW_BROWSER_CHECK
pio run -d firmware -e compact_n16r8_web -e compact_a3_web -e compact_a3_timing_bench
python3 tools/verify_semi_evidence.py
```

The research FMU and external pinned Speeduino source/dependencies must be built as described in [benchmark setup](engine-research-benchmark.md). No physical target is required for these software checks, and none is qualified by them.
