# Engine samples, logs and paired screens

The selected N16R8 build now shares coherent engine observations through the web API, a bounded RAM recorder and an opt-in ESP-NOW engine stream. Inputs and proposed outputs come from one completed control step. Physical engine outputs remain inhibited. No board was flashed or physically tested for this increment.

Open **Engine development → Control sample & engine log**. The panel identifies target observations or completed synthetic SIL results, original snapshot sequence, revisions and ages. Worker command observations have their own timestamp and sequence. A submitted proposal, virtual edge or software command mask does not establish electrical execution.

## Capture and export

Choose 20, 50, 100, 200, 500 or 1000 ms and 1–900 seconds, then start a target log. The default is 100 ms for 12 seconds. Settings apply to that session only; logs are volatile and do not write flash. Stop preserves the current retained ring. Timeout also freezes it if control observations stop arriving.

The device retains 256 rows: 5.12 seconds at 20 ms or 25.6 seconds at 100 ms. Each row includes log ID, row sequence, original control sequence/timestamps, qualified inputs, proposals, faults, phase evidence, revisions, earlier worker observations and raw ADC values when available. The recorder occupies 84,056 static bytes on both native and pinned Xtensa builds. A copied 16-row page is 5,336 bytes. JSON is serialized one row at a time outside the recorder and target locks. Streamed rows yield an RTOS tick so HTTP cannot continuously monopolize the lower-priority ADC/control task. Runtime stack/heap and timing measurements remain physical work.

The browser collects pages while it remains open, including when another UI page is selected. It holds at most 45,000 rows. Background-tab throttling, disconnection or closing the tab can lose data older than the device ring. **Export collected JSON/MSL** contains the rows that browser actually received and explicit missing row ranges. **Export retained window** downloads the device's current stopped ring. The file identifies boot/log IDs, retained range, period, duration, overwritten rows, missed intervals and skipped repeated/invalid observations. A new log replaces the prior ring; starting/following another log replaces that browser collection. Export first.

Scheduling is absolute. A delayed producer appends at most one current observation and counts skipped periods; it never fabricates rows for unobserved times. Repeated source snapshots are skipped. Stop/timeout accounts for due slots after the last observation, including a producer that stalls entirely. Lock-contention attempts are reported separately because one failed producer attempt need not lose a scheduled log point. Clock reversal freezes a recording with an explicit reason.

On the host, **Replay completed SIL log** replays the end of an existing SIL result through the same C++ recorder without waiting in real time. It retains original virtual timestamps and revisions. Its source is `synthetic_control_observation`, sensor-profile revision is 0, hardware ADC values are unknown, and the sample panel remains labelled historical. Saving a newer tune does not rewrite an older log's revision. The host radio fixture sends no ESP-NOW packets.

## API

All log endpoints require the current `X-ECU-Token` from `/api/session`. Browser mutations also require the existing same-origin policy. Read metadata first and include its 32-hex-character `boot_id` as `X-ECU-Log-Boot` for commands, row pages and MSL exports. A reboot changes this identifier, preventing accidental reuse of log 1 from another boot.

| Request | Result |
| --- | --- |
| `GET /api/engine/sample` | Coherent schema 1 observation; 64-bit sequences/timestamps are decimal strings |
| `GET /api/engine/data-log` | Session metadata, loss counters, boot ID and export state |
| `POST /api/engine/data-log` with `{"action":"start","period_ms":100,"duration_s":12}` | Validated new session; refuses active recording/export |
| Same POST with `{"action":"stop","log_id":1}` | Stops that exact session |
| `GET /api/engine/data-log?log_id=1&after=0` | At most 16 copied rows, `next_after`, and exact `gap_first/gap_last` range |
| `GET /api/engine/data-log.msl?log_id=1&after=0` | Stopped, nonempty retained window; holds an export lease against rearming |

Command bodies are at most 256 bytes and reject duplicate/unknown keys, trailing data, invalid periods and out-of-range integers. POST query strings are rejected before mutation. Stale boot/session/cursors return 409. A copied JSON page remains a consistent historical view if another client rearms afterward; `copied_page=true` does not mean current at transmission. The next request detects the changed ID. An interrupted or malformed JSON response must leave the caller's cursor unchanged. MSL export releases its lease on normal completion and send/format failures.

