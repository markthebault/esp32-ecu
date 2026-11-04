# Flex integration preflight

Read-only review against project8c589a4 and pinned production9ff5aae. Source freeze/hashes are in preflight-source-freeze.json. Baseline headers were extracted from the commit, not a concurrently changing working tree, for later exact disabled-path comparisons. No production executable or device was run in this preflight.

## Fuel order

Production correctionsFuel separately composes flex fuel and fuel-temperature percentages after baro. calcPrimaryPulseWidth applies aggregate corrections before includeOpenTime and before the reference AE adder. That adder is based on REQ_FUEL, independent of current VE/MAP/WUE/EGO/flex. computePulseWidths returns zero immediately if aggregate corrections is zero, so zero fuel/temperature factors suppress even an active reference adder and deadtime.

Own engine computes base and multiplicative transient fuel separately, then AddReference chooses base+added. Put flex factors on the corrected base/multiplicative paths before that choice, without scaling added or deadtime. Preserve exact disabled arithmetic and operation order. If either enabled factor is zero, prevent AddReference from resurrecting fuel and keep all pulses zero. Preserve transient deceleration-zero and DFCO precedence.

Example oracle: base10 *1.5 *0.8 + reference adder2 =14; cylinder trim1.25 gives17.5 effective dose; divide actual openings/flow, then add one deadtime per opening. Multiplying final(base+adder) instead produces18 trimmed dose and is distinguishable.

Own current per-cylinder fuel trim scales effective complete dose then adds deadtime, whereas production applyFuelTrim scales the total pulse including deadtime. This is an existing documented policy difference; do not silently change it during flex integration or claim exact production trim parity. Judge capacity on resulting actual channel demands after trims, and retain hard global cut on one failed channel.

## Spark order

Production advance1=correctionsIgn(primaryraw), with flex first, then soft limiter, then fixed/cranking overrides. Secondary Multiply acts on corrected advance1 and therefore scales flex and retard together. Add adds to corrected advance1. Conditional/Input calls correctionsIgn on raw secondary and must receive flex exactly once too. Cranking/fixed overrides suppress flex and bypass secondary. Production calls the correction dispatcher twice in switched mode; do not copy stateful side effects merely to add a stateless flex value.

Own integration should add flex to each chosen raw scalar/cylinder demand before that demand's clamp/retard and secondary operation. Never add flex again after secondary::spark. Reconstruct per-cylinder demands from raw tables/trim/flex, not a globally clamped scalar. Own trim-before-secondary behavior differs from production ignition trim applied after global corrections; preserve existing disabled behavior and disclose the difference.

Example oracle: primary20, flex+5, retard5 -> corrected20; secondary150% ->30; Add10 ->30; switchedraw25 ->25. Crank5 stays5 (flex suppressed). Test negative/positive flex and cylinder trim, soft-band edges, final -5/40 bounds and saturation that a negative trim can recover. General fixed-timing configuration is not currently implemented in own Tune; do not imply otherwise.

## One coherent dependency

Derive ETH selection and correction factors from one validated observation/calibration snapshot. Do not trust bare legacy ethanol_pct/qualified independently. Exact CaptureConfig equality/context must be checked at control time: a local config_epoch counter alone cannot prove agreement with active Tune after reconfiguration or producer restart. Check future/stale timestamps at consumption without replacing flex sample time by fresh ADC/control time. Required acquisition is corrections.enabled OR either secondary ETH condition, including dependencies while a table is inactive or spark is cranking-bypassed.

Target binding must reject Synthetic, unknown sources and any value-only host source. TargetCapture requires actual producer origin and configured input confirmation; the source label or user confirmation is not electrical qualification. Reconfiguration/config-lock races must produce invalid data and full reacquisition, not an old coherent measurement under new calibration.

## Legacy host value-only route

Explicit Source::SyntheticValue(3) is acceptable for the historical host scalar-ETH API only with corrections Off, normal observation-time freshness, explicit construction by the host adapter/tests and clear value-only diagnostics. Keep frequency/width/temperature unknown. It must remain invalid for raw Capture::edge and enabled corrections, rejected by target binding and excluded from raw-edge/acquisition evidence. Avoid automatic Controller fallback from unlabelled bare scalar fields. Distinguish qualified synthetic ETH selection from raw/coherent eight-cycle capture readiness.

## ACK/config/migration

ACK only an exact pending generation after the same invalid snapshot was consumed by a completed control observation. Tune-lock/binding/config failure or a newer fault must not clear it. Do not use a diagnostic read as control completion. Capture context and invalid consumption must survive the normal config fence and publication races; one serialized owner must operate Capture.

Schema1..8 parsing into an already-used Tune must explicitly reset flex to disabled neutral. Schema9 must require a full strict section. Upgrade schema8 by adding flex without replacing or duplicating its secondary rules/maps. Malformed config, nonfinite/unsorted curves, unknown keys/enums and whole-tune allocation/store failure must preserve active tune and revision atomically. Neutral defaults do not make enabled acquisition optional.

## Wire/target scope

Own009 page8192 has384 bytes after7808. Append fields with explicit units/alignment, update reserved-tail rejection and preserve old offsets. Existing runtime/radio schema4 is250 bytes including HMAC, so it cannot accept an unchecked payload append; old screens must not silently misrepresent enabled flex. Keep source, sample age, calibration match, fault generation/ACK, requested reason and correction enable distinct in diagnostics. Update both engine_bridge and target_timing_bridge, auxiliary host parser and receiver enum bounds for new source3.

No pin allocation or hardware acceptance follows this review. GPIO3 belongs to idle, GPIO0 is BOOT/PAIR and GPIO46 needs a protected reset/download-safe gate before application code. Target timer/capture/ISR/resource/queue/overflow and power/brownout behavior need separate frozen implementation/hardware review. Physical outputs remain inhibited.

## Preserved coverage disclosure

The earlier acquisition reviewer probe unintentionally updated16 generated upstream .gcda counters. Exact files/timestamps are preserved in prior-coverage-side-effect.json; no reconstruction/reset was attempted. Generated coverage is excluded from unchanged-cache claims. Every later production executable must be an owned copy and receive an owned GCOV_PREFIX and GCOV_PREFIX_STRIP=0 before startup.
