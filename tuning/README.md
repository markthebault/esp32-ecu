# Tuning and log interoperability

Use [esp32-ecu-boost.ini](esp32-ecu-boost.ini) for **own011 / tune schema10**. TunerStudio MS Lite3.3.01 now loads, edits and saves this definition offline. The [application-saved fixture](examples/tunerstudio-boost-roundtrip.msq) changes all three boost tables; Python/native and browser import/save/export retain every calibration field. Earlier own001..010 definitions and files remain historical.

**Online support remains unresolved.** A fresh own011 trial reports unsupported firmware after valid discovery, with zero calibration/runtime reads, writes or burns. The same unmodified application previously completed those operations against a separate genuine production Speeduino reference. [Current application diagnosis](../docs/engine-tuning-application.md) records both scopes. No vendor identity is imitated.

Current identity: `ESP32ECU DEV 011 INHIBITED`. Serial discovery returns `002`. One12288-byte calibration page stages the entire tune; a successful burn validates/persists/activates it, resets control and reacquires phase. Live data is1152 bytes,1159 framed. Physical engine outputs remain inhibited. See [USB/host transport](../docs/engine-usb-tuning.md) before connecting any hardware.

[Editor limits](editor-limits.json) bind the current33 general scalars, six curves and three timing values to the native validator, including four-cylinder support and a5..45° cam window. Coupled fan/rev/axis/idle/boost rules still require whole-tune validation. These editor changes do not add cylinder or trigger support.

Python and browser exports use unitless boost option fields. The earlier Python own011 exporter incorrectly labelled three bit fields as percent; that caused actual application warnings. Values and wire layout are unchanged. Re-exporting an older file corrects its metadata without rescaling calibration.

Own004..011 origin revision is read-only metadata. TunerStudio omits it from saved MSQs. Browser import retains the loaded editor CAS; a competing writer still rejects. Python import accepts an explicit `base_revision`; without one,1 is only an offline placeholder. An application-saved file cannot discover a live backend revision.

```sh
python3 scripts/generate_tunerstudio_ini.py
python3 tools/engine_msq.py INPUT.json NEW_OUTPUT.msq
python3 tools/web_server.py --tuner-port 29000 --tuner-pty .cache/engine/NEW-PTY
```

Use fresh ports/paths and one owner per state file. The host endpoints share the synthetic simulator store and execute the target's portable C++ Session/Stream, without attaching to an ESP32.

MegaLogViewer HD Lite4.6.14 opens and plots current245-column engine MSL008 boost/protection data and202-column direct-SIL008 control-state data. The latter trial has300 rows from the existing unvalidated regression plant and plots BoostReason6..8; it adds file compatibility evidence, not a new engine benchmark. Source, age and validity flags remain authoritative. Vendor-derived AFR* can show misleading extrema for unavailable lambda; graph displays also cannot establish exact enormous counters. Preserve JSON and raw MSL for those audits. [Observability and viewer limitations](../docs/engine-observability.md).

[Reviewed current application evidence](../reports/engine/tuning-apps-011/README.md) preserves the initial unit warnings, corrected real-app files, raw online rejection, plots and independent checks. The [vendor request](vendor-integration-request.md) is updated locally and remains unsent. Supported online integration, target USB/load/timing, autotune and wider [ECU feature parity](../docs/engine-feature-coverage.md) remain open.
