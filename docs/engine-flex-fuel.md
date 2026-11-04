# Flex-fuel development integration

The shared controller, configuration store, browser, own010 tuning definition and logs now consume the raw-edge flex core. **The protected target producer and a matching PCB input remain missing.** Enabled corrections or an ethanol secondary condition therefore inhibit target control until a qualified target source is implemented. All selected physical engine outputs remain inhibited.

The earlier [production raw-edge groundwork packet](../reports/engine/flex-core/README.md) remains immutable. The [integration evidence](../reports/engine/flex-integration/README.md) adds controller, migration, UI, logger and fixed-gasoline plant checks. Neither establishes ethanol combustion calibration or physical engine operation.

## Acquisition contract

`firmware/include/ecu/flex_fuel.hpp` accepts serialized rising/falling timestamps with an explicit source. It has no GPIO, ISR, queue, NVS or web access and is not safe for concurrent callers. The new [integer ingress](../firmware/include/ecu/flex_ingress.hpp) supplies a64-edge ring, context/time fences and local-suppression decisions for a future target producer. It is not wired to a peripheral. One worker must own the floating-point core. A source name describes origin, not electrical qualification. Target binding must reject synthetic sources.

The default calibration maps 50 Hz to E0 and 150 Hz to E100. Low-pulse width maps 1–5 ms to −40–125°C. Those conventions follow the pinned production [sensor ISR](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/sensors.cpp) and [periodic conversion](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/timers.cpp). They do not select or qualify a purchased sensor or harness pinout.

The core requires eight complete coherent cycles by default, adjustable from 2 to 32. Frequency is derived from the sum of full periods; temperature uses low widths from those same cycles. The calibration uses the complete configured frequency span. A first rising edge cannot establish a valid period or low width. Optional smoothing uses elapsed measurement time, never query count. Its first qualified value initializes the filter directly.

Calibration validation bounds frequency, sensor-fault threshold, tolerance, window size, stale interval and filter time. Default frequency tolerance is 1 Hz with 1 µs timestamp-difference uncertainty. Low width has a 2 µs boundary tolerance. The fault-frequency period threshold rounds conservatively. Values inside tolerance can clamp to the physical range and expose clamp flags. Repeated levels, timestamps that do not increase, a reversed/future query, short edges, invalid widths/frequencies, overflow, source/config changes and stale data invalidate acquisition. A completed sample expires after 250 ms by default even if a newer incomplete edge exists.

Faults carry a generation and remain pending through reacquisition. `observe()` returns the invalid pending sample; `acknowledge(generation)` may clear only the current generation after observation. The host engine adapters ACK only after a completed control observation consumed that invalid sample. The future target worker must follow the same rule. Old tickets cannot clear newer faults. Reconfiguration resets the complete window/filter and preserves fault notification. No initial or held value is silently treated as E0.

## Correction contract and integration requirements

The separate correction helper provides six-bin ethanol fuel percentage, signed spark addition and optional fuel-temperature percentage curves. Defaults are neutral and disabled. Enabled correction requires a valid, fresh, source-tagged coherent sample. Invalid correction returns unknown factors and an explicit reason. Off returns exactly neutral factors without disabling acquisition needed by secondary ETH conditions.

Fuel and optional temperature factors apply separately to ordinary fuel before the independent acceleration reference adder. Zero factors suppress all fuel, including that adder and opening deadtime. Cranking still uses fuel factors but bypasses flex and secondary spark for its fixed angle. Flex spark is added before limiter retard and secondary combination; per-cylinder trims preserve the existing arithmetic, including recovery from a scalar clamp. Hard pulse/dwell/duty limits remain active.

One immutable observation carries its actual capture calibration and producer revision. Control rechecks timestamp/window geometry, calibrated frequency, pulse/high interval, raw conversion and clamp consistency. When smoothing is Off, filtered values must equal raw values. A new configuration invalidates acquisition even when capture calibration is unchanged, preserves clock/fault history and requires reacquisition. Host-only scalar ETH fixtures are explicitly `synthetic_value`: they may select secondary ETH with corrections Off but never qualify as a frequency/temperature capture or enable corrections.

Schema9 requires the complete `flex_fuel` section. Schema1..8 migration always initializes it disabled and neutral, including when parsing into a previously enabled Tune. Schema8 secondary maps survive migration unchanged. Browser controls cover both correction curves, calibration, input confirmation and source/fault/age diagnostics. Confirmation is a configuration assertion, not physical qualification. The current carrier has no released flex connection; do not wire a sensor to an unassigned module pin.

Use [esp32-ecu-flex.ini](../tuning/esp32-ecu-flex.ini), identity `ESP32ECU DEV 010 INHIBITED`. Its8192-byte page preserves all prior offsets and appends160 bytes at7808; its832-byte runtime block preserves the640-byte prefix. MSL007 appends41 flex fields for229 engine /186 direct SIL columns, with U64 counters/timestamps preserved as decimal strings in JSON. The device recorder retains128 rows, with overwrite/gap accounting. Prior256-row retention exceeded linked DRAM after this diagnostic expansion.

