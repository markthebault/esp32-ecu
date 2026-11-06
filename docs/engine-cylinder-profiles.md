# Cylinder profile development

The development branch now carries one to eight even-fire, four-stroke cylinders through the shared controller, virtual target executor, configuration, browser, own012 tuning files, coherent logs and authenticated screen schema7. **The PCB still has four injector and four coil commands.** Cylinders5–8 have no allocated physical outputs. All normal firmware builds inhibit engine outputs; the separate dummy-load policy rejects profiles above its fitted four-cylinder capacity.

This is a software integration checkpoint toward the wider Speeduino goal. A [separate sixteen-output production-reference fixture](engine-reference-profiles.md) supports generalized naturally aspirated comparisons. [Turbo geometry and native project coupling](engine-turbo-profiles.md) now accept1..8 cylinders; matched turbo hardware/maps, expanded genuine boost comparisons, further feature gaps and physical qualification remain unfinished.

Public `Tune`, `Output`, `AngleConfig`, `AngleScheduler` and `PhaseDecoder` now select capacity eight. Explicit `Legacy...` aliases preserve the capacity-four types. A capacity fault on any cylinder inhibits every engine channel and retains that cylinder's identifying bit.

## Configuration and observations

- Tune schema11 stores eight firing-order positions, eight6×6 fuel maps and eight spark offsets. Only the selected1..8 cylinders participate; unused order positions are zero. Inactive calibration stays saved when the count shrinks.
- The browser exposes active cylinder editors and a phase/channel/connector table. Save requires a complete valid order, all stored calibration and the existing revision CAS. Imported file origin never silently replaces the loaded editor revision.
- Historical JSON schemas1..10 and own001..011 retain their original four-cylinder/specification bounds before migration. Added maps are neutral100%, with axes copied from the first existing trim map; added spark offsets and order positions are zero. Stored files are preserved until an explicit successful save.
- Schema11 allows25..12000cc total displacement and25..5000cc/min injector flow. Pulse, duty, dwell, sensor and whole-engine capacity limits still apply. These ranges are software validation bounds, not supported physical engine calibrations.
- [Own012](../tuning/esp32-ecu-profiles.ini) retains the12288-byte page and1152-byte runtime. Its223 constants append C5–8 calibration after the historical prefix. Runtime adds proposal/worker counts, fitted capacities, full32-bit command masks and C5–8 proposals. [Machine layout](../config/engine-profile.json).
- Coherent data schema3 carries all eight rows, per-cylinder validity/clamp masks, logical IDs, fitted4+4 capacity and separate proposal/earlier-worker counts. Worker count0 means no known command; it is never inferred from the new tune. Inactive or unavailable numeric values remain null/NaN.
- Engine MSL009 has265 columns. Direct-SIL009 has245, adding all eight cylinder proposals to its older202-column prefix. Browser/native files preserve unknowns and full masks.
- [Screen schema7](../config/engine-radio-v7.json) requires authenticated BASE250/FLEX232/BOOST144/CYLINDERS236 datagrams from one immutable observation. No partial observation can be acknowledged or displayed. Full masks must match the BASE low-byte prefix. Schemas1..6 withhold incompatible current counts or earlier wider worker contexts, while compatible four-cylinder bytes and sensor fallback remain unchanged.

## Current integration evidence

The [public-profile packet](../reports/engine/cylinder-profiles/README.md) records native/CAS/migration tests,48 coupled count/strategy plant runs, Chrome, actual TunerStudio/MegaLogViewer checks, fresh inhibited builds and independent reviews. The full Speeduino goal is still active.

The later [production-reference comparison](engine-reference-profiles.md) observes sixteen actual native GPIOs and couples both controllers to independent copies of the same declared physical engine. It records effective setup/event modes, explicit incompatible fallbacks, fault runs, fixed-geometry wrong-wiring controls and numerical refinement. The earlier setup-only probe below remains historical geometry evidence. This new fixture does not change the fitted PCB or establish target timing.

