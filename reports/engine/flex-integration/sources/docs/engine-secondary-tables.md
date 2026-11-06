# Secondary fuel and spark tables: development integration

Schema8 and own009 expose independent secondary fuel and spark tables through firmware configuration, the browser, TunerStudio offline files, coherent diagnostics, bounded logs and negotiated screen telemetry. The target implements guarded J4 switch acquisition, with a separate routed THT accessory prototype and wiring/debug guide. [Enabled-table plant comparisons](engine-secondary-plant.md) exercise both project dispatchers and both production-reference timer models, with neutral, fault, quantization and refinement controls. Physical accessory qualification remains pending. Physical engine and idle outputs remain inhibited in the selected web builds.

The independent architecture assessment exercised unchanged [pinned Speeduino secondary functions](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/secondaryTables.cpp), interpolation and ignition corrections without `UNIT_TEST`. Its342 controlled checks establish reference behavior, not a complete engine-loop or plant comparison. [Evidence and implementation review](../reports/engine/secondary-core/README.md) bind the earlier core foundation to its exact sources. The separate [software integration evidence](../reports/engine/secondary-integration/README.md) preserves current sources, failure probes, browser/application checks and target audits.

## Core contract

Each secondary16×16 table has independent RPM/load axes, MAP/TPS/IMAP:EMAP source, declared axis basis, mode, condition threshold, input channel/polarity and debounce period. Its cell meaning is separately declared as absolute, multiplier or adder. A mode or source change cannot silently reinterpret stored cells or axes. The browser retains them and requires explicit calibration acknowledgement before replacing axes or declaring a new cell meaning. Neutral fill is a separate action:100 for multipliers,0 for adders. Absolute tables have no invented neutral replacement. TunerStudio exposes source, stored axis and cell meaning separately; an inconsistent whole-page burn rejects atomically.

| Mode | Fuel coefficient | Spark |
| --- | --- | --- |
| Off | Existing primary result | Existing primary result |
| Multiply | Primary × secondary /100, bounded0..255 | Corrected primary advance × secondary /100 |
| Add | Primary + secondary, bounded0..255 | Corrected primary advance + secondary delta |
| Conditional | Replace primary when the selected physical value is strictly greater than its threshold | Replace the base spark table, then apply its own soft retard |
| Input | Replace primary when a qualified debounced input matches its polarity | Same replacement/correction policy |

Conditions are RPM, absolute MAP kPa, physical TPS percent and qualified ethanol percent. The core accepts explicitly qualified synthetic ethanol for testing; there is no target ethanol producer. An enabled Conditional rule using ethanol therefore faults on target instead of inventing a value. Other modes may retain unused ethanol condition metadata without introducing that dependency. TPS thresholds use physical percent, unlike Speeduino's internal half-percent status and separate TPS table scaling. No continuous table blend is claimed.

Fuel composition precedes existing enrichment, EGO, per-cylinder fuel trim, opening-count splitting, deadtime and capacity checks. Lambda `follow_fuel` and trim coordinates continue to follow the primary fuel source. Zero combined ordinary fuel retains the existing no-deadtime-only-opening policy; a configured reference transient adder can still deliver its separate dose.

Spark multiply/add follows primary soft retard, matching the reference order. Switched spark applies soft retard to the selected secondary value. In sequential mode cylinder offsets apply before nominal angle bounds/retard and before multiply/add; switched offsets apply to the secondary base. Final advance remains bounded-5..40degrees. Cranking uses the original cranking angle and bypasses secondary spark selection while Input qualification continues. Stable fresh contacts therefore retain qualification at run entry; invalid data still requires a new stable interval. Every valid Input rule observes its sample even when a load-coordinate guard fails, so a simultaneous sensor fault cannot hide lost switch qualification. The project has no fixed-timing mode. Integer reference rounding, its wider angle domain and diagnostic encodings are not copied into the project's F64 arithmetic/F32 observations.

Enabled secondary sources join the static configured input dependency union even when a condition currently selects primary. A MAP condition independently requires qualified MAP; a ratio source requires qualified absolute EMAP and participates in the existing J16 role conflict. These pressure dependencies remain required while cranking. Enabled Conditional ethanol rules likewise require a qualified value. Missing values cause a fault, rather than quietly selecting primary. Off rules introduce no extra dependencies.

