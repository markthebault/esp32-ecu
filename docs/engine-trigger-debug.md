# Crank and cam input diagnostics

**Trigger logging** records finite windows of digital input edges, displays crank/cam traces and raw rising-crank intervals, and exports JSON or MegaLogViewer MSL. The selected N16R8 firmware keeps all physical engine outputs inhibited. No board was connected or flashed for this increment.

This uses the existing protected Hall inputs. PCB, manufacturing and enclosure files are unchanged. The original printed A3 assembly manual is retained as a release record; this guide covers the new trigger workflow. The web connection guide is version 1.1.

## Bench workflow

1. Keep J3 open before startup and leave every actuator harness disconnected. Use the service AP and its per-boot password from the 115200-baud UART console.
2. J17 is crank; J18 is cam. On either connector: pin 1 ground, pin 2 SENSOR_5V, pin 3 raw Hall signal. Conditioning feeds GPIO8/GPIO9 respectively. Verify actual supply, ground, sensor type and polarity before applying a signal. Do not feed 12 V to these inputs or connect a generator in parallel with an energized sensor. A raw VR sensor needs an appropriate external conditioner.
3. Open **Trigger logging**, choose 128, 256 or 512 recorded edges and a 50–5000 ms window, then select **Record trigger window**. The API also accepts other integer limits from 16 through 512.
4. The recording freezes at its edge limit, timeout or **Stop recording**. A timeout with no edges is useful evidence of no reported input activity. It does not invent a signal. Reload reads the current capture. Starting another capture replaces the previous RAM frame; reboot also loses it.
5. Inspect both input traces and the raw rising-crank interval chart. Zoom and pan to inspect individual edges. Long intervals above 1.5 times the median are highlighted. Missing teeth, noise, capture loss and an interrupted signal can produce different or similar patterns; this highlight does not diagnose the cause or establish synchronization.
6. Export JSON for callback-order records and counters, or MSL for plotting. Use **Raw recorded edges** to inspect individual timestamps, polarity and configuration epochs. A digital trace does not measure voltage, Hall thresholds, signal integrity or a manufacturer's required air gap.

The host simulator uses **Replay SIL window**. Run a scenario in Engine development first. Replay takes the final window from a completed synthetic run and contains only the generated rising crank events. Cam and falling edges are not simulated. The UI draws rising-edge marks, leaves levels unknown and labels the source. It never presents this replay as a live MCU recording.

## Data and API contract

`POST /api/engine/trigger-log` uses the boot session token and same-origin checks. It accepts one of:

```json
{"action":"start","samples":512,"timeout_ms":1000}
```

```json
{"action":"stop","frame_id":1}
```

Unknown/duplicate fields, non-integer bounds, changed frame IDs and malformed commands are rejected. Stop requires the current frame ID and is idempotent for an already frozen current frame. Diagnostic commands do not save configuration or enable outputs.

`GET /api/engine/trigger-log` returns metadata. `GET /api/engine/trigger-log?frame_id=1&offset=0` returns at most 64 records. A client reads further pages at offsets 64, 128 and so on. An active recording can be inspected, but the UI waits for a frozen frame before assembling an export. Each page checks frame identity after its last row; a replaced snapshot returns conflict and discards its rows. Allocation or encoding failure returns an error, never a successful partial frame.

Records contain sequence, source channel, edge polarity, mapped capture time, callback observation time, raw 32-bit counter and configuration epoch. JSON retains callback delivery order, which can differ from capture-time order across channels. The chart and MSL sort by capture time; the sequence field retains the original order. Epoch changes can occur during a configuration save. A capture spanning them does not represent one immutable calibration.

Pre-arm timestamps and unresolved time mappings are dropped and counted separately. These counts do not detect every lost physical edge. `CallbackDelay` is a software observation difference that includes capture-clock synchronization uncertainty; it is not a measured interrupt duration. No field measures actual output-pin transitions.

## Capture isolation and limitations

