# Tuning and log interoperability

Use [esp32-ecu-profiles.ini](esp32-ecu-profiles.ini) for **own012 / tune schema11**, with1–8 virtual cylinders. TunerStudio MS Lite3.3.01 loads, edits and saves this definition offline. Actual cylinder8 fuel/spark edits reconstruct the complete12288-byte calibration page. Earlier own001..011 definitions and application fixtures remain historical.

Current identity: `ESP32ECU DEV 012 INHIBITED`. Serial discovery returns `002`. The single12288-byte calibration page stages the entire tune; a successful burn validates, persists and activates it, resets control and reacquires phase. Live data is1152 bytes,1159 framed. These portable transport operations work in native tests; physical USB is unverified and engine outputs remain inhibited.

**Supported online TunerStudio integration remains unresolved.** The latest fresh application rejection used own011, after valid discovery but without calibration/runtime reads, writes or burns. Own012 online acceptance is unverified. A separate genuine production Speeduino reference provided the historical positive control. No vendor identity is imitated. See the [application evidence and limitations](../docs/engine-tuning-application.md) and [USB/host transport guide](../docs/engine-usb-tuning.md).

[Editor limits](editor-limits.json) include the current1–8 cylinder domain. Cross-field, table-axis, timing, idle and boost rules still require whole-tune validation. Additional virtual cylinders have no fitted PCB drivers beyond the existing4+4 commands.

Origin revision is read-only metadata. TunerStudio omits it from saved MSQs; the browser retains the loaded editor CAS when importing. Python import accepts an explicit `base_revision`; without one,1 is an offline placeholder. An application-saved file cannot discover the live backend revision. Competing writers must reject stale commits.

```sh
python3 scripts/generate_tunerstudio_ini.py
python3 tools/engine_msq.py INPUT.json NEW_OUTPUT.msq
python3 tools/web_server.py --port 8765 --state .cache/engine/NEW-PREVIEW/profile.json --tuner-port 29000 --tuner-pty .cache/engine/NEW-PTY
```

The generator updates the current own012 definition and layout manifest; archived definitions remain separate. Use fresh ports/paths and one owner per state file. Host endpoints share the synthetic simulator store and execute the portable C++ transport without attaching to an ESP32.

MegaLogViewer HD Lite4.6.14 opens and plots the current **265-column engine MSL009** and **245-column direct-SIL009** files, including cylinder8 and full output masks. These are file-compatibility checks. Vendor-derived AFR extrema can misrepresent unavailable lambda, and plotted huge counters may lose precision; preserve source/age/validity fields, JSON and raw MSL. See [observability](../docs/engine-observability.md) and the [current cylinder-profile evidence](../docs/engine-cylinder-profiles.md).

The [own011 application packet](../reports/engine/tuning-apps-011/README.md) retains earlier boost-table edits, unit-warning corrections and online rejection. Its formats are historical. The [vendor request](vendor-integration-request.md) remains local and unsent. Online integration, physical USB/load/timing, autotune and wider [feature parity](../docs/engine-feature-coverage.md) remain unfinished.
