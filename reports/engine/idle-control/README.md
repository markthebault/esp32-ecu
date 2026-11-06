# Idle control evidence

This increment adds on/off, open-loop and closed-loop idle across the shared controller, common timer owner, configuration, browser, tuning files and logs. The master default is off. Physical idle writes remain compiled out in every shipped environment. The hardware is an **unrouted accessory draft with 28 unconnected items**, not a fabrication release.

[Control guide and reproduction](../../../docs/engine-idle-control.md) · [Feature gaps](../../../docs/engine-feature-coverage.md) · [Interactive figures](charts.html) · [Validation manifest](validation-summary.json) · [Metrics CSV](metrics.csv)

## Results and their scope

- [Matrix](matrix/summary.json): 29 coupled runs and 38 reference PWM checks. [Follow-ups](followups/summary.json): four restart/reachable-target runs. All declared software acceptance checks pass. Each summary binds its raw gzip traces and relevant source hashes.
- Both controller cores drive separate copies of the same fixed, uncalibrated external Modelica air path, empirical combustion/free shaft and independent RL/NC valve. Actual virtual GPIO edges drive the valve. No RPM trace is imposed.
- The default 900 RPM case does not track perfectly. With the valve disconnected or stuck closed, the baseline engine settles around 916–919 RPM, exposing limited downward authority. A separate 1,100 RPM tune with explicit normalized P/I gains 0.06/0.06 gives final-second mean absolute error of 0.71 RPM for this project and 3.67 RPM for Speeduino. This is model-specific calibration, not a physical engine tune or a general ECU ranking.
- Negative controls include disconnected/stuck valves, logical drive inversion, missing integral, open-loop control, sensor/trigger loss and restart. The step refinement also changes the reference loop cadence, so it is not an isolated solver-convergence result.
- [Reference pin probes](matrix/reference-pwm.json) preserve unmodified Speeduino PWM_OLCL timer activity after `disableIdle()`. The plant runs end with an explicit external virtual cutoff. A separate 50 ms timer-only probe exposes the production disable discrepancy before that cutoff; reported duty zero is not substituted for pin state.

The reference is Speeduino commit `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. Production control/decoder/scheduler sources are unchanged. The declared native HAL changes timer width/ticks, PWM conversion and deterministic clocks/GPIO. A once-only seeded initialization profile and unseeded controls are retained. Native16 is not AVR CPU/register/integer-width emulation. [Reference manifests](reference/) retain exact build inputs and binary hashes.

## Verification and applications

| Evidence | Result |
| --- | --- |
| [Native ASan/UBSan suite](tests/native.log) | 13 binaries pass, including 117 control scenarios and idle/PWM regressions |
| [Python suite](tests/python.log) | 135 tests pass |
| [Chrome UI checks](tests/ui/) | Engine, tuning/CAS, bounded logger and idle workflows pass, including 320/390/768/1440 px layouts |
| [Generated artifacts](tests/generated-reproduction.json) | Codec, INI/layout, idle UI and embedded assets reproduce byte-for-byte |
| [Firmware builds](builds/platformio.log) | Selected N16R8 web, generic A3 web and separate timing bench pass |
| [Final ISR/USB static audits](builds/) | Three ISR closures and two dedicated USB ownership audits pass; runtime timing/resources remain unmeasured |
| [Native KiCad](hardware/) | ERC 0, placement DRC 0, parity 0; **28 unconnected items remain** |

Actual TunerStudio MS Lite 3.3.01 edited/saved the own005 idle settings and curve, and displayed the spark map. [Screens and exact tested INI/MSQs](applications/) retain that offline session. The final generated INI subsequently narrowed only three master idle editor bounds; the tested INI is retained separately and both hashes are recorded. Current browser/native validators and layout checks cover the final definition. Online application acceptance remains unresolved; historical own003/004 rejection is not a new own005 online test. No vendor message was sent.

Actual MegaLogViewer HD Lite 4.6.14 opened/plotted the [48-field SIL log](applications/idle-sil-48-fields.msl) and [91-field recorder log](applications/idle-recorder-91-fields.msl). These are synthetic observations. Spot current can alias PWM, and viewer floating-point IDs are not an exact audit format. Original files and JSON preserve integer text.

## Independent review and remaining work

[Review resolution](review-resolution.md) maps findings to fixes and limits. Immutable records retain the [initial control review](reviews/control/pass1/review.md), [owner review](reviews/owner/review.json), [final image review](reviews/owner/final/review.json), [integration review](reviews/integration/review.md), [plant probes](reviews/plant/) and [hardware review](reviews/hardware/pass2/review.md). The plant reviewer examined four earlier coupled traces, not all 33 published runs. Later publication image/UI differences are bound separately in the validation manifest; earlier review hashes are not relabelled as current.

Review probe scripts and manifests keep their original cache paths. Source snapshots are review records, not alternative production sources. Plant review inputs are losslessly gzip-compressed here; their manifests hash the decompressed original JSON. SDK/application binaries, vendor PDFs, extracted datasheet text and generated native executables are not redistributed. Original cache/source records remain locally intact.

Permanent carrier-side GPIO3 bias, actual module eFuse/JTAG routing, the open actuator-return path through the carrier, external power protection, valve specification, routing, thermal behavior and enclosure fit remain physical release blockers. No board was flashed. There are no measured GPIO voltages, target PWM jitter, stack high-water, minimum heap, real valve/engine behavior or vehicle/environmental qualification. Other Speeduino feature gaps remain open.