The normal decoder remains on the original MCPWM group 0 rising-only channels. A separate group 1 capture timer and channels feed diagnostic recordings of both polarities. Each timer is independently synchronized to GPTimer's APB-derived microsecond domain at boot, with the measured startup bracket reported. The diagnostic timer continues running while its channels are disabled between recordings.

Group 1 interrupts have priority 1; the decoder/timing interrupts retain priority 3. A task mutex serializes start, stop and cleanup. Driver enable/disable calls stay outside the target spinlock. Start confirms both channels disabled, clears only group 1 capture status, and then arms the next frame. A driver failure latches diagnostics unavailable until reset. Both raw recorder and clock state reside in internal RAM. ISR recording performs bounded copies and integer operations; JSON work runs in task context in 64-record pages.

Diagnostic capture is unavailable in physical dummy-load and legacy pulse builds, where group 1 is not allocated. Its callback never mutates the engine decoder or executor. Shared CPU, GPIO matrix, APB clock and short target locks still require physical load testing. Isolation of latches does not establish zero interference or a timing guarantee.

The pinned SDK reads a single capture latch and its polarity separately. Fast edges can overwrite a pending latch or change it between those reads. Hardware capture loss, timestamp/polarity consistency, interrupt/lock duration, noise behavior and per-pin timing remain unmeasured. The recorder exposes the SDK-reported events and cannot prove that every physical edge was recorded. Cam recording does not implement 720-degree phase decoding or sequential fuel/spark.

## Speeduino and log-viewer evidence

[Ten native comparisons](../reports/engine/trigger-logging/logger-comparison.json) execute Speeduino's actual logger functions, attached interrupt wrappers and production history buffers at the pinned revision. Cases include 200/1000/6000 RPM, jitter, a short glitch, a 100 ms signal gap and cam edges. Raw composite comparisons check timestamps, source channel and edge level. Clean tooth tests compare intervals with both endpoints inside the common window. Speeduino's tooth logger filters accepted decoder edges; raw noisy/dropout intervals are intentionally not claimed equivalent.

The native Arduino fake supplied Uno interrupt numbering with Mega GPIO assignments. The test HAL now supplies the [official Arduino Mega mapping](https://github.com/arduino/ArduinoCore-avr/blob/1.8.6/variants/mega/pins_arduino.h). Production Speeduino decoder/logger/scheduler sources remain unchanged and are compiled without `UNIT_TEST`. A separate cam fixture enables its sequential-injection configuration solely to configure the real secondary decoder pin. That fixture does not add sequential capability to this project or establish strategy equivalence. Native execution has zero CPU cost and does not emulate AVR interrupt/electrical behavior.

MegaLogViewer HD Lite 4.6.14 opens the actual browser-exported trigger MSL and plots `ToothTime`. Unknown levels/counters remain `NaN`; the header states the synthetic source. Select a field and use playback to show its trace. [Viewer evidence](../reports/engine/trigger-logging/megalogviewer-check.json) records the unchanged application hash and the exported source file. This does not establish physical capture behavior or TunerStudio online support. The own-identity TunerStudio connection remains unresolved.

## Reproduce

```sh
CXX=g++ sh scripts/test_firmware.sh
PYTHONPATH=tools python3 -m unittest tools.test_trigger_capture tools.test_speeduino_runtime -v
uv run --with playwright python tools/test_trigger_ui.py
python3 scripts/build_speeduino_sim.py
PYTHONPATH=tools python3 tools/compare_trigger_loggers.py
pio run -d firmware -e compact_n16r8_web -e compact_a3_web -e compact_a3_timing_bench
python3 scripts/audit_target_isr.py firmware/.pio/build/compact_n16r8_web/firmware.elf .cache/engine/trigger-selected-closure
```

[Validation summary](../reports/engine/trigger-logging/validation-summary.json) records source/ELF hashes, native allocation-failure tests, HTTP/browser checks, independent target/reference reviews and the refreshed external engine-plant matrix. Manufacturing/physical qualification and remaining Speeduino features are still open.
