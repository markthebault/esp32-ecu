# Secondary fuel and spark tables: core foundation

The shared C++ controller now implements independent secondary fuel and spark tables. **This is a core foundation, not an operator-ready secondary-table release.** Current schema7 JSON and own008 tuning explicitly keep the feature Off. The web editor, TunerStudio definition, coherent runtime/log/radio extensions, protected switch acquisition/accessory and new coupled plant comparisons remain pending. Physical engine and idle outputs remain inhibited.

The independent architecture assessment exercised unchanged [pinned Speeduino secondary functions](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/secondaryTables.cpp), interpolation and ignition corrections without `UNIT_TEST`. Its342 controlled checks establish reference behavior, not a complete engine-loop or plant comparison. [Evidence and implementation review](../reports/engine/secondary-core/README.md) bind this foundation to its exact sources.

## Core contract

Each secondary16×16 table has independent RPM/load axes, MAP/TPS/IMAP:EMAP source, declared axis basis, mode, condition threshold, input channel/polarity and debounce period. Its cell meaning is separately declared as absolute, multiplier or adder. A mode or source change cannot silently reinterpret stored cells or axes. The later UI must retain and explicitly review them.

| Mode | Fuel coefficient | Spark |
| --- | --- | --- |
| Off | Existing primary result | Existing primary result |
| Multiply | Primary × secondary /100, bounded0..255 | Corrected primary advance × secondary /100 |
| Add | Primary + secondary, bounded0..255 | Corrected primary advance + secondary delta |
| Conditional | Replace primary when the selected physical value is strictly greater than its threshold | Replace the base spark table, then apply its own soft retard |
| Input | Replace primary when a qualified debounced input matches its polarity | Same replacement/correction policy |

Conditions are RPM, absolute MAP kPa, physical TPS percent and qualified ethanol percent. The core accepts explicitly qualified synthetic ethanol for testing; there is no target ethanol producer or operator option yet. TPS thresholds use physical percent, unlike Speeduino's internal half-percent status and separate TPS table scaling. No continuous table blend is claimed.

Fuel composition precedes existing enrichment, EGO, per-cylinder fuel trim, opening-count splitting, deadtime and capacity checks. Lambda `follow_fuel` and trim coordinates continue to follow the primary fuel source. Zero combined ordinary fuel retains the existing no-deadtime-only-opening policy; a configured reference transient adder can still deliver its separate dose.

Spark multiply/add follows primary soft retard, matching the reference order. Switched spark applies soft retard to the selected secondary value. In sequential mode cylinder offsets apply before nominal angle bounds/retard and before multiply/add; switched offsets apply to the secondary base. Final advance remains bounded-5..40degrees. Cranking uses the original cranking angle and bypasses secondary spark selection. The project has no fixed-timing mode. Integer reference rounding, its wider angle domain and diagnostic encodings are not copied into the project's F64 arithmetic/F32 observations.

Enabled secondary sources join the static configured input dependency union even when a condition currently selects primary. A MAP condition independently requires qualified MAP; a ratio source requires qualified absolute EMAP and participates in the existing J16 role conflict. These pressure dependencies remain required while cranking. Ethanol conditions likewise require a qualified value. Missing values cause a fault, rather than quietly selecting primary. Off rules introduce no extra dependencies.

Switch samples carry source, validity, observed timestamp and raw level. Default debounce is20ms;0..500ms is configurable in the core API. Freshness is at most20ms, inclusive. Initial qualification needs fresh observations spanning the debounce interval. Reusing a held sample cannot advance qualification. A normal transition retains the previous qualified selection until the new level is stable; pending state is explicit. Invalid, stale, future/reversed or contradictory same-time observations invalidate immediately. A poll gap over20ms, source/channel/debounce/rule change, BadTune or controller reset requires qualification again. Fuel and spark may deliberately share one coherent sampled input while retaining their individual debounce/polarity rules.

## Compatibility and memory

All schema1..7 parse paths and own008 decode reset unrepresented secondary fields to their default Off state. Stored documents, old INIs, identities, bytes and revisions are not upgraded by this foundation. An own008 session rejects a programmatic backend model with nondefault secondary configuration or map data rather than exposing an editor that could discard it. A later versioned identity and migration must preserve both full tables.

The added maps grow the native `Tune` to7204bytes. The session now allocates its temporary typed workspace through checked `heap_object` only during open/burn; its resident native size is5456bytes. At most one workspace is live in scoped allocation tests, and it is released on every tested return. Burn allocation failure returns busy and preserves staged bytes/origin/base/active data. Explicit open/reconnect still abandons old staged edits before allocation, as before. These are native object/lifetime bounds, not ESP32 runtime heap/stack measurements.

The selected N16R8 target compiles with physical scheduler writes inhibited. Static image/section checks do not establish runtime memory, interrupt latency, electrical behavior or engine operation. Existing native/Python regression tests and exact disabled-path observations accompany the new core tests. No new secondary-table trajectory has yet been accepted against the independent external plant.

## Remaining implementation

1. Add a strict versioned schema/whole-tune page, migrations and atomic storage/CAS/allocation-failure checks. Measure document and target workspace bounds for two additional maps.
2. Add both browser/TunerStudio map editors, explicit cell/source basis review, imports/exports and actual application roundtrips. Extend coherent runtime JSON, bounded logs/MSL and negotiated screen telemetry with values, source, selection, pending state and invalid reasons.
3. Design and review a protected two-input THT accessory on internal J4 I2C, with bounded acquisition and register/configuration readback. Keep cam, J16 pressures, PAIR, RESET and SAFE_N roles. J4 itself is3.3V internal logic, not a protected switch connector.
4. Add production-reference map/profile writers and independent virtual inputs, then compare equivalent/perturbed calibrations in the external plant across both project dispatchers and reference timer models. Include crossings, bounce/failures, trims, zero fuel, capacity and selected half-step runs. Obtain independent integration/simulator review.

J4's MCP23008 PDIP18 accessory is a proposal, with GP0/GP1 candidates. The [current manufacturer data sheet](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP23008-and-MCP23008-Data-Sheet-DS20001919.pdf) identifies GP7 as output-only on MCP23008. Circuit protection/bias, reset/power behavior, exact parts, supply budget, CAD, harness/case fit and physical tests remain undone. Ordinary two-wire contacts cannot prove wire continuity. No current PCB, BOM, Gerber, enclosure or manual artifact implements this accessory.

Full secondary-table availability, wider Speeduino parity, online TunerStudio acceptance and physical qualification remain open.
