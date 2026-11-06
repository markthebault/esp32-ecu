# Independent ESP32-S3 controller integration diagnostics

Prepared locally on 2026-11-04. Unsent. Intended recipient: support@efianalytics.com. See `request.txt` for the proposed email.

The own controller is `ESP32ECU DEV 009 INHIBITED`. Unmodified TunerStudio MS Lite 3.3.01 accepts its INI/MSQs offline but explicitly rejects it online after valid discovery: 1,640 complete exchanges, 328 unsupported-firmware warnings, no page/runtime reads, writes or burns. The attachment preserves the current INI, raw wire bytes, application debug log, screenshot and session hashes.

The same application JAR connects to a separate genuine pinned Speeduino production parser/loop. That reference retains `speeduino 202504-dev` and its matching INI. The final public bridge records 10,838 complete exchanges, 22 page reads, 10,790 runtime reads, one application write and one burn. Page 2 offset 240 changes from 85 to 86; the next controller CRC is `be04ef33`, matching the full reconstructed page and saved MSQ. Separate reference captures, debug log, screenshot, INI, MSQ and build manifest are included.

The application JAR hash is `3ebafb867fef3722816e768879501845904f81bc5e13249c77d170e9adf61cf8`. Speeduino is pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`, without UNIT_TEST. The native reference binary hash is `c02e74a93744dc1999262ac6b47c99be55f818187f57daa219d8fe4f8a3fd760`. No application executable or proprietary definition PDF is included.

Our own endpoint uses MS-envelope protocol 002, 256-byte chunks, one 8192-byte little-endian calibration page and a 640-byte runtime block. It stages writes and validates/persists/activates the whole tune on burn. Physical engine outputs are compiled out. Own online support remains unresolved; the reference is a separate positive control.

Both tests use private Linux software fixtures. The reference engine is stopped with synthetic static ADC values. This is not a physical USB, engine, flash/power-cycle or vehicle test. Its fake EEPROM is process-local. The serial adapter's queue bounds do not qualify the reference parser against arbitrary malformed lengths.

Gzip captures preserve original bytes. `attachment-manifest.json` in the repository binds ZIP members to packet sources and SHA256. `source-hashes.json` identifies our source snapshots. Debug/session records retain the original private scratch paths and historical PIDs.

Repository diagnosis and reproducible endpoints:
https://github.com/markthebault/esp32-ecu/blob/feature/engine-development-sil/docs/engine-tuning-application.md

The full source-bound evidence packet additionally retains independent sanitizer/provenance/concurrency checks and replay tooling. No message has been sent to EFI Analytics.