Inputs have a per-field validity mask. Bit order is RPM, MAP, TPS, CLT, IAT, lambda, battery, 5V rail. Unqualified values become JSON `null` / MSL `NaN`. The engine path uses confirmed physical units and raw input qualification; the slower display filter does not supply engine inputs. `InputsFresh` describes freshness at evaluation; display freshness also requires current source/control age. Target GP timestamps and ESP radio uptime have different origins; only same-clock durations are combined.

`phase_epoch` belongs to the external configuration context. Worker `epoch` belongs to the executor's internal generation. They are distinct counters. Tune/sensor revisions and separately timestamped worker sequences must also remain distinguishable.

## MegaLogViewer HD

The current `ESP32ECU ENGINE LOG 003` MSL has 91 fields, preserving the former79-field prefix: source/revisions/ages, input-valid mask, engine inputs, proposed corrections/fuel/spark, phase/fault/worker information and ADC diagnostics, including21 cylinder trim/validity/enable/mask fields, followed by12 idle controller/availability fields. Source and loss information is in the quoted header. Browser and native exports are checked field-for-field, including exact 64-bit IDs in the file. A viewer may represent large IDs as floating-point numbers; JSON remains the lossless audit format.

The unchanged MegaLogViewer HD Lite 4.6.14 opens the actual browser export and plots `ProposedPW` and `ProposedAdvance`. These are proposals from the synthetic run. Its default calculated `AFR*` graph can show a very large value at unavailable lambda samples; the source file still contains `NaN` and a clear lambda-valid bit. Inspect `InputValidMask` and source JSON before interpreting missing inputs or viewer-derived fields. This desktop check does not validate calibration or physical fuel/spark.

The direct SIL003 export now has48 fields, including controller, PWM and synthetic valve observations. Trigger MSL remains available. Current own005 offline MSQ editing and the inhibited USB service are described in the [USB guide](engine-usb-tuning.md). TunerStudio online identity acceptance remains unresolved.

## Validation and remaining work

[Evidence](../reports/engine/observability/) includes native sanitizer/allocation probes, actual task-service mutex/lease tests, authenticated HTTP cases, Chrome collection/export/navigation tests, three external-plant scenarios with actual pinned Speeduino algorithms on a separate plant, and two independent reviews. The external MVEM air path is hash-verified; combustion/free-shaft behavior remains local, empirical and uncalibrated. The native reference HAL has zero CPU/IRQ execution cost and is not an AVR/peripheral emulator.

The telemetry queue model injects loss, delay, reordering, authenticated replay, tampering and a long outage. It checks received values against source snapshots and conservative ages against model time. Logging pauses exceed device retention and must produce disclosed gaps. The observed control edge/trigger/cam streams and final ECU state match the previous reviewed scenario traces exactly. These are software/source-model results, with no claim of perfect engine behavior or physical ECU parity.

```sh
CXX=g++ sh scripts/test_firmware.sh
sh scripts/test_radio.sh
uv run --with fmpy==0.3.26 --with playwright python -m unittest discover -s tools -p 'test_*.py'
uv run --with playwright python tools/test_engine_observability_ui.py
uv run --with fmpy==0.3.26 python tools/run_engine_observability_scenarios.py
pio run -d firmware -e compact_n16r8_web -e compact_a3_web -e compact_a3_timing_bench
```

Actual two-device ESP-NOW pairing/negotiation, RF obstruction/range, reboot persistence, sustained HTTP/radio load, task high-water marks, minimum heap, timer jitter and captured GPIO/ADC behavior remain undone. PCB/case/antenna fit, electrical load/surge/EMI/thermal/splash tests remain undone. [Feature coverage](engine-feature-coverage.md) lists the wider Speeduino gaps.

[The cylinder update](engine-cylinder-trims.md) records the additive JSON fields, recorder growth and unchanged ESP-NOW schema1 base-demand layout. Historical001 log/viewer evidence remains retained.

The [idle update](engine-idle-control.md) documents the additive `idle.available` object, target/feedforward/P/I/D/state/reason fields and strict null handling. An absent legacy idle object is unavailable. The fixed radio frame remains232 bytes; only the existing base idle proposal is carried there.

The [semi-sequential increment](engine-semi-sequential.md) adds the current schema5/own006 strategy and negotiated engine-radio schema2. Earlier identities/evidence described here remain historical records; byte offsets, CAS, bounded logging and selected physical-output inhibition are retained.
