# Load sources, pressure and AFR development

Schema7 and own008 add independent primary fuel and spark coordinates: manifold absolute pressure, physical TPS percent, or `100 × IMAP / EMAP`. Lambda and cylinder-trim tables may follow the primary fuel coordinate or select their own source. Selected ESP32 web builds keep engine and idle outputs physically inhibited. This is a software/configuration/debugging increment, not a manufacturing or engine release.

| Setting | Meaning |
| --- | --- |
| MAP | Table coordinate in absolute kPa |
| TPS | Table coordinate in physical percent, 0..100 |
| IMAP / EMAP | Dimensionless pressure ratio expressed as percent, with a calibrated absolute exhaust-pressure input |
| Pressure `none` | Fixed 100 kPa modeled fuel reference, independent of the table coordinate |
| Pressure `map_100kpa` | Physical MAP multiplication, preserving the old calculation |
| Pressure `map_baro` | Modeled reference pressure `100 × MAP / baro`; baro is fixed/manual or a calibrated live input |
| AFR `off` | Stoichiometric fuel basis, with no target incorporation |
| AFR `target` | Divide by target lambda, preserving the old calculation |
| AFR `measured` | Apply measured lambda / target after the running delay, outside cranking, with a ready wideband; otherwise factor1 with an explicit reason |

Pressure multiplication is independent of the table source. Selecting TPS while retaining MAP multiplication is not pure Alpha-N. Selecting TPS with pressure Off requires a TPS calibration; an unchanged MAP table is not converted automatically. Measured-AFR incorporation is a compatibility calculation, separate from bounded EGO PI; it is not autotuning or a guarantee of reaching target lambda. A separate baro correction curve remains unimplemented.

Table units are explicit metadata. The browser preserves axes and cells when a source changes. Save rejects a mismatched basis until the operator reviews the calibration and explicitly accepts edited axes or replaces them with illustrative axes. Replacement retains cells and requires retuning. TunerStudio exposes the same source and axis-basis fields; changing a selector alone cannot silently reinterpret a saved tune. MAP axes allow5..110 kPa, TPS0..100%, ratio0..600%; the engine remains naturally aspirated with a10..110 kPa operating guard.

New fuel coefficients allow0..255%. Zero ordinary fuel suppresses deadtime-only openings while spark can continue. A reference transient adder can still deliver finite fuel on a zero base; its effective dose ratio is unknown, with a flag, rather than infinity. Injector deadtime, opening-count splitting, cylinder trims and final capacity limits retain their existing meanings.

Historical JSON1..6 and own001..007 MSQs explicitly migrate to the old MAP/target model. Their F32-qualified20..120 coefficient bounds remain enforced before migration. Old stored bytes/revisions remain unchanged until an explicit successful save. Defaults preserve the original double-precision fuel arithmetic and do not feed F32 diagnostic coordinates back into calculations.

## J16 and input dependencies

J16 is the existing protected POSTCAT input on ADC channel5. Its physical pins remain **1 ground, 2 SENSOR_5V, 3 POSTCAT_BUF signal**. Default role is `postcat_monitor`. An explicit `emap` or `baro` assignment reuses this input; disconnect the prior buffer and connect only one appropriate conditioned0..5 V absolute-pressure signal. Confirm its measured linear/table conversion in exact unit `kPa`; relabelling raw voltage is rejected. The about55 kohm input loading and shared5 V supply budget still apply.

EMAP qualification is20..500 kPa absolute; live/fixed baro is50..110 kPa. The same J16 input cannot supply both live baro and EMAP. A simultaneous extra pressure path remains open. No pre-crank ambient capture is inferred from zero RPM. Exhaust sensor/tubing temperature, electrical behavior, fit and installation remain unqualified.

MAP is required by pressure multiplication, active MAP/ratio tables, enabled trims using MAP/ratio, and MAP-rate enrichment. Lambda's coordinate is inactive only when AFR is Off and EGO is disabled. A pure TPS configuration can operate without qualified MAP; it preserves an unknown reading and reports the pressure guard unavailable. A known calibrated MAP above110 kPa faults every mode. TPS/CLT/IAT, rails, ADC and acquisition supervision remain required.

A fresh stopped/cranking observation resets the measured-AFR running delay, including during another input fault. Stale/future observations do not repeatedly reset it, and a continuous-rotation rev or sensor fault retains the epoch. This conservative possible-restart policy does not prove a physical stop. The previous afterstart clock is separate and unchanged.

