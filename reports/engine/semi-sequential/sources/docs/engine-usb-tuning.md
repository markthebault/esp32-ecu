# Shared development tuning transport

The selected N16R8 and generic A3 web builds now include a dedicated native USB Serial/JTAG tuning service. The host TCP/PTY tools execute the same portable C++ Session/Stream. The tested TunerStudio 3.3.01 accepts our definition and offline MSQs but rejects our own controller identity for online use. This transport is an implemented development interface; it does not establish online application compatibility or physical USB qualification.

## Connection and ownership

Use the ESP32-S3 module's native USB Type-C connection on GPIO19/20. The other module Type-C connection may be a USB-to-UART bridge; confirm the actual purchased board's routing before using it. UART0 on GPIO43/44 remains the diagnostic console and prints the random web-service password. Binary tuning never shares that console. The carrier does not allocate GPIO19/20 to other interfaces. No new carrier connector, Gerber, enclosure opening or physical-fit claim is introduced here.

J3 must be open at startup. The service is compiled only into `compact_n16r8_web` and `compact_a3_web`, with physical engine outputs inhibited. Combining it with legacy bench pulses or the dummy-load engine build is a compile error. The separate dummy-load environment omits the USB tuning task. No configuration file can enable physical writes in the selected build.

`CONFIG_ESP_CONSOLE_SECONDARY_NONE=y` prevents SDK console messages from also using binary USB. The prebuild script normalizes generated Linux sdkconfigs and retains their original bytes in the ignored task cache. Legacy symlinks are preserved and rejected for this normalization. Fresh builds use the same tracked defaults. ROM/boot/panic traffic still needs observation on the real board.

The task runs at priority 1 on CPU0 with a 12,288-byte stack, 1024-byte RX/TX driver rings, 64-byte read slices and a mandatory tick yield. A reply is queued with a nominal 2 ms retry budget; scheduling/yield delays can extend elapsed time. Diagnostics expose observed maximum slice duration. These are source budgets, not measured minimum heap, stack high-water, throughput or timing guarantees.

The project-local pinned ESP-IDF USB component fixes one TX-ring allocation check. The original SDK installation remains unchanged. [Source hashes, license and patch](../firmware/components/esp_driver_usb_serial_jtag/README.md) are retained. Its USB ISR remains in flash with flags 0 and can pause during flash operations. The engine ISR placement audit does not certify USB ISR behavior. RX driver overflow has no exposed counter and is reported as unknown.

## Layout and commits

The controller signature is `ESP32ECU DEV 005 INHIBITED`. Raw and framed `F` return serial protocol `002`; `f` advertises protocol 2 with 256-byte data chunks. The MS-envelope uses a big-endian length and CRC32 around command payloads. Calibration and runtime values are little-endian. [Layout manifest](../tuning/protocol-layout.json) and [current INI](../tuning/esp32-ecu-idle.ini) match the shared generated codec.

| Page 1 region | Offset | Bytes |
| --- | ---: | ---: |
| Flags, numbers, curves, origin, strategy and timing | 0 | 512 |
| VE axes and map | 512 | 1152 |
| Spark axes and map | 1664 | 1152 |
| Lambda axes and map | 2816 | 1152 |
| Four physical-cylinder trim maps, spark offsets and enable | 3968 | 800 |
| Idle algorithm, scalars, curves and reserved tail | 4768 | 224 |

One complete 4992-byte page avoids TunerStudio's automatic burn between pages splitting a valid strategy/trim transition. `M` modifies staged bytes only. A successful `b` validates the complete native tune, repeats the atomic backend revision check, persists, activates, resets controller state and reacquires phase. It can happen automatically when a dialog closes. It is not a promise of seamless hot tuning or a separate manual-only apply step.

The mapped origin revision at offset 268 is read-only and remains byte-for-byte stable until explicit rediscovery. A successful burn advances only the internal expected backend revision and active revision. Thus CRCs do not change behind an application's cache. Repeated clean burns are idempotent only while the backend revision still matches. An HTTP/other-session save causes permanent conflict 84 even for a clean session; it never silently rebases cached values.

Changed read-only/reserved bytes reject the entire write chunk. Invalid whole tunes retain both staged edits and the active tune. Conflict, invalid tune and storage-blocked conditions return 84; temporary contention/allocation failure returns 85. Successful burn returns 04. Persistence failure retains active calibration, closes the configuration fence at the old revision and blocks further saves until restart/inspection. The fence may deliberately cut virtual outputs before a failed flash operation; retaining calibration does not imply uninterrupted execution.

Preparation uses checked owned text and typed tune allocations. USB commit avoids unchecked project-side string allocation. Independent failure injection covers cJSON allocation positions and the checked document copy, final-CAS races and NVS API failures. It does not cover every internal SDK allocation or physical flash/power-loss behavior. Existing boot-load and HTTP-response string allocation limits are outside that USB commit result.

