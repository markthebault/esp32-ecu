# Tuning and log interoperability

Use [esp32-ecu-idle.ini](esp32-ecu-idle.ini) for the current own005 development layout. Offline MSQ editing/export and MegaLogViewer MSL workflows work in the tested applications. **TunerStudio 3.3.01 rejects our controller identity for online use.** The shared binary transport and dedicated target USB service do not remove that application gate. Vendor integration remains open.

The current identity is `ESP32ECU DEV 005 INHIBITED`. Serial protocol discovery returns `002`, independently of the tune layout revision. One 4992-byte page stages the complete tune; any successful burn validates, persists and activates it, resets control and reacquires phase. This is development configuration, not seamless hot tuning. Physical outputs remain inhibited in the selected build.

[USB tuning guide](../docs/engine-usb-tuning.md) describes wiring/port selection, revision semantics, diagnostics, reproduction and physical limitations. [Vendor integration request](vendor-integration-request.md) is prepared locally and has not been sent.

Retained own001/002/003/004 INIs and application-saved MSQs are historical definitions and import fixtures. The browser/Python importer accepts all five exact identities, with explicit neutral migration of absent fields. Current exports use own005. Other controllers' tune files are rejected.

Own004/005 `baseRevision` is read-only session-origin metadata. Active/backend revisions are separate runtime channels. TunerStudio omits the read-only origin from saved MSQs. Browser import displays that origin as unavailable and saves against the editor's loaded revision; a competing writer still causes 409. Python import uses an explicit `base_revision` when supplied, otherwise revision 1 is an offline placeholder. Legacy imports retain their strict matching-revision behavior.

```sh
python3 scripts/generate_tuning_wire.py
python3 scripts/generate_tunerstudio_ini.py
python3 tools/engine_msq.py INPUT.json NEW_OUTPUT.msq
python3 tools/web_server.py --tuner-port 29000 --tuner-pty .cache/engine/NEW-PTY
```

Use free ports/new PTY paths and one owning process per state file. These host endpoints share the web simulator's store and execute the target's portable C++ tuning Session/Stream. They do not attach to target hardware. Host runtime reads identify completed synthetic observations, their age and validity; saves clear the old control sample.

MSL exports retain the engine/trigger source labels and are usable in the tested MegaLogViewer HD 4.6.14. The current bounded engine log has 91 fields. App plots, source/age/validity handling and the derived lambda-display caveat are recorded in [observability documentation](../docs/engine-observability.md). USB tuning does not add autotune or TunerStudio high-speed logging.

[Idle control](../docs/engine-idle-control.md) adds versioned coolant/duty curves, normalized gains, state/gate diagnostics and an actual own005 application-saved fixture. Legacy imports disable the new idle path. The direct SIL export has 48 fields, including separate PWM and synthetic valve observations. The 232-byte radio frame remains unchanged.