Both the quick regression plant and separately built MVEM air path executed1..8 cylinders in all three modes. Declared physical geometry controls TDCs, intake-close events, actuator arrays, total/per-cylinder volume and trapped air. Geometry remains fixed in wrong-order/reference tests. A30-degree reference error outside the configured cam window produces no phase lock, sparks or combustion work; no recorded spark error in that case is an unavailable measurement. These are empirical, uncalibrated research plants. The profile FMU preserves the older adapter/FMU and verifies actual initialized cylinder/displacement parameters.

The exact historical quick-plant state replay and78,001 external four-cylinder state/ledger comparisons remain unchanged. Independent checks also cover actual FMI cylinder/per-cylinder displacement, airflow invariance at fixed total displacement,1/7/8-cylinder step refinement, cylinder8 alongside the idle channel and conservation ledgers. Earlier expanded-turbo guards rejected an air path without declared matching geometry. The later turbo composition now binds that geometry and retains explicit source-map/hardware limits.

Unmodified TunerStudio3.3.01 opened own012 offline and saved actual C8 fuel/spark edits. Its222 saved constants plus the explicit caller origin reconstruct all223 constants and the entire12288-byte expected page. MegaLogViewerHD4.6.14 plotted C8 values/counts/capacities and mask131072 from both009 log formats. This does not establish supported online onboarding. The latest observed online rejection remains own011; own012 online acceptance is unverified. The known calculated-AFR/unknown-lambda caveat remains.

Three fresh Linux builds and static ISR/output-policy/USB checks pass. The selected flex-development image is1,834,560 bytes inside its2MiB app partition. The linked128-row recorder is104,536 bytes in internal DRAM, within the explicit112KiB source budget; the maximum-width native MSL header uses5,582/6,144 bytes. Linked fit and formatting do not measure runtime heap/stack, interrupt latency, flash/RF load or electrical behavior. No device was flashed.

## Timing and channels

An order starts with cylinder1, contains each configured cylinder exactly once, and leaves unused fixed-array positions zero. Compression TDCs follow the order at `720/N` degrees. The scheduler keeps fractional angles, including seven-cylinder spacing, until it calculates integer-microsecond deadlines.

- Sequential fuel and spark use one event per cylinder per720° and require validated cam phase.
- Batch injection opens every injector together once per360°. Each opening carries half the full-cycle fuel dose plus its own dead time.
- Semi-sequential injection uses each cylinder's closing reference modulo360°, also with two half-dose openings per720°.
- Nonsequential ignition uses a dedicated command for each cylinder once per360°. Only even cylinder counts have opposing compression phases that coincide modulo360°. Odd counts must not be described or wired as opposing-cylinder pairs.

These are logical cylinder commands. A paired coil, a bank of injectors and a dedicated COP output are different electrical topologies.

| Cylinder | Injector logical ID | Coil logical ID | Existing PCB channel |
| --- | --- | --- | --- |
| 1 | 0 | 4 | J9/J10 channel1 |
| 2 | 1 | 5 | J9/J10 channel2 |
| 3 | 2 | 6 | J9/J10 channel3 |
| 4 | 3 | 7 | J9/J10 channel4 |
| 5 | 10 | 14 | No mapping or driver |
| 6 | 11 | 15 | No mapping or driver |
| 7 | 12 | 16 | No mapping or driver |
| 8 | 13 | 17 | No mapping or driver |

Logical8 and9 retain idle and boost. `cylinder_channels.hpp` owns the kind/cylinder conversions. Expanded engine scheduling excludes those auxiliary IDs. The virtual executor uses32-bit masks across this18-ID namespace and separate injector/coil high-time limits. Its physical writer independently bounds the current eight-pin target array. A sanitized executed-event test exercises all16 engine commands, including10ms INJ5–8 pulses beyond the3.5ms coil limit, and a global-low cut. Explicit extra pin/driver assignments and physical timing remain unfinished.

An initialized scheduler rejects changes to count, order, strategy, wheel slots, angle references or pulse/duty limits. It returns failure and clears its plan; the caller must take the global-low path. An explicit cut/reset fences the old profile before a new one starts. Independent review reproduced an unfenced8→1 change that previously left removed cylinders' edges pending; that failure is retained with the corrected checks.

## Earlier core evidence

