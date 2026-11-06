# Shared development tuning transport

The current definition is **own012 / schema11**, identity `ESP32ECU DEV 012 INHIBITED`. Actual TunerStudio3.3.01 offline checks include C8 fuel/spark edits and a complete12288-byte page reconstruction. One to eight logical cylinders are available; fitted hardware remains4+4 and engine outputs remain inhibited. [Cylinder integration](engine-cylinder-profiles.md) describes its boundaries. The latest observed online rejection is own011; supported own012 online acceptance remains unverified. [Application evidence](engine-tuning-application.md).

## Connection and ownership

The selected N16R8, generic A3 and flex-development web builds contain a dedicated native USB Serial/JTAG service on GPIO19/20. Confirm the actual purchased module's port routing. UART0 on GPIO43/44 remains the diagnostic console and prints the random web password; binary tuning does not share it.

Follow the [module power restriction](web-configuration.md): remove the unpowered module from the carrier before USB power. Never combine USB power with carrier3V3. The NC module5V pad does not qualify simultaneous power. A removed module cannot acquire carrier sensors. Use the web service for powered-carrier monitoring; simultaneous powered-carrier USB tuning needs a separately designed and tested power path.

J3 must be open at startup. USB tuning cannot be combined with legacy bench pulses or the dummy-load engine build; selected engine writes are compiled out. No file can enable them. No new connector or case/power-path release is implied.

The host TCP/PTY endpoints execute the same portable Session/Stream against a synthetic store. They are not physical USB/UART. Use new state files, free ports and fresh PTY paths; do not replace another running endpoint.

## Current layout

Raw/framed `F` returns serial protocol `002`; `f` advertises protocol2 and256-byte chunks. MS-envelope lengths/CRC32 are big-endian; calibration/runtime values are little-endian. The [layout manifest](../tuning/protocol-layout.json) and [INI](../tuning/esp32-ecu-profiles.ini) describe the current12288-byte page and1152-byte runtime.

| Page1 region | Offset | Bytes |
| --- | ---: | ---: |
| Flags, general curves, origin, strategy and timing | 0 | 512 |
| VE / spark / lambda maps | 512 | 3456 |
| Cylinder maps and trim metadata | 3968 | 800 |
| Idle | 4768 | 224 |
| Transient settings | 4992 | 128 |
| Load/pressure/AFR plus reserved tail | 5120 | 256 |
| Secondary rules/maps plus reserved regions | 5376 | 2432 |
| Flex plus reserved tail | 7808 | 384 |
| Boost options/scalars plus reserved gap | 8192 | 128 |
| Boost open-duty RPM/TPS table | 8320 | 320 |
| Boost target RPM/TPS table | 8640 | 320 |
| Boost feedforward RPM/target-pressure table | 8960 | 320 |
| C5–8 firing-order positions | 9280 | 4 |
| C5–8 fuel maps | 9284 | 768 |
| C5–8 spark offsets | 10052 | 16 |
| Reserved zero tail | 10068 | 2220 |

The runtime retains the896-byte own011 prefix and appends proposal/worker counts, fitted4+4 capacity, full32-bit masks and C5–8 proposals at896..984, with a zero tail to1152. A full reply is1159 framed bytes. **That exceeds each1024-byte target USB ring.** The writer handles incremental enqueue/retry; the nominal2ms budget and host PTY tests do not prove real target throughput or scheduling under flash/RF/ISR load. Do not retain the old839-byte within-ring claim.

## Staging, revision and diagnostics

One whole page avoids automatic inter-page burns splitting valid transitions. `M` modifies staging. Successful `b` validates the entire tune, repeats backend CAS, persists, activates, resets control and reacquires phase. TunerStudio may burn when a dialog closes. This is development configuration, not seamless hot tuning.

The origin at268 is read-only and stable until rediscovery. Active revision and expected backend revision are separate channels. Clean burns are idempotent only while that backend revision still matches. Another writer causes conflict84, including a clean session, rather than rebasing cached values.

Read-only/reserved-byte changes reject the complete write chunk. Invalid tunes retain staged edits and active calibration. Conflict, invalid tune and storage-blocked replies use84; temporary contention/allocation failure85; burn success04. Storage failure preserves active calibration and blocks later saves. A configuration fence can cut virtual outputs before a failed save. The separate NVS source/power-loss model is documented in [boost development](engine-boost-development.md).

Idle raw `F`, optionally prefixed byF0, discards staging and opens a current session. Framed discovery does not reset it. Incomplete frames expire after25ms and report80; CRC errors report82 without executing. Failed reply queueing stops commands until raw rediscovery. USB loss abandons staging. SOF indicates host-bus presence, including an unopened port, rather than an application connection.

The web Engine development page exposes read-only diagnostics at `/api/engine/tuning`: revisions, staged state, CRC/framing/timeouts, burn/rejection counts, observed task timing and unknown driver RX drops. Host sessions remain separate. Source codes differ: tuning runtime0/1/2 means none/synthetic/target, while coherent JSON/MSL0/1/2 means none/target/synthetic.

TunerStudio-saved MSQs omit origin metadata. Browser imports keep the editor's loaded CAS and require an explicit save. Python import can use an explicit known `base_revision`; default1 is an offline placeholder. Other ECU identities are rejected. Legacy files migrate with neutral absent features. Current editor limits constrain33 scalars/six curves/three timing fields; coupled conditions still require whole-tune validation.

## Source budgets and reproduction

The target task uses CPU0, priority1, a12288-byte stack,1024-byte RX/TX rings,64-byte reads, a tick yield and nominal2ms send retry. These are source budgets, not measured minimum heap, stack high-water or latency. The pinned project-local USB driver fixes one TX allocation check; its ISR remains in flash and can pause during flash work. [Driver source and provenance](../firmware/components/esp_driver_usb_serial_jtag/README.md). UART-only console defaults suppress normal SDK output on binary USB; ROM/boot/panic traffic remains unmeasured.

```sh
python3 scripts/generate_tunerstudio_ini.py
CXX=g++ CC=gcc uv run --with numpy --with fmpy==0.3.26 python3 -m unittest discover -s tools -p 'test_tuning*.py'
uv run --with playwright --with numpy --with fmpy==0.3.26 python3 tools/test_tuning_ui.py --report-dir .cache/engine/NEW-UI
```

`PtyEndpoint(store, fresh_path, on_wire=observer)` can observe complete actual host RX/TX slices. The optional callback receives `(direction, bytes)`, including partial writes; ordinary debug prints still truncate previews. Keep captures bounded and analyze them with `tools/analyze_tuning_wire.py --require-complete`. Host writes do not establish application consumption or physical delivery. The current regression captures an entire1159-byte reply across31-byte OS writes and validates its CRC.

[Earlier application packet](../reports/engine/tuning-apps-011/README.md) retains actual own011 files, full-page/native/browser checks, current raw rejection and MSL008 plots. [Historical USB packet](../reports/engine/tuning-usb/) retains earlier own004 evidence; [own009 diagnosis](../reports/engine/tuning-online-009/) remains immutable. Engine comparisons and target timing have separate scopes. Supported online onboarding, physical USB/power/load/HIL and [wider ECU features](engine-feature-coverage.md) remain unfinished. The vendor draft is local and unsent.
