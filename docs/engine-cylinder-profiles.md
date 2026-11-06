# Cylinder profile development

The shared controller and angle scheduler now have an internal capacity-eight path for one to eight even-fire, four-stroke cylinders. **The public tune, browser, USB definition, coherent telemetry, target executor and PCB still support four cylinders.** This is an intermediate implementation toward broader engine support, not a completed feature release or physical ECU acceptance.

`BasicTune<8>`, `BasicOutput<8>`, `BasicAngleConfig<8>`, `BasicAngleScheduler<8>` and `BasicPhaseDecoder<8>` share the existing control/phase algorithms. The `Expanded...` aliases select them. Existing public aliases retain capacity four, so expanded objects cannot be passed to their older interfaces. Eight independent fuel trim maps and spark offsets, the complete fuel-dose calculation and per-cylinder capacity/clamp masks are available in the expanded core. A failure on cylinder eight inhibits every engine channel and retains bit7 in the cylinder fault mask.

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

Logical8 and9 retain idle and boost. `cylinder_channels.hpp` owns the kind/cylinder conversions. Expanded engine scheduling excludes those auxiliary IDs. The eventual expanded executor needs masks wide enough for this18-ID namespace, explicit pin assignments, independent high-time limits and proven bounded dispatch. Its logical IDs must never be used as indices into the current eight-pin target array.

An initialized scheduler rejects changes to count, order, strategy, wheel slots, angle references or pulse/duty limits. It returns failure and clears its plan; the caller must take the global-low path. An explicit cut/reset fences the old profile before a new one starts. Independent review reproduced an unfenced8→1 change that previously left removed cylinders' edges pending; that failure is retained with the corrected checks.

## Current evidence

The [core packet](../reports/engine/cylinder-core/README.md) records the completed tests and independent review. The reproducible probe is `tools/run_engine_profiles.py`, using a kernel executable from a completed sanitized firmware suite and a separately attested production reference.

The motored fixture covers1..8 cylinders, all three strategies,36/60/120-slot missing-two wheels,500/2000/7500RPM, three closing angles and two orders. It checks every configured injector/coil event count, phase, pulse width, inactive channels, dose conservation, upper-cylinder capacity, stale command expiry and configuration fences. This is prescribed-shaft timing evidence, not a combustion or free-shaft engine result.

Injector low edges retain their committed deadline after opening. With integer-microsecond captures, interval quantization can project across a long pulse. The test records actual errors and uses a bound derived independently from the imposed shaft, one-microsecond interval error and pulse plus missing-tooth-gap horizon. It retains a separate0.55° spark phase gate. Neither bound establishes physical capture accuracy or interrupt latency.

The completed1296-case fixture measured maximum spark phase error0.07° and maximum injector phase error2.115°. Injector timing therefore does not have a demonstrated sub-degree bound in this fixture. The full sanitized firmware suite, three public-format boundary tests, thirteen tuning tests and three fresh inhibited target builds pass. Static ISR placement, compiled engine-output inhibition and exclusive binary-USB ownership checks pass for those builds; no target was connected or flashed.

The four-cylinder before/after probe uses exact F64 word output across7776 controller observations, including three strategies, primary load/AFR/transient modes and injected faults. Its baseline is commit `cdbd534a25a3e5594292f9bc65ae6d91a1897b8a`. This checks the declared unchanged path; it does not establish every possible tune.

The genuine Speeduino reference remains pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. The new probe reuses108 attested production objects, verifies an exact original relink, writes configuration through production storage and runs unchanged `setup()`. It records24 requested/effective configurations and the actual schedule angles. It does not generate shaft events, observe sixteen GPIOs or run an engine plant.

The reference changes requested wasted-COP to wasted spark for1/2/3/5/7 cylinders, and changes some requested injector layouts. Seven-cylinder sequential schedules use integer102° increments, whereas evenly spaced four-stroke geometry is720/7°. Its two-cylinder sequential fuel schedule has a180° second-channel offset while ignition has360°. These are observed configuration/geometry differences requiring investigation in the generalized plant, not demonstrated physical engine bugs. Relevant primary code: [ignition controller](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/scheduler_ignition_controller.cpp) and [fuel controller](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/scheduler_fuel_controller.cpp).

The old native v0.4 fixture aliases injector6 and coil4 at pin50 and does not define sixteen independent outputs. Its four-cylinder benchmark remains a historical four-cylinder result. A broader event comparison needs an explicit native pin fixture and real production IO reinitialization, with its differences disclosed.

## Remaining integration

1. Add a versioned public engine-profile model, complete import/migration and whole-tune validation, browser profile/order/trim editors, TunerStudio storage/runtime definitions and debugging. Retain old identities and files. Current schemas1..10 and own011 explicitly reject other cylinder counts.
2. Expand coherent observations, raw/MSL logs, timing traces and authenticated ESP-NOW screen telemetry without truncating cylinders or reinterpreting old payloads. Expose logical counts, channel kinds and board capacity separately.
3. Extend the target executor, auxiliary arbitration and ISR budget for the complete channel namespace. Measure timing, memory, capture/flash/USB/RF load and fault response on actual hardware before physical output authorization.
4. Generalize both reduced-order and external research plants: cylinder TDCs, charge/valve events, total and per-cylinder displacement, all actuator states, ledgers and physical order. Run independent plants against both actual controllers with normal/fault/refinement cases, checking the reference's effective modes. Existing four-cylinder plants cannot certify another cylinder count.
5. Define and route a matching protected driver/input allocation within the120mm/THT/pluggable-module constraints. The present PCB has four injector and four coil commands. Extra cylinders require reviewed extra channels or an explicit banking/coil topology, connector/current/thermal/protection work and enclosure updates. Bridging existing outputs or doubling driver loads is not authorized by this logical model.

All engine outputs remain inhibited. Other OEM triggers, VR conditioning, VVT, knock, staging, supported TunerStudio online operation and physical/environmental qualification remain part of the unfinished wider goal.
