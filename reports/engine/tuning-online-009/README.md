# Current TunerStudio online diagnosis

The unmodified TunerStudio MS Lite 3.3.01 application rejects our current **ESP32ECU DEV 009 INHIBITED** identity after valid discovery. A separate genuine pinned Speeduino production process completes online reads, an actual VE edit, burn acknowledgement, matching page CRC and saved MSQ through the same application. Our own controller's supported online integration remains unresolved.

| Actual application trial | Own controller | Genuine reference |
|---|---|---|
| Identity | ESP32ECU DEV 009 INHIBITED | speeduino 202504-dev |
| Complete valid exchanges | 1,640 | 10,838 |
| Unsupported-firmware warnings | 328 | 0 |
| Calibration/runtime requests | 0 / 0 | 22 / 10,790 |
| Application write/burn | 0 / 0 | 1 / 1 |
| Saved online edit | Unavailable | Page 2 offset 240, 85 to 86; CRC be04ef33 |

Both trials use the same unmodified application JAR, SHA256 `3ebafb867fef3722816e768879501845904f81bc5e13249c77d170e9adf61cf8`. The current own INI matches the tested definition. The separate reference uses its genuine pinned INI and production parser/loop from Speeduino commit `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`, without UNIT_TEST. No application executable or proprietary definition PDF is distributed here.

## Inspect and reproduce

`own/` preserves the rejected current trial. `reference/` preserves the final public `SpeeduinoPtyEndpoint` trial, complete wire and native event captures, actual application debug log, screenshots and application-saved MSQ. Gzip files contain the exact original bytes. Session paths and PIDs are retained historical observations; they are not new launch targets.

`sources/` and `summary.json` bind the implementation, own-controller headers/transport, current definition, guides and verifier to this checkpoint. `upstream/` preserves selected inspected production source and its license. The serial manifest records hashes of all 565 original build inputs. It does not redistribute the complete build cache.

`reviews/revision001..005/` contain selected original independent review records and probe source. They retain findings, resolved findings and original scratch paths. Historical scratch executables, object trees and redundant application copies are omitted. Revision 005 accepts the final six implementation files and the closed captures. `reviews/publication-review.json` independently binds the published guides, verifier and packet claims. Review acceptance applies to this serial fixture and evidence scope, not full ECU parity.

From the repository root:

```sh
python3 tools/verify_tuning_online_evidence.py --replay
```

This validates artifact/source hashes and reviews, reassembles both saved streams, reconstructs the complete changed 288-byte VE page against the saved MSQ and controller CRC, reruns the frozen own Session/Stream probe under ASan/UBSan, and runs four capture-analysis tests. Add `--check-live-sources` to require an unchanged checkout. Replay does not launch TunerStudio or reexecute the native production reference; [the application guide](../../../docs/engine-tuning-application.md) gives separate build/PTY instructions for a fresh trial.

`validation/` retains the final exact-relink build log, 221 passing Python tests, 16 new serial/capture tests and the numerical-reference noninterference receipt. No firmware, controller identity, calibration layout or PCB changed in this increment. The own protocol remains schema 8/own009 with an 8192-byte calibration page, 640-byte runtime and physical engine writes inhibited.

## Interpretation and open work

The serial fixture replaces only host transport/clock scaffolding. It relinks all 109 original numerical objects to the exact attested benchmark hash, then reuses 107 production objects with its separate entry point and bounded 600 s clock copy. Independent negative controls reject a modified cached communications object and verify lock, concurrent trace, queue and closure behavior. The numerical 16/32-bit benchmark binaries, their manifests and the external production checkout remain unchanged.

The reference uses static synthetic ADC inputs and RPM 0. Its write changes RAM immediately; burn acknowledges the production fake-EEPROM path. This does not establish physical flash persistence or restart recovery. Closure `stats` is the last requested snapshot; the complete wire and native events establish final TX accounting of 752,363 bytes. Host-observed bytes do not establish physical delivery or application consumption.

The bounded RX/TX queues do not repair the pinned production parser's unchecked payload-length path. This reference fixture is scoped to owned valid application traffic and specific small timeout/CRC probes. Our separate bounded Session/Stream has its own independent sanitizer checks. Reconnect refresh/stale-client behavior remains an application integration test to perform once our own identity is accepted.

Supported own-controller onboarding, online calibration workflows, physical ESP32 USB/load/timing, flash/power loss, running-engine behavior and full Speeduino feature parity remain open. The [local vendor request](../../../tuning/vendor-integration-request.md) and [diagnostic ZIP](vendor-support.zip) have not been sent. The ZIP is a reviewable support attachment with hashes and no application binary.
