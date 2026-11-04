# Tuning and log interoperability

Use [esp32-ecu-secondary.ini](esp32-ecu-secondary.ini) for the current own009 development layout. Offline MSQ editing/export and MegaLogViewer MSL workflows work in the tested applications. **Earlier TunerStudio3.3.01 online trials rejected our own controller identity; own009 online acceptance is unverified.** The shared binary transport and dedicated target USB service do not remove that application gate. Vendor integration remains open.

The current identity is `ESP32ECU DEV 009 INHIBITED`. Serial protocol discovery returns `002`, independently of the tune layout revision. One8192-byte page stages the complete tune; any successful burn validates, persists and activates it, resets control and reacquires phase. This is development configuration, not seamless hot tuning. Physical outputs remain inhibited in the selected build.

[USB tuning guide](../docs/engine-usb-tuning.md) describes wiring/port selection, revision semantics, diagnostics, reproduction and physical limitations. [Vendor integration request](vendor-integration-request.md) is prepared locally and has not been sent.

Retained own001..008 INIs and application-saved MSQs are historical definitions and import fixtures. The browser/Python importer accepts all nine exact identities, with explicit neutral migration of absent fields. Current exports use own009. Other controllers' tune files are rejected.

Own004..009 `baseRevision` is read-only session-origin metadata. Active/backend revisions are separate runtime channels. TunerStudio omits the read-only origin from saved MSQs. Browser import displays that origin as unavailable and saves against the editor's loaded revision; a competing writer still causes 409. Python import uses an explicit `base_revision` when supplied, otherwise revision 1 is an offline placeholder. Legacy imports retain their strict matching-revision behavior.

```sh
python3 scripts/generate_tuning_wire.py
python3 scripts/generate_tunerstudio_ini.py
python3 tools/engine_msq.py INPUT.json NEW_OUTPUT.msq
python3 tools/web_server.py --tuner-port 29000 --tuner-pty .cache/engine/NEW-PTY
```

Use free ports/new PTY paths and one owning process per state file. These host endpoints share the web simulator's store and execute the target's portable C++ tuning Session/Stream. They do not attach to target hardware. Host runtime reads identify completed synthetic observations, their age and validity; saves clear the old control sample.

MSL exports retain the engine/trigger source labels and are usable in the tested MegaLogViewer HD 4.6.14. The current bounded engine log has188 fields; direct SIL has145. App plots, source/age/validity handling and the derived lambda-display caveat are recorded in [observability documentation](../docs/engine-observability.md). USB tuning does not add autotune or TunerStudio high-speed logging.

[Idle control](../docs/engine-idle-control.md) adds versioned coolant/duty curves, normalized gains, state/gate diagnostics and an actual own005 application-saved fixture. Older own001..004 imports disable the new idle path. Its historical direct SIL export had48 fields, including separate PWM and synthetic valve observations. Current MSL006 retains those fields, and radio schemas1/2 retain their232-byte layouts.

Own006 adds selectable timed semi-sequential at enum2 (offset272), with the same4992-byte page and256-byte live block. Historic [own005 idle definition](esp32-ecu-idle.ini) and its fixtures remain unchanged. Old identities cannot represent mode2. JSON4 and own005 files preserve idle and trim values during migration; JSON1..3 and own001..004 retain the disabled-idle migration. [Strategy, wiring, debugging and evidence](../docs/engine-semi-sequential.md).

[Transient fueling](../docs/engine-transient-enrichment.md) adds schema6, own007 rate curves, a320-byte atomic runtime block and14 appended MSL fields. Earlier identities and application files remain historical.


[Secondary-table software integration](../docs/engine-secondary-tables.md) adds schema8/own009, two16×16 maps and independent mode/source/axis/cell/condition metadata. Browser edits require explicit calibration review before replacing axes or cell meanings; TunerStudio exposes stored units separately and invalid whole-tune combinations reject. Actual offline edits to both rule panels/maps roundtrip through all8192 expected bytes with an explicit known base revision. Full runtime is640 bytes, or647 framed; MSL006 has188 engine/145 direct SIL fields, and schema4 compact screens keep250 bytes.

JSON1..7/own001..008 imports add default Off secondary tables. Schema7/own008 retain all load/AFR choices and0..255 coefficient bounds. Earlier identities retain their stricter bounds. The48KiB tune envelope requires128KiB engine NVS at the existing0x210000 offset; startup blocks saves on a mismatched old partition layout without erasing saved data. Guarded target J4 switch acquisition is implemented; its separate THT accessory is a prototype requiring physical qualification. Firmware/partition flashing, target storage/heap/USB/RF/timing and fresh secondary-enabled coupled plant comparisons remain untested. This is not complete secondary-feature or ECU parity acceptance. Follow the USB guide’s existing carrier/module power restriction before any hardware connection.