Switch samples carry source, validity, observed timestamp and raw level. Default debounce is20ms;0..500ms is configurable in the core API. Freshness is at most20ms, inclusive. Initial qualification needs fresh observations spanning the debounce interval. Reusing a held sample cannot advance qualification. A normal transition retains the previous qualified selection until the new level is stable; pending state is explicit. Invalid, stale, future/reversed or contradictory same-time observations invalidate immediately. A poll gap over20ms, source/channel/debounce/rule change, BadTune or controller reset requires qualification again. Fuel and spark may deliberately share one coherent sampled input while retaining their individual debounce/polarity rules.

## Configuration, compatibility and memory

The required schema8 `secondary_tables` object contains `fuel` and `spark`. Each rule stores mode, source, axis, cell meaning, condition, physical threshold, input channel/polarity, debounce and a complete16×16 map. Types, unknown/duplicate keys, full-width enum/channel values, F32 map axes/cells and physical scalar bounds are validated before activation. Off tables retain their edited calibration and still require valid stored units/ranges.

JSON1..7 and own001..008 import explicitly add default Off secondary tables. Schema7/own008 load choices, AFR behavior and0..255 fuel coefficients are preserved. Older identities retain their original20..120 F32 bounds. Loading stored JSON retains its original bytes/revision until explicit save. File origin remains metadata; browser Save uses the already-loaded editor revision and rejects intervening writers. An import does not publish or silently rebase calibration.

Current [own009 INI](../tuning/esp32-ecu-secondary.ini) and [layout manifest](../tuning/protocol-layout.json) use one8192-byte page. The historical [own008 definition](../tuning/esp32-ecu-load.ini), [manifest](../tuning/protocol-layout-load.json) and [codec](../tuning/archive/own008_tuning_layout.hpp) remain records. All first5376 own008 bytes, including its reserved region, retain their meanings. Independent comparison checks324 valid legacy profiles byte for byte. New fields are:

| Region | Offset | Bytes |
| --- | ---: | ---: |
| Fuel rule |5376|36|
| Spark rule |5412|36|
| Reserved zero |5448|56|
| Secondary fuel RPM/load/cells |5504|1152|
| Secondary spark RPM/load/cells |6656|1152|
| Reserved zero |7808|384|

Each rule contains five U32 enums, F32 threshold/debounce and U32 channel/polarity. Each map contains16 RPM values,16 load values and256 cells, all F32. Whole-page staging, stable origin, CRCs, backend CAS and atomic commit remain in effect. Invalid tune, allocation/storage failure or stale session cannot partially publish either table. A successful burn resets control and requires phase acquisition again.

The tune document limit is48KiB. Legal dense/subnormal F32 maps exceed the old24KiB limit. `engine_nvs` grows from64KiB to128KiB at0x210000, ending0x230000; every other partition offset and the2MiB factory app stay fixed. The pinned IDF writes a replacement blob before invalidating the prior version, so two maximum-size documents need more pages than the old partition. This is a source/capacity assessment, not physical flash/fragmentation/power-loss qualification.

Target startup checks the actual partition address/size before opening engine storage. A mismatched old partition table blocks engine saves, exposes the reason and retains saved bytes; it does not erase or migrate flash automatically. A future hardware installation needs the matching partition table and a separately reviewed backup/flash procedure. No board was flashed here.

Native and pinned Xtensa object sizes are7204bytes for `Tune`,8272 for the resident tuning `Session`,528 for a coherent `RuntimeSample`,544 for a row and139352 for the256-row recorder. A16-row copied page is8792bytes. Temporary typed tune workspaces and HTTP request buffers use checked heap ownership. Target JSON/MSL export streams one row at a time outside recorder locks. Native DOM/allocator failure probes do not measure target minimum heap, stack high-water or timing. N16R8 enables PSRAM malloc; the generic A3 build compiling does not establish runtime heap fit.

## Diagnostics, logs and screens

Both rules report primary, corrected primary, secondary and combined values; load coordinate; condition/threshold; raw input level/validity/time; qualified/pending levels; source, age, reason, configuration metadata and availability/evaluated/valid flags. A known configuration is not a valid input or completed arithmetic result. Unknown numbers are JSON `null` / MSL `NaN`. An invalid future raw switch timestamp remains a diagnostic decimal string without advancing any control clock. Host switch/ethanol inputs are explicitly synthetic and cannot claim target provenance.

Selection uses core physical values and strict `>`. F32 diagnostic rounding may make the logged condition equal its threshold even when the F64 core selected secondary; consumers must use the reported selection instead of recalculating it from rounded fields.