Known engine screen schemas1..4 cannot carry flex quality/factors. When flex is required they explicitly suppress the engine frame and retain legacy sensor telemetry; a negotiated flex-capable screen protocol is still needed. No frame is silently extended beyond250 bytes.

The host SIL panel can emit actual synthetic frequency/low-pulse edges. The27-case matrix exercises three strategies, neutral/off controls, endpoint frequencies, enabled fuel/temperature/spark factors, smoothing, zero fuel, missing input and dropout. Its combustion model retains fixed gasoline properties. This tests integration and cut behavior, not ethanol chemistry; the separate pinned production fixture supplies the earlier raw-edge comparisons.

Remaining work includes protected target acquisition/fault ACK, pin/protection/reset design, PCB/case integration, negotiated flex radio fields, ethanol-aware plant calibration, online vendor support and HIL. The target producer must acquire when either corrections or a secondary ETH condition requires it. The software cannot turn the confirmation checkbox into missing target data.

## Source execution and observed differences

[The evidence packet](../reports/engine/flex-core/README.md) retains the source-bound 25 raw-edge cases, exact input/output captures, audits, negative controls and independent review. The fixture executes genuine pinned setup, installed input callbacks, `oneMSInterval` and production loop without injecting ethanol, RPM or synchronization status. A synthetic 60-2 signal produces 2,000 RPM through the real decoder. Our standalone capture/correction helper sees the same changed flex-pin transitions. Own engine scheduling and a running plant are not part of this comparison.

The fixture's virtual pin 2 flex input and pin 19 crank input belong to Speeduino's v0.4 fake-board mapping. They are not ESP32 carrier wiring instructions.

The native experiments expose these differences:

- Before the first one-second tick, neutral reference flex tables queried at E0 return cached zero: at synchronized 2,000 RPM the fixture reports 0% fuel correction, −40° flex addition and no scheduled injector pulse. At the first tick, the values become 100%, 0° and a nonzero pulse. The table-cache initialization mechanism is independently reproduced. This is a conditional native startup finding; real boot timing and physical behavior were not tested.
- With E0/E100 configured at 40/160 Hz, a 100 Hz input becomes E60 in the reference and E50 in our normalized span. The reference subtracts the low endpoint without dividing by span. Standard 50/150 calibration agrees after qualification and reference timing/filter quantization.
- A synthetic 356 Hz robustness input wraps the reference 8-bit one-second count to 100 and produces plausible E50. Our capture reports sensor-fault frequency and keeps corrections invalid. This is an artificial over-frequency test, not a claimed sensor fault waveform or EMI qualification.
- Reference low/high range handling and pulse-width clamping can return E0/E100 or a boundary temperature for an invalid input. Our stricter policy invalidates and latches the fault. Reference filtering also delays and quantizes readings. These are declared policy differences, not numerical equivalence claims.

At 3 ms, our continuous temperature is 42.5°C; production integer nearest rounding reports 43°C. Neutral/changed curves, cold/hot boundaries, one-pulse deadband, dropout, hidden recovery/ACK, disabled corrections with live acquisition, 1 µs phase and loop-refinement controls are retained. Eleven deliberately corrupted records are rejected by the saved-capture auditor.

## Target and hardware constraints

