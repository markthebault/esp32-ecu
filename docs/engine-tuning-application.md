# TunerStudio application interoperability

The unmodified **TunerStudio MS Lite3.3.01** now loads, edits and saves the current own011 definition offline. A fresh own011 online trial still reports `Unsupported Controller Firmware` after correct discovery, before reading calibration or runtime. The current [source-bound packet](../reports/engine/tuning-apps-011/README.md) preserves both results. Physical engine outputs remain inhibited.

## Current application evidence

The latest INI has one12288-byte page and1152-byte runtime. Actual GUI edits change open-duty cell0 to13.25%, target cell9 to149.75kPa absolute and feedforward cell18 to31.125%. Both the original application save and a fresh reload/save with the latest editor bounds reconstruct every expected page byte using an explicit known origin7. The202 application-saved constants omit the read-only origin; reconstructed zero/reserved bytes and caller-supplied origin are not additional values saved by the application.

The browser imports the actual edited MSQ, retains its loaded CAS, saves it and re-exports every calibration field through the native validator. Ten Chrome checks also cover competing writers, absent origins and historical migrations. The three bit/enum boost fields now export blank units. The first actual Python-exported file used percent, causing three application warnings; that original failure remains preserved. Binary field values/offsets and identity are unchanged.

The fresh online capture contains1685 complete exchanges:337 rawF,337 I,674 capability and337 signature queries. All lengths/CRCs validate, protocol2/256-byte chunks and the exact own011 signature are observed. The app logs337 matching unsupported-firmware warnings and sends zero page, runtime, write, CRC-page or burn requests. The endpoint and both owned application/display processes close cleanly. Neither a parsed INI nor a correct frame proves supported online operation.

MegaLogViewer HD Lite4.6.14 opens the120-row,245-column MSL008 synthetic control fixture and plots raw BoostDuty/MAP plus BoostTarget and BoostInhibitEngine. The CSV boost values match the corresponding native source observations. This is an authored shared-controller stimulus, without an engine plant or physical output measurement.

A separate actual-app trial opens the300-row,202-column direct-SIL008 file and plots BoostReason with observed extrema6 and8, matching its raw rows. That file comes from the existing unvalidated warm-start regression plant. This trial checks file/field rendering and adds no engine-physics or target acceptance.

**Viewer limitation:** the unmodified app's calculated AFR* summary displays a14,700,000 maximum when the raw file contains ten unavailable Lambda values, even though those tokens areNaN and the validity bit is clear. The raw source values are correct. Treat source/input-valid/feature-available fields and JSON as authoritative; vendor-derived extrema and floating-point counter plots do not establish measurements. Other application releases are unverified.

## Version, identity and the reference control

The inspected EFI download pages list [TunerStudio3.3.01](https://www.efianalytics.com/TunerStudio/download/) and [MegaLogViewer HD4.6.14](https://www.efianalytics.com/MegaLogViewerHD/download/). Those are the installed unmodified versions in this trial, bound by JAR hashes. MLV also offered an update inside its own test profile; that prompt was deferred. No global installation or personal project was changed, and no proprietary executable/PDF is redistributed.

The earlier [own009/reference packet](../reports/engine/tuning-online-009/README.md) remains historical. The same TunerStudio JAR completed actual online page/runtime reads, a VE-cell85→86 edit, burn acknowledgement, matching CRC and saved MSQ against a separate genuine production Speeduino process. Its pin is `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. The native fixture executes the original parser/loop and static synthetic ADC values at stopped-engine RPM0. Its process-local EEPROM does not prove physical persistence or engine timing.

That control establishes that the application can perform the workflow for the genuine reference identity. It does not authorize us to use that identity. Our own signature remains `ESP32ECU DEV 011 INHIBITED`; supported vendor integration is unresolved. The [reviewable request](../tuning/vendor-integration-request.md) and [email draft](../tuning/vendor-integration-email.txt) are local and unsent.

## Reproduce and inspect

Use fresh app copies, fresh Java user profiles, copied test projects and an owned Xvfb display. The archived launch/action scripts, INIs, input/edited files, logs, screenshots, endpoint sources and hashes reproduce this Linux workflow. They never open a physical serial port or restart another display/service. Install the vendor applications separately under their normal terms.

The host `PtyEndpoint` executes the shared native Session/Stream. Its optional `on_wire(direction, bytes)` observer records actual read/write slices, including long replies. Record complete data rather than the128-byte diagnostic preview. Analyze a saved capture with:

```sh
python3 tools/analyze_tuning_wire.py NEW_WIRE.log NEW_ANALYSIS.json --require-complete
```

The analyzer validates split/coalesced envelopes, lengths, CRCs, order and unmatched tails. Captured host bytes do not prove physical delivery or application consumption. The current own011 rejection has a complete captured tail, not an assumed quiet shutdown.

Use [the USB/host guide](engine-usb-tuning.md) for current layout, staging/CAS and module power restrictions. The old own009 verifier continues to verify its frozen historical packet. Current formats, app acceptance and their limits are separate from [engine simulation](engine-research-benchmark.md), target/HIL and the wider [feature goal](engine-feature-coverage.md).
