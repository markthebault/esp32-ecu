# Flex acquisition source review

Review basis: project eb3ba08e8687b67c461dabd5545b14de78736260; genuine unedited Speeduino 9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20. No project/external checkout or numerical fixture edits. Source hashes and numerical fixture hashes are in source-review-binding.json.

## Production acquisition facts

- sensors.cpp:906: CHANGE ISR uses the resolved boardInputPin_t. LOW records micros() as flexStartTime; HIGH subtracts this uint32 timestamp, clamps elapsed to65535us, applies the unsigned16 LPF and increments uint8 flexCounter. The initial HIGH has no known LOW start. Native board uses inputPin_t/digitalRead; actual AVR board uses fast port input. The native fixture must invoke the installed callback for a genuine changed pin level, including both polarities; directly assigning ethanol or calling a substitute algorithm does not exercise this.
- sensors.cpp:919: initialiseFlexSensor zeroes ethanolPct, ANDs flexEnabled with !pinIsOutput(pinNumbers.pinFlex), sets INPUT (external pullup required), installs CHANGE interrupt. setup resolves board mapping before this. Verify pinFlex, pin mode, enabled state, interrupt number, exact callback and mode after production setup; do not overwrite pinFlex after setup. Map3 normally resolves pin2. Native Arduino fake's Uno interrupt macro differs from FakeMega pins; the existing fixture explicitly overrides it with Mega mapping.
- timers.cpp:159: every1000 oneMSInterval calls, count below low->0; above high+1 but below high+20->100; at/above high+20->0; otherwise subtract low. A result exactly1 becomes0 and values above100 clamp100. There is no normalization by high-low. LOW_PASS_FILTER then filters ethanol. Counter wraps modulo256 before these rules. Fuel-temperature low width is clamped1000..5000us and transformed by ((4224*us)>>10)-8125, then signed divide100. Temperature range -40..125C, integer truncation.
- There is no explicit source validity/fault/age state. No pulses produce filtered ethanol toward0 but leave/clamp previous width; startup has width0 which becomes1000. The own implementation's strict invalid/stale inhibition is an intentional policy difference.
- oneMSInterval and edge coincidence ordering is a fixture convention, not CPU/vector emulation. Test phases immediately before/at/after1s boundaries and disclose tick-before-edge vs edge-before-tick.

## Production correction facts

- corrections.cpp:65..67/643/653/901: three separate six-bin curves. Fuel factors are percentage bytes; fuel temperature axis is temp+40; spark byte encoding is value-40 through IGNITION_ADVANCE_LARGE, not signed8 reinterpretation.
- correctionsFuel combines ethanol and temperature factors separately (integer percent composition), after baro. Spark correction is the first correctionsIgn operation, before soft limit and fixed/cranking overrides. Standalone factor parity does not establish final engine-order parity.
- Source-level hypothesis requiring genuine loop confirmation: table2D non-UNIT_TEST cache starts input0/output0/cacheTime0 and getCacheTime=currentStatus.secl. At initial secl0/ethanol0 a first flex fuel or spark lookup can return cached0 rather than configured first-bin value. initialiseCorrections does not reset table caches. Do not prewarm tables, assign secl or manually assign ethanol to avoid this startup path.

## Required raw fixture probes

- Neutral and nonneutral curves; low/high/percent midpoint; startup/no-edge; nominal1/3/5ms low width;0999/1000/1001/4999/5000/5001us; first edgeHIGH; steady state and step with FILTER_FLEX0/75/255; hold final input with no new edges.
- Frequency pulse counts49/50/51/52/149/150/151/152/169/170/171 and255/256/306/356 pulses per1s. Phase-shift the window so a counter boundary is not mistaken for a sensor error.
- Nonstandard calibration span e.g80..180 vs50..150, then80..200. Treat subtraction/non-normalized behavior as observed production semantics only after real raw-edge experiment.
- Single edge/drop/duplicate pin level; opposite polarity at same timestamp; missing LOW start; micros32 wrap under monotonic host64 clock. Native64-bit unsigned long is not AVR32 unsigned long/int16 or CPU timing.
- Decode raw curve bytes accurately and verify readback after production setup. Do not use UNIT_TEST (it disables table cache and changes symbol visibility). Preserve ABI flags: -fshort-enums, NATIVE_BOARD, channel counts, board include, timer typedef, Arduino defines. Do not link objects from16/32 timer variants interchangeably.
- Source/archive, all fixture files, compiler+flags, dependencies and binary hash must be bound to results. Keep own source and genuine code separately identified; record source modifications and native HAL limits. Existing numerical fixtures remain immutable.

## Own core review checklist

- No first-cycle acceptance without known falling edge, rising edge and period; timestamp0 must be representable independently of an initialized flag.
- Window values must come from coherent completed cycles. low_width<period; all additions/differences/counts checked; window bounded. Explicit raw source provenance and source/config changes reset old window. Invalid enum/NaN/Inf/unsorted bins reject whole config.
- Freshness comes from raw completion time, never snapshot/query time. Held sample repeated at increasing query time must go stale. Per-edge producer timeout must not be hidden by sparse snapshots.
- Duplicate/reversal/glitch/overflow causes invalid reacquisition. Expose fault generation/pending latch for later worker ACK so quick reacquisition before an engine observation cannot erase a capture fault. Existing switch acquisition provides a model.
- Enabled correction requires a current valid bounded sample; Off must preserve exact previous arithmetic and avoid requiring acquisition. Neutral100/100/0 curves do not remove enabled sample validity requirements.
- Shape/schema/service/engine/screen/UI/config/log/debug/pin ownership remain open until connected. A portable factor does not establish operator-configurable flex fuel.

## Pin and physical scope

GPIO3 already belongs to the idle accessory draft. GPIO0 is BOOT/PAIR. GPIO46 is a candidate only; it is a strap and must be LOW/floating when GPIO0 is LOW at reset for serial download. Normal GPIO0-HIGH flash boot ignoresGPIO46, but a pulled-HIGH sensor circuit can break BOOT recovery. Permanent protected hold/bias must work before application code and across power/reset/unplug/brownout. A runtime pin reservation cannot prove this. No pin allocation or physical/electrical release is established.

Primary source verification read2026-11-04: https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html ; https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html ; https://docs.espressif.com/projects/esp-idf/en/v4.4.1/esp32s3/api-reference/peripherals/gpio.html . GPIO46 on ESP32-S3 is not the S2-only input-only restriction; avoid copying generic family text without variant verification.

## Generated coverage side effect

The table-cache probe unintentionally updated16 preexisting generated .gcda files in the external checkout .pio/build/native_code_coverage directory when linked dependency archives flushed coverage at exit. No tracked source or numerical fixture was changed. These generated files were left intact because their prior counters cannot be reconstructed safely. See coverage-side-effect.json. Any later executable probe must redirect GCOV_PREFIX into this review directory with GCOV_PREFIX_STRIP=0.