## Tuning, logs and screens

Use [own008 INI](../tuning/esp32-ecu-load.ini). One5376-byte configuration page retains the first5120 bytes, appends twelve U32 selections at5120..5167 and baro/delay F32 scalars at5168/5172. The remaining200 bytes are reserved zero. Whole-tune staging, stable origin and backend revision checks remain atomic; HTTP or another session causes a stale-editor conflict.

One416-byte runtime block retains the first320 bytes. It appends nine F32 values at320..355, a flags/reason U32 at356 and eight source/mode codes at360..391. Bytes392..415 remain zero. A full runtime reply is423 framed bytes. Configuration chunks remain256 bytes; USB rings remain1024 bytes. This is a protocol implementation, not measured USB throughput or online TunerStudio acceptance.

The web/JSON `load_model` object and engine MSL005 expose coordinates, normalization, baro/EMAP/aux pressures, AFR factor, source codes, flags, reason and AFR state. Engine/native/browser logs have126 fields; direct SIL logs83. Unknown numerics remain null/NaN. `available` does not make every optional value valid. AFR state255 means not evaluated. Check source, ages, validity masks and reason before interpreting a number; vendor-calculated channels and large integer precision are not qualified by opening a file.

Flags bits0..12 respectively identify arithmetic valid, required MAP, required auxiliary pressure, MAP calibrated/in range, auxiliary calibrated/in range, manual baro, MAP guard available, zero base fuel, undefined effective transient ratio, AFR waiting and measured AFR active. Bits13..15 encode AFR state. Runtime word bits16/17 separately identify model/AFR availability, and bits24..26 the reason.

[ESP-NOW schema3](espnow-engine.md) adds authenticated source tags and a compact summary within250 bytes. Schemas1/2 retain their232-byte layouts for representable legacy models. A peer requiring an upgrade receives a disclosed fallback to the existing sensor stream. Full per-cylinder, transient and load-fault diagnostics remain in web/logs. No screen hardware or RF qualification is included.

## Comparison and review

[Evidence](../reports/engine/load-model/README.md) records56 primary cases plus8 selected half-step runs across portable/target project execution and pinned production Speeduino32/16 timer models. Eight prior executed-event/plant-ledger replays remain exact. Native and173 Python tests, browser workflows, three firmware builds, actual offline TunerStudio/MSQ and MegaLogViewer file checks accompany separate independent architecture/core/integration/simulator reviews.

The external Modelica MVEM air path supplies thermodynamics and pumping; local wall film, combustion and free-shaft behavior remain empirical. The Alpha-N map was derived from independent steady airflow without ECU feedback:244 points settled;12 below-pressure-domain corners remain unqualified and were not weighted by the tested trajectories. Ambient80 kPa changes the physical FMU parameter. EMAP125 kPa is an exogenous sensor stimulus, with no exhaust thermodynamics. The baro experiment's coefficient scaling is a declared fixture, not an automatic production correction.

An unchanged flat85% TPS map stalls the project in this plant while the reference remains running rich. Zero fuel prevents project injector starts. Correct fixed/live baro fixtures agree; an incorrect datum shifts mixture. Measured and target AFR modes have different startup/readiness and steady behavior. Passed audits establish declared software bounds and conservation, not ideal tuning or equivalent engine policies. Selected half-step differences stayed below0.9%; native polling cadence changes too, so this is not isolated solver convergence.

The native reference executes unchanged pinned sensor/load/fuel/decoder/scheduler source through a host HAL, with zero CPU/IRQ cost. Its TPS coordinate is physical percent×4; table axes are translated before raw load/2 storage, with actual integer rounding retained. Virtual EMAP calibration has-20..620 kPa headroom so20/100/125/500 kPa do not sit on the production ADC rail. This is not a physical transducer recommendation. Independent review caught and closed a rail/held-value fixture error, a rounding fault, misleading binding text and browser/native diagnostic mismatches.

Secondary fuel/spark tables, a separate baro curve, other cylinder counts/OEM trigger patterns, boost/VVT/flex/staged injection/knock, online application acceptance, physical HIL and vehicle qualification remain open. Source/CAD/simulator checks do not establish EMI/surge, thermal, splash, printed fit or real engine operation.
