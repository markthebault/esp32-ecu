# Sensor calibration and storage checkpoint

Optional ratiometric linear/table conversion now compensates a sensor signal using the measured SENSOR_5V rail and its curve reference supply. All defaults and legacy migrations keep it Off. Raw voltages and electrical fault checks remain absolute; display samples normalize before filtering, while engine input binding uses instantaneous conversion. Engine rail/freshness limits and physical output inhibition are unchanged.

[Usage, limits and reproduction](../../../docs/sensor-ratiometric.md) · [Independent review](independent-review.json) · [Source/build manifest](manifest.json) · [Browser checks](ui-tests.json)

Sensor profile2 explicitly stores both new fields for every sensor. Boot normalizes valid profile1 only in RAM. A successful explicit device save uses bounded blob storage under a separate key and retains the old string. This fixes a reviewed 3,775-byte legacy profile expanding to 4,033 bytes, beyond the SDK's string ceiling. Present invalid blobs block saving; device commit errors preserve runtime and block retries until restart/inspection. The shared 24 KiB NVS partition and all offsets stay unchanged; space, wear, SDK recovery and power-loss behavior remain physical test requirements.

| Evidence | Result |
| --- | --- |
| Shared C++ parser/filter/engine binding/controller, ASan/UBSan |93 checks pass|
| Actual storage helper/parser, native NVS API model |60 checks pass|
| Configuration/API + focused ratio/storage host suites |20 +10 tests pass|
| Engine + engine HTTP + existing radio regressions |21 +7 +8 tests pass|
| Chrome editor/migration/legacy-backend/viewports |8 grouped checks pass, including current unit-label assertions|
| Actual frozen legacy conversion replay |12288 bit-identical readings across 2,048 raw vectors, ratio Off|
| Actual pinned production Speeduino MAP acquisition |8 declared raw-ADC/reference cases pass|
| Final current firmware |3 web environments build; exact BINs/ELFs and embedded UI/defaults/guide retained|

The Speeduino fixture's five common-reference cases return 51 kPa for an authored true 52 kPa signal, reflecting integer conversion. A separate sensor-only drop is not cancelled by unchanged AVCC. Our optional ratio conversion preserves this fixture within declared 12-bit quantization. This comparison exercises production MAP acquisition/conversion, with authored ADC/reference relationships. It does not establish ADC hardware accuracy, full-engine equivalence or a property of every Speeduino board.

The independent reviewer exercised 40,049 core/parser/allocation assertions, 33 actual ESP-NOW publication assertions, 16 actual firmware boot/filter assertions, 14 actual save-handler assertions and 7 Chrome checks using actual host sampling. The review found the NVS migration regression and verified its fix. It also reran the legacy/reference checks and verified the reviewed build's exact artifacts/embedded UI.

[Post-review follow-up](post-review-followup.json) records a small subsequent unit-label refresh and confirmation reset, with matching browser assertions and fresh firmware builds. The independent review was not rewritten to imply it checked that later change. The exact earlier review sources/builds and the final sources/builds are both retained. [Exact follow-up diff](post-review-unit-label.patch).

Archives contain the current project source snapshot, whitelisted independent probe sources/fakes/results, authored checks and exact firmware BIN/compressed-ELF payloads. Linked Speeduino executables, per-user instruction contents and vendor PDFs are excluded. Absolute paths in recorded probe commands may need adjustment in another workspace. The production fixture builder requires the existing attested native reference cache; the wider [engine development guide](../../../docs/engine-development.md) describes its source pin and build groundwork.

```sh
python3 -B tools/verify_sensor_evidence.py
python3 -B tools/verify_sensor_evidence.py --current
```

The default verifies the frozen checkpoint even after later development. `--current` additionally requires its bound sources to match the working tree.

The unfinished nonideal circuit convergence study and its experimental tools/data are excluded from this packet's acceptance claims. All physical engine outputs remain disabled. Physical sensor/ADC/timing/flash/load/RF/thermal/EMI/surge/fit/engine tests, online TunerStudio support and the wider [Speeduino feature gaps](../../../docs/engine-feature-coverage.md) remain open.