An idle raw `F`, optionally prefixed by `F0`, explicitly discards staged edits and opens a current session. Framed `F` and ordinary queries do not reset it. A 25 ms intercharacter timeout discards an incomplete frame and reports 80. CRC errors report 82 without executing commands. A failed reply queue stops further command execution until idle raw discovery. USB bus loss abandons staged state. USB SOF indicates a present host bus, including an unopened port, so diagnostics never label it an application connection.

## Runtime and UI

The runtime block is 256 bytes. The existing 184-byte proposal/phase/cylinder layout is retained, followed by:

| Offset | U32 value |
| ---: | --- |
| 184 | Observed active revision, 0 if unavailable |
| 188 | Stable session-origin revision |
| 192 | Internal expected backend revision |
| 196 | Staged dirty flag |
| 200 | Write state: ready 0, staged 1, conflict 2, storage-blocked 3, busy 4, invalid 5, unavailable 6 |
| 204 | Last command result before this runtime read |
| 208 | Input-valid mask |
| 212 | Coherent observation flags |

Own005 appends six F32 values at 216..239: target, feedforward, P, I, D and proposed duty. U32 flags/state/reason/algorithm occupy 240..255. Flags bit 8 supplies `iacAvailable`; missing idle data must not appear as a valid zero. Source/age and availability are logged explicitly. The 216-byte prefix and historical own004 definition remain records.

Sample revision at 56 is independent of active/session revisions. A save clears the old completed control observation. An absent sample has `hasResult=0` and unknown age; zeros are not a measurement. This wire's source codes retain the older domain: 0 none, 1 completed synthetic, 2 target. JSON/radio `DataSource` codes use a different domain: 0 none, 1 target, 2 synthetic. Do not interchange them. A target observation is still a software proposal, not proof of a pin transition.

The Engine development page has authenticated read-only tuning diagnostics and JSON export at `/api/engine/tuning`. It shows state, revisions, burn/rejection counters, CRC/timeouts/framing/TX errors, bus-presence meaning and unknown driver drops. Multiple host sessions are exported separately; they are not presented as one connected screen or a real USB device.

Own004/005 MSQ origin is metadata. The browser displays it and retains the editor's already-loaded revision for the normal Save CAS. An intervening writer still causes 409. Saving is explicit after review. TunerStudio omits the read-only origin from its saved MSQ. The browser shows it as unavailable and retains the loaded editor revision. Python import accepts an explicit already-loaded `base_revision`; without one it uses revision 1 as an offline placeholder, never a discovered current revision. Exact historical own001/002/003/004 MSQs remain importable, with their existing revision guards and neutral migration of absent features. Other ECU identities are rejected. Engine JSON is schema 4; historical engine JSON/MSQs migrate with new idle disabled.

## Reproduction and evidence

```sh
python3 scripts/generate_tuning_wire.py
python3 scripts/generate_tunerstudio_ini.py
python3 scripts/embed_web.py
CXX=g++ sh scripts/test_firmware.sh
uv run --with playwright --with 'fmpy==0.3.26' python -m unittest discover -s tools -p 'test_*.py'
uv run --with playwright python tools/test_tuning_ui.py
uv run --with 'fmpy==0.3.26' python tools/run_tuning_scenarios.py
pio run -d firmware -e compact_n16r8_web
python3 scripts/audit_tuning_build.py compact_n16r8_web NEW_OUTPUT.json
```

Use new output paths when preserving a published run. [Evidence](../reports/engine/tuning-usb/) binds reviewed sources, application logs/wire captures, native tests, Chrome checks, nine before-start plant comparisons and three firmware builds. The external benchmark uses the hash-verified MVEM air path plus local uncalibrated combustion/free shaft, with actual pinned Speeduino production control in a zero-CPU-cost native HAL. The different fuel/deadtime policies and wrong-cylinder negative control remain explicit. USB commits during a running plant are not modeled by this benchmark; real service configuration fences are separately exercised with fakes.

[Prepared vendor request](../tuning/vendor-integration-request.md) remains unsent. Full Speeduino feature parity, target/HIL measurements and vehicle electrical/environmental qualification remain open in the [coverage ledger](engine-feature-coverage.md).

The [idle increment](engine-idle-control.md) records own005 offline application edits, 91-field bounded engine logging, 48-field direct SIL logging and current validation. Historical USB evidence in the directory above remains unchanged.

The [semi-sequential increment](engine-semi-sequential.md) adds the current schema5/own006 strategy and negotiated engine-radio schema2. Earlier identities/evidence described here remain historical records; byte offsets, CAS, bounded logging and selected physical-output inhibition are retained.
