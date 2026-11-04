# Flex-fuel acquisition and correction groundwork

The portable raw-edge core and a separate genuine production-reference fixture are implemented. **Flex fuel is not yet connected to the engine controller, target input, configuration store, browser, TunerStudio definition or PCB.** The current device remains schema 8/own009 with physical engine outputs inhibited. This increment makes the acquisition and correction semantics testable before those required integration steps.

## Acquisition contract

`firmware/include/ecu/flex_fuel.hpp` accepts serialized rising/falling timestamps with an explicit source. It has no GPIO, ISR, queue, NVS or web access and is not safe for concurrent callers. A future target ISR must enqueue bounded raw events; one worker owns this core. A source name describes origin, not electrical qualification. Target binding must reject synthetic sources.

The default calibration maps 50 Hz to E0 and 150 Hz to E100. Low-pulse width maps 1–5 ms to −40–125°C. Those conventions follow the pinned production [sensor ISR](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/sensors.cpp) and [periodic conversion](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/timers.cpp). They do not select or qualify a purchased sensor or harness pinout.

The core requires eight complete coherent cycles by default, adjustable from 2 to 32. Frequency is derived from the sum of full periods; temperature uses low widths from those same cycles. The calibration uses the complete configured frequency span. A first rising edge cannot establish a valid period or low width. Optional smoothing uses elapsed measurement time, never query count. Its first qualified value initializes the filter directly.

Calibration validation bounds frequency, sensor-fault threshold, tolerance, window size, stale interval and filter time. Default frequency tolerance is 1 Hz with 1 µs timestamp-difference uncertainty. Low width has a 2 µs boundary tolerance. The fault-frequency period threshold rounds conservatively. Values inside tolerance can clamp to the physical range and expose clamp flags. Repeated levels, timestamps that do not increase, a reversed/future query, short edges, invalid widths/frequencies, overflow, source/config changes and stale data invalidate acquisition. A completed sample expires after 250 ms by default even if a newer incomplete edge exists.

Faults carry a generation and remain pending through reacquisition. `observe()` returns the invalid pending sample; `acknowledge(generation)` may clear only the current generation after observation. The later engine consumer must ACK only after a completed control observation consumed that invalid sample. Old tickets cannot clear newer faults. Reconfiguration resets the complete window/filter and preserves fault notification. No initial or held value is silently treated as E0.

## Correction contract and integration requirements

The separate correction helper provides six-bin ethanol fuel percentage, signed spark addition and optional fuel-temperature percentage curves. Defaults are neutral and disabled. Enabled correction requires a valid, fresh, source-tagged coherent sample. Invalid correction returns unknown factors and an explicit reason. Off returns exactly neutral factors without disabling acquisition needed by secondary ETH conditions.

This helper does not yet alter fuel mass, pulse widths, cranking angles, cylinder trims, secondary spark or scheduler demands. Required integration must preserve zero-effective-fuel behavior, deadtime per opening, hard pulse/dwell limits and actual correction order. Production applies fuel and temperature factors separately; its flex spark correction precedes later limiter/fixed/cranking overrides. Interactions with our secondary tables, trims and transient reference adder need explicit coupled experiments before acceptance.

Required remaining work includes schema/default/import migration, atomic whole-tune validation and storage, browser controls/guides, own TunerStudio offline definition/MSQ, runtime/log/radio fields, target acquisition/fault ACK, pin/protection design and HIL. Acquisition ownership must be requested when either flex corrections or a secondary ETH condition needs it. Existing own009 pages, runtime layout and applications are unchanged in this groundwork.

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

GPIO3 is already reserved by the idle accessory draft. GPIO0 is BOOT/PAIR. GPIO46 remains only a candidate: [Espressif's boot-mode documentation](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html) requires it low/floating when GPIO0 is low for serial download. Runtime software cannot repair an incorrect reset strap. Pin allocation, boot gate, component selection, routing and enclosure changes remain pending.

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

Native success does not establish actual ESP32 input acquisition, online TunerStudio support, coupled own-engine flex operation, fuel chemistry/calibration, target timing, physical electrical/environmental behavior or full Speeduino parity. Those remain open requirements of the project.