Own009 retains the416-byte runtime prefix and adds two80-byte observation blocks at416/496 in a640-byte runtime. The full response is647 framed bytes, within the existing1024-byte USB rings. Each block contains nine F32 values, flags/channel/axis, six U32 codes, a raw U64 observed timestamp and eight reserved bytes. Bytes576..639 remain zero. [USB transport details](engine-usb-tuning.md) describe framing, ownership and commit semantics.

MSL006 appends31 fields per rule. Native/browser engine exports have188 columns; direct SIL format has145. Earlier prefixes remain intact. Decode source/mode/cell/condition/reason codes and availability/validity before interpreting values. MegaLogViewer HD Lite4.6.14 opens/plots the new fields in both formats. Its extrema can displayNaN on channels containing unknown samples; vendor-calculated channels and large integer precision remain unqualified. The application fixtures are fixed-input synthetic native probes, not a coupled engine trajectory.

Negotiated ESP-NOW schema4 keeps the250-byte packet and authenticates compact mode/source/active/available/evaluated flags in former reserved bytes90/91. Full values, reasons, raw switch state and cell meaning remain in web/USB/log diagnostics. Schemas1..3 retain exact layouts; every non-Off secondary mode requires schema4, even if its condition currently selects primary. An unrepresentable peer receives sensor-stream fallback and an explicit upgrade reason. [Wire contract](espnow-engine.md) preserves the nonce/counter/sequence/ACK/freshness rules. No physical two-device/RF test is claimed.

## Application workflow and remaining gates

TunerStudio MS Lite3.3.01 opens the current definition with no INI parser errors or MSQ unit warnings. Offline edits to both rule panels and both maps survive a complete8192-byte F32 page comparison with the known base revision37 supplied explicitly because the application omits that read-only origin. The application-authored [example](../tuning/examples/tunerstudio-secondary-roundtrip.msq) imports through the browser/native paths without silently publishing. It is an illustrative test fixture, not an engine base tune. Own009 online vendor acceptance has not been established; earlier own-identity online rejection remains unresolved.

Reproduce the software checks with `CXX=g++ sh scripts/test_firmware.sh`, the full Python suite, `tools/test_secondary_ui.py`, and the [software evidence verifier](../tools/verify_secondary_integration_evidence.py). The historical7776-row disabled probe remains preserved. The separate [enabled-plant packet and verifier](engine-secondary-plant.md) bind new controller loops, inputs, fault recovery, exact neutral replays and refinements to their own sources; older packets remain records of their original increments.

1. The separate [SW2-J4-DRAFT1 accessory](../hardware/switch-inputs/README.md) and production target acquisition implement the digital input path. Independent software/circuit reviews, native CAD checks and conditional circuit experiments do not establish physical protection, reset/power behavior, rail/thermal headroom, scheduling or fit. These measurements remain required. Cam, J16 pressures, PAIR, RESET and SAFE_N keep their roles; J4 itself is internal3.3V logic.
2. The [enabled-plant comparison](engine-secondary-plant.md) supplies production-reference map/profile writers, independent timed inputs, crossings, bounce/failures, trim ordering, zero fuel, capacity, selected half-step runs and independent integration review. Its declared fixtures do not cover target ethanol acquisition, every pressure pair, all combinations of trims/sources or physical engine behavior.
3. Measure actual target storage/heap/stack, USB, switch electrical behavior, timing, RF and fail-safe outputs before any physical engine operation. Wider Speeduino feature parity and physical qualification remain open.

The new separate accessory has a native schematic/PCB, candidate BOM and literal contract. It uses MCP23008 GP0/GP1 for contacts and output-only GP7 for a guarded loopback. It has no Gerber/drill or enclosure release. Original carrier/manufacturing/manual artifacts remain records; their case fit is not extended to this accessory. Ordinary two-wire contacts cannot prove wire continuity. Exact passives/procurement, reset and power-off margins, protection ratings, full supply loading and physical tests remain open.

Target diagnostics at `switch_accessory` report bus phase, requested mask, current/last fault, exact source times and counters, fault awaiting a completed control observation, read duration and SDK ownership/result. Source timestamps use the controller GP clock and never refresh on write-only ticks. A trailing IODIR read catches reset during acquisition; a later reset is detected by the next observation/freshness check. Fault-ID acknowledgement prevents fast bus recovery hiding a skipped invalid control observation. The nominal5ms service cadence and measured3ms acceptance budget are not hard scheduler/SDK deadlines. Existing per-rule qualification, source/age/reason and selection fields carry through unchanged to own009/USB/MSL; no wire identity or schema bump is needed. Host stimuli and missing hardware diagnostics remain explicitly synthetic or unknown.
