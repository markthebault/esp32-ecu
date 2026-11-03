# Tuning interoperability

The project has its own identity: **ESP32ECU SIL 001 INHIBITED**. It does not identify as Speeduino or MegaSquirt. Their tunes and INIs are incompatible with this layout.

## Supported file workflow

TunerStudio MS Lite 3.3.01 was installed from the official archive and tested with the generated `esp32-ecu-sil.ini`. Offline settings, curves and 16×16 maps load. An actual GUI edit from VE 85 to 86 was saved and read back through our native validator; nonuniform cells 92.5 and 90.1 verified map orientation. The [application-authored fixture](examples/tunerstudio-roundtrip.msq) is test data, not a physical engine tune.

1. Export an MSQ from the web **Engine development** page.
2. Create a TunerStudio test project with this INI, select **Work Offline**, then load that MSQ.
3. Edit the tune and use **Save Tune As**.
4. Import the saved MSQ in the web engine page. Review the imported edits, then save. The normal validator, revision check and physical-output inhibition still apply.

Use a fresh export when the saved revision changes. Stale MSQs are rejected. The UI also imports/exports the project's JSON format. CLI conversion preserves the same layout:

```sh
python3 tools/engine_msq.py config/engine/defaults.json /tmp/ecu-development.msq
python3 tools/engine_msq.py /tmp/ecu-development-edited.msq /tmp/ecu-development-edited.json
python3 scripts/generate_tunerstudio_ini.py
```

The converter refuses to overwrite an existing output. Import is limited to 64 KiB, rejects foreign signatures, unknown/duplicate/missing constants, unsafe XML declarations, invalid numbers and invalid native tune values. `baseRevision` is persisted losslessly in the MSQ. This does not enable outputs.

## Online prototype and current limitation

The local development transport implements CRC32 MS-envelope queries, capability/CAN-ID discovery, chunked page read/write, page CRC, transactional burn and historical output snapshots. [Protocol layout](protocol-layout.json) defines four pages and the 76-byte snapshot. Page values are little endian; envelope length/CRC are big endian.

Calibration is pinned to each connection's snapshot. Another HTTP/tuning writer causes burn conflict, even if the stale client had not started editing yet. Reconnect after another writer. Live/status polling never advances the calibration base. All pages commit together through EngineStore's validator/revision/storage path.

```sh
python3 tools/web_server.py --port 8765 --tuner-port 29000 --tuner-pty .cache/engine/tuner-serial
```

The endpoints share the web store in this process. TCP binds `127.0.0.1`. The PTY is a host test serial device, not an ESP32 UART. Its link must not exist before startup. The standalone `tools/tuning_server.py` uses a separate store and can serve a completed SIL snapshot.

**Actual TunerStudio live connection is not working.** The tested application reads the own signature and capability responses, then logs `Unsupported Controller Firmware: ESP32ECU SIL 001 INHIBITED` and remains disconnected. Wire tests do not establish desktop online compatibility. A supported own-controller integration with EFI Analytics must be resolved. No other ECU identity, application patch or license bypass is used.

There is no target binary serial transport in this increment. UART0 already carries diagnostic/AP password output; sharing it with a tuning protocol would corrupt framing. A separate reviewed USB CDC/UART transport and target integration are future work.

The output block identifies completed historical SIL data, source, tune revision, age, completion and result presence. It is not real-time engine telemetry. The web UI explicitly labels the completed snapshot. Physical outputs always report inhibited.

## MegaLogViewer HD logs

MegaLogViewer HD Lite 4.6.14 was installed unchanged from the official archive. It opens and plots an actual UI-exported MSL: 600 rows, 13 source fields plus its calculated field. The [desktop check](../reports/engine/megalogviewer-sil-log.png) shows synthetic data.

Run a SIL scenario and choose **Export MSL log**. Logs include a simulation warning and Time, RPM, MAP, TPS, lambda, pulse width, advance, dwell, VE, lambda target, EGO, faults and synchronization. Raw trigger/output edge JSON and timing metrics are in cached scenario evidence. These are simulation records, not physical ECU measurements. Real target logging and TunerStudio high-speed tooth/composite logger integration remain missing.

[Source/download checksums](../reports/engine/sources.json) record installed versions. Commercial binaries are outside this repository. No registration was purchased and optional commercial features have not been tested.

## Verification

```sh
python3 tools/test_engine.py
python3 tools/test_engine_http.py
uv run --with playwright python3 tools/test_engine_ui.py
```

These cover native validation, persistence, stale clean/dirty writers, TCP/PTY fragmentation/CRC, offline file exchange, UI saves/imports, delayed-response navigation and responsive layouts. [Independent review](../reports/engine/independent-stall-interop-review.md) and [UI results](../reports/engine/ui-tests.json) state the scope and limitations.
