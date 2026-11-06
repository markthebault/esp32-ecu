# TunerStudio online diagnosis

The unmodified TunerStudio MS Lite 3.3.01 application rejects the current `ESP32ECU DEV 009 INHIBITED` identity after valid discovery, before reading calibration or runtime. The same application completes online reads, a VE-cell edit, burn acknowledgement and MSQ export against a separate genuine production Speeduino reference. This establishes a reproducible application-integration gate. It does not make our own controller supported online.

EFI's [current stable download](https://www.efianalytics.com/TunerStudio/download/) lists 3.3.01 for Linux. Its [additional-controller support FAQ](https://tunerstudio.com/index.php?Itemid=38&id=24&option=com_content&view=article) describes coordination through the hardware vendor. The [prepared integration request](../tuning/vendor-integration-request.md) remains local and unsent. The next support step is to establish the supported process for our own identity and verify the resulting integration in the application.

## Application evidence

[The source-bound packet](../reports/engine/tuning-online-009/README.md) preserves the actual application logs, raw captures, INIs, screenshots, reference MSQ, independent probes and hashes. No application executable or proprietary definition PDF is redistributed.

Verify the archived evidence with `python3 tools/verify_tuning_online_evidence.py --replay`. This rechecks both saved streams, reconstructs the changed page and saved MSQ, and reruns the frozen own-controller sanitizer probe and capture-analysis tests. It does not relaunch the proprietary application or establish physical behavior. Add `--check-live-sources` only when the live files still match this checkpoint.

For own009, the capture contains 1,640 complete request/reply exchanges: 328 raw F, 328 I, 656 capability queries and 328 signature queries. All framed lengths and CRCs validate. The application reports 328 unsupported-firmware warnings and sends zero page, runtime, write, CRC-page or burn requests. This is a current own009 trial, distinct from the historical own003/004 rejection records. Offline own009 editing/import behavior remains independently tested.

The final public reference bridge captures 10,838 complete exchanges: discovery/version queries, 18 page CRCs, 22 page reads, 10,790 runtime reads, one write and one burn. The source is the unchanged pinned Speeduino production parser, loop and definition. Its active identity is `speeduino 202504-dev`; it is a separate reference ECU process. The application displays the synthetic MAP 100 kPa, IAT 24°C and CLT 85°C with RPM 0. An actual application edit changes page 2 offset 240 from 85 to 86. Write returns 00, burn returns 04 and the next controller CRC is `be04ef33`. Independently reconstructed page bytes and the application-saved 256-cell VE array match that result.

The native fake EEPROM is process-local. The burn result demonstrates production API behavior and acknowledgement, not physical flash persistence or a tested power cycle. The reference calibration is a software fixture, not an engine tune to install.

## Reference serial fixture

`scripts/build_speeduino_serial.py` uses the existing pinned 32-bit numerical build. It holds the numerical build lock, relinks all 109 original objects with their original archives and requires a byte-identical original executable. It checks 565 original source/header/library/object inputs before and after compilation. The serial fixture then reuses 107 production objects and compiles its own entry point and bounded 600 s clock copy. Source/binary hashes, exact relink proof and compiler flags remain available in its manifest. The numerical benchmark binaries, manifests and source adapter stay unchanged.

The serial-only executable uses distinct bounded 16 KiB RX/TX queues. A reader can supply later byte slices while the production parser waits for a length or CRC. Inherited `Print` output, including raw F, enters the same captured TX queue. Wall-clock `micros`/`millis` let production 400 ms receive deadlines expire; virtual timer callbacks catch up between loops. These are stopped-engine serial semantics, not a CPU-cost, engine-plant, UART-bandwidth or interrupt-latency model.

The public PTY bridge relays raw bytes, uses bounded nonblocking writes and closes only its owned processes, descriptors and symlink. Concurrent API senders record RX in actual pipe order. Source controls and the exact original benchmark hash prevent stale production objects from silently entering a new build. Reference quirks remain visible, including extra unspecified bytes in the pinned I reply. They are not copied into our own protocol as requirements.

The 16 KiB queues bound fixture storage. They do not repair the reference parser's unchecked payload-length path. This positive control uses owned, valid application traffic and specific small CRC/timeout probes. It is not a general malformed-packet safety claim. Our separate Session/Stream has its own bounded frame validation and sanitizer evidence.

## Capture and reproduce

Use fresh paths and a copied application/project profile. Keep the actual controller identities and matching definitions.

```sh
python3 scripts/build_speeduino_sim.py --source ../speeduino --timer-bits 32
python3 scripts/build_speeduino_serial.py --source ../speeduino
PYTHONPATH=tools python3 -m unittest tools.test_speeduino_serial tools.test_tuning_wire_analysis
```

The reference PTY API is deliberately separate from the project endpoint:

```python
from pathlib import Path
from speeduino_serial_runtime import SpeeduinoPtyEndpoint

with SpeeduinoPtyEndpoint(Path(".cache/engine/new-reference-pty")) as endpoint:
    print(endpoint.link)  # Configure the isolated application to use this PTY.
    input("Press Enter after closing the test application: ")
```

Run that snippet with `PYTHONPATH=tools`, use the pinned reference INI, and close the test within the 600 s native fixture bound. It opens a Linux PTY, never a physical serial port. The project's separate endpoint is `tools/tuning_server.py`; [USB tuning](engine-usb-tuning.md) documents its whole-tune semantics and physical wiring limits.

`on_wire(direction, bytes)` can record the raw RX/TX slices. Keep captures bounded and preserve their original bytes. Audit a capture with:

```sh
python3 tools/analyze_tuning_wire.py NEW_WIRE.log NEW_ANALYSIS.json --require-complete
```

The analyzer reassembles split/coalesced envelopes, validates lengths/CRCs, reports command counts and capabilities, and rejects response bytes that precede any queued request. Incomplete requests, unmatched replies and shutdown tails remain explicit. These are host-observed byte records, not proof of physical delivery or application consumption. Native closure `stats` is the last explicitly requested diagnostic snapshot; use the complete wire record for final byte accounting.

Independent review covers the own009 rejection, original object binding, unchanged numerical reference, concurrent trace ordering, queue/closure behavior, full-page CRC, source-derived runtime values, actual application edit/burn/MSQ and capture-analysis negative controls. The firmware/INI contract remains schema 8/own009 with outputs inhibited. Supported own-controller online acceptance, physical USB/runtime measurements and wider ECU feature parity remain open.