The [FLEX-G38-DRAFT1 draft](../hardware/flex-input/README.md) prefers GPIO38 capture and a separate PDIP18 MCP23008 at0x21 for the ordinary RGB status LED. GPIO0 BOOT/PAIR and GPIO3 idle stay assigned; GPIO45/46 remain NC. [Espressif's boot-mode documentation](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html) requires GPIO46 low/floating when GPIO0 is low for serial download. GPIO45 can select the flash supply unless a verified fuse setting overrides it. This draft avoids reliance on a boot gate and supplier eFuses. It has no circuit or fabrication release. The separate `compact_n16r8_flex_dev` software build now removes all GPIO38 RMT ownership, disables its output and configures it as input, while default/historical builds retain their old LED wiring. Actual GPIO38 capture remains unimplemented.

The new build implements the shared-bus MCP23008 LED service. Required switch acquisition has priority under one3ms transaction deadline; LED verification waits for remaining slack. Nonuniform IOCON readback and trailing IODIR detect byte-mode/reset aliases. The UI distinguishes requested policy, verified or historical latch, source/age and transport faults. Readback is advisory and cannot establish light output or CPU health. A failed LED alone does not add an engine dependency; shared-bus failure still invalidates required switches. Sensor protection, the target owning worker/publication/ACK fences and physical LED/input qualification remain open.

`flex_ingress.hpp` accepts only serialized integer events, with no SDK, GPIO, allocation or floating-point work. The64-slot queue rejects old contexts and timestamps at/before arming. Clock errors, full queues, repeated levels, intervals below50µs and more than32 callbacks in a fixed10ms window discard the queued series and request masking only the flex channel. A fixed window can admit64 callbacks across a boundary; this is not a rolling frequency limit or a measured ISR load bound. The peripheral has no edge FIFO, so even accepted callbacks do not prove every physical edge was captured.

That callback window is per armed episode and excludes foreign/inactive callbacks. It is not a global interrupt budget across arbitrary stop/arm calls. The trusted owner must apply actual local masking and use the ACK/holdoff path for noise recovery, without resetting the ordinary arm window to bypass it.

After popping an event, floating-point work may run outside the lock, but publication must still be fenced. Retain the popped context, fault generation and arm boundary. Atomically revalidate current context/generation/armed state and timestamp against the current arm boundary before committing the result. A mismatch discards it and invalidates/reacquires the separate Capture series. IngressEdge has no generation field; retain the companion snapshot/version. This target-worker publication fence remains unimplemented.

Suppression keeps an exact context/generation fault pending. Diagnostic snapshots cannot offer or ACK it. The worker may offer the invalid sample and ACK only after completed matching control consumption; stale or unoffered tickets fail. Clearing the queue, stopping, rearming and idempotent context requests never acknowledge a fault. Strictly increasing contexts prevent reuse across calibration, tune, source or owner changes. Invalid context reuse and sequence exhaustion are terminal. All ingress calls require the same external lock; the class itself is not concurrent.

Retries require the fault ACK plus a50ms holdoff, then a fresh capture-core window. Masked time is not proof of electrical quiet. Persistent noise receives another bounded attempt and can suppress again. Target code must actually mask/clear only flex status, avoid resyncing the common timer, preserve the producer's real calibration/revision and route faults into the owning capture core. Every stop/rearm or binding change must invalidate that separate floating-point series too; ingress queue clearing alone cannot do so. The ingress cannot verify completed control execution, so the owning worker must bridge both fault tickets only after the same matching invalid evaluation completes. These target obligations remain unimplemented. The native ingress tests feed the actual Capture/Controller to verify unchanged waveform conversion and invalid-control/reacquisition behavior; that harness is not ESP32 acquisition evidence.

The eventual protected input must preserve BOOT/PAIR/reset/download behavior, avoid back-powering, define signal polarity and bias, and retain the physical low-pulse meaning through conditioning. Shared MCPWM capture resources, clock extension, ISR placement/load, bounded queues, overflow, control-consumer ACK and sensor power faults need separate review. Keep the 120×120 mm limit, leaded home-solderable construction, pluggable module and existing sealed-button requirements. No eFuse changes are part of this work.

## Reproduce

The reference builder currently binds the reviewed 32-bit-timer numerical baseline hash recorded in its source. It relinks all 109 original objects byte-for-byte, verifies 565 original inputs before/after, and compiles only the separate entry. It reuses the original timer HAL and 108 original objects. A different numerical baseline/compiler environment requires a fresh audit, rather than silently accepting unrelated cached objects.

```sh
python3 scripts/build_speeduino_flex.py --source ../speeduino
python3 tools/run_flex_scenarios.py --output .cache/engine/NEW-flex-run
python3 tools/check_flex_experiments.py .cache/engine/NEW-flex-run .cache/engine/NEW-flex-checks.json --check-live-sources
CXX=g++ sh scripts/test_firmware.sh
```

Use new output paths. The runner sets an owned coverage prefix before startup; the fixture also confines coverage to its executable directory. Run an owned ELF copy for independent probes. The initial reviewer table-cache probe updated 16 generated upstream `.gcda` counters before that safeguard was applied; the exact files and limitation are disclosed in the packet. Tracked upstream sources and both existing numerical binaries/manifests remain unchanged. Generated coverage counters are excluded from unchanged-cache claims.

Native success does not establish actual ESP32 input acquisition, online TunerStudio support, ethanol combustion chemistry/calibration, target timing, physical electrical/environmental behavior or full Speeduino parity. Those remain open requirements of the project.

For the current software integration, run `PYTHONPATH=tools python3 -B -m unittest test_engine_flex`, `python3 -B tools/run_flex_integration_scenarios.py --output NEW_DIRECTORY` and `python3 -B tools/verify_flex_integration_evidence.py --replay`. The earlier reproduction commands above refer to the separate raw production-reference packet.

For the unwired integer ingress, run `python3 -B scripts/check_flex_ingress.py --output NEW_DIRECTORY --sdkconfig-directory PATH_TO_ISOLATED_BUILD_ENV/config`. It records native sanitizer scenarios, a standalone Xtensa clock/ingress IRAM/DRAM probe and owned flash-pointer/external-call negative controls. It needs the existing pinned PlatformIO toolchain/SDK configuration. It does not run a real interrupt callback or establish target latency. Use `scripts/build_firmware_preserved.py` with a new `.cache` output directory for firmware builds; it retains the default cache and prevents configuration-triggered PlatformIO cleanup from deleting earlier artifacts.