The earlier [core packet](../reports/engine/cylinder-core/README.md) records the completed tests and independent review. The reproducible probe is `tools/run_engine_profiles.py`, using a kernel executable from a completed sanitized firmware suite and a separately attested production reference.

The motored fixture covers1..8 cylinders, all three strategies,36/60/120-slot missing-two wheels,500/2000/7500RPM, three closing angles and two orders. It checks every configured injector/coil event count, phase, pulse width, inactive channels, dose conservation, upper-cylinder capacity, stale command expiry and configuration fences. This is prescribed-shaft timing evidence, not a combustion or free-shaft engine result.

Injector low edges retain their committed deadline after opening. With integer-microsecond captures, interval quantization can project across a long pulse. The test records actual errors and uses a bound derived independently from the imposed shaft, one-microsecond interval error and pulse plus missing-tooth-gap horizon. It retains a separate0.55° spark phase gate. Neither bound establishes physical capture accuracy or interrupt latency.

At the earlier core checkpoint, the completed1296-case fixture measured maximum spark phase error0.07° and maximum injector phase error2.115°. Injector timing therefore does not have a demonstrated sub-degree bound in this fixture. The full sanitized firmware suite, three public-format boundary tests, thirteen tuning tests and three fresh inhibited target builds pass. Static ISR placement, compiled engine-output inhibition and exclusive binary-USB ownership checks pass for those builds; no target was connected or flashed.

The four-cylinder before/after probe uses exact F64 word output across7776 controller observations, including three strategies, primary load/AFR/transient modes and injected faults. Its baseline is commit `cdbd534a25a3e5594292f9bc65ae6d91a1897b8a`. This checks the declared unchanged path; it does not establish every possible tune.

The genuine Speeduino reference remains pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. The earlier geometry-only probe reuses108 attested production objects, verifies an exact original relink, writes configuration through production storage and runs unchanged `setup()`. It records24 requested/effective configurations and the actual schedule angles. That earlier probe does not generate shaft events, observe sixteen GPIOs or run an engine plant; the separate expanded fixture above now does.

The reference changes requested wasted-COP to wasted spark for1/2/3/5/7 cylinders, and changes some requested injector layouts. Seven-cylinder sequential schedules use integer102° increments, whereas evenly spaced four-stroke geometry is720/7°. Its two-cylinder sequential fuel schedule has a180° second-channel offset while ignition has360°. These are observed configuration/geometry differences requiring investigation in the generalized plant, not demonstrated physical engine bugs. Relevant primary code: [ignition controller](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/scheduler_ignition_controller.cpp) and [fuel controller](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/scheduler_fuel_controller.cpp).

The old native v0.4 fixture aliases injector6 and coil4 at pin50 and does not define sixteen independent outputs. Its four-cylinder benchmark remains a historical four-cylinder result. The separate expanded event fixture uses explicit pin bindings and real production IO reinitialization, with its differences disclosed.

## Remaining integration

1. Extend the declared production-reference comparison beyond its fixed500cc/cylinder,60-2/Hall, neutral-correction research fixture. Keep unsupported2/7-cylinder non-sequential fallback geometry explicit; additional configurations need their own evidence.
2. Complete matched turbo/map hypotheses and expanded genuine-reference normal/fault/refinement comparisons. The generalized gas path and project1/7/8-cylinder evidence do not relabel the historical four-cylinder Speeduino turbo benchmark as eight-cylinder evidence.
3. Measure target heap/stack, timing, capture/flash/USB/RF load and fault response on actual inhibited hardware and dummy loads. No source or CAD check supplies these measurements.
4. Define and route a matching protected driver/input allocation within the120mm/THT/pluggable-module constraints. Extra cylinders need reviewed channels or an explicit banking/coil topology, connector/current/thermal/protection work and enclosure updates. Bridging existing outputs or doubling driver loads is not authorized by this logical model.
5. Complete supported TunerStudio online integration and the wider trigger, VR, VVT, knock, staging and debugging/configuration/UI gaps in the [feature ledger](engine-feature-coverage.md).

All engine outputs remain inhibited. Physical car, electrical, EMI/surge, thermal, splash, RF and printed-fit qualification remain undone.
