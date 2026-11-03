# Tuning and log interoperability

Use [esp32-ecu-development.ini](esp32-ecu-development.ini) for the current own004 development layout. Offline MSQ editing/export and MegaLogViewer MSL workflows work in the tested applications. **TunerStudio 3.3.01 rejects our controller identity for online use.** The shared binary transport and dedicated target USB service do not remove that application gate. Vendor integration remains open.

The current identity is `ESP32ECU DEV 004 INHIBITED`. Serial protocol discovery returns `002`, independently of the tune layout revision. One 4768-byte page stages the complete tune; any successful burn validates, persists and activates it, resets control and reacquires phase. This is development configuration, not seamless hot tuning. Physical outputs remain inhibited in the selected build.

[USB tuning guide](../docs/engine-usb-tuning.md) describes wiring/port selection, revision semantics, diagnostics, reproduction and physical limitations. [Vendor integration request](vendor-integration-request.md) is prepared locally and has not been sent.

Retained own001/002/003 INIs and application-saved MSQs are historical definitions and import fixtures. The browser/Python importer accepts all four exact identities, with explicit neutral migration of absent fields. Current exports use own004. Other controllers' tune files are rejected.

Own004 `baseRevision` is read-only session-origin metadata. Active/backend revisions are separate runtime channels. TunerStudio omits the read-only origin from saved MSQs. Browser import displays that origin as unavailable and saves against the editor's loaded revision; a competing writer still causes 409. Python import uses an explicit `base_revision` when supplied, otherwise revision 1 is an offline placeholder. Legacy imports retain their strict matching-revision behavior.

```sh
python3 scripts/generate_tuning_wire.py
python3 scripts/generate_tunerstudio_ini.py
python3 tools/engine_msq.py INPUT.json NEW_OUTPUT.msq
python3 tools/web_server.py --tuner-port 29000 --tuner-pty .cache/engine/NEW-PTY
```

Use free ports/new PTY paths and one owning process per state file. These host endpoints share the web simulator's store and execute the target's portable C++ tuning Session/Stream. They do not attach to target hardware. Host runtime reads identify completed synthetic observations, their age and validity; saves clear the old control sample.

MSL exports retain the engine/trigger source labels and are usable in the tested MegaLogViewer HD 4.6.14. The current bounded engine log has 79 fields. App plots, source/age/validity handling and the derived lambda-display caveat are recorded in [observability documentation](../docs/engine-observability.md). USB tuning does not add autotune or TunerStudio high-speed logging.
