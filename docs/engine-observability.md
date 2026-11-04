# Engine samples, logs and paired screens

The selected N16R8 build now shares coherent engine observations through the web API, a bounded RAM recorder and an opt-in ESP-NOW engine stream. Inputs and proposed outputs come from one completed control step. Physical engine outputs remain inhibited. No board was flashed or physically tested for this increment.

Open **Engine development → Control sample & engine log**. The panel identifies target observations or completed synthetic SIL results, original snapshot sequence, revisions and ages. Worker command observations have their own timestamp and sequence. A submitted proposal, virtual edge or software command mask does not establish electrical execution.

## Capture and export

Choose 20, 50, 100, 200, 500 or 1000 ms and 1–900 seconds, then start a target log. The default is 100 ms for 12 seconds. Settings apply to that session only; logs are volatile and do not write flash. Stop preserves the current retained ring. Timeout also freezes it if control observations stop arriving.

The device retains 256 rows: 5.12 seconds at 20 ms or 25.6 seconds at 100 ms. Each row includes log ID, row sequence, original control sequence/timestamps, qualified inputs, proposals, faults, phase evidence, revisions, earlier worker observations and raw ADC values when available. Current secondary metadata grows the recorder to139,352 static bytes on both native and pinned Xtensa builds. A copied16-row page is8,792 bytes. JSON is serialized one row at a time outside the recorder and target locks. Streamed rows yield an RTOS tick so HTTP cannot continuously monopolize the lower-priority ADC/control task. Runtime stack/heap and timing measurements remain physical work.

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

Current MSL006 engine exports have188 fields; direct SIL006 has145. The preserved prefixes contain source/revisions/ages, input-valid masks, proposals, phase/fault/worker/ADC information, cylinder trims, idle, transient and primary-load diagnostics. Both secondary tables append values, source/unit/condition metadata, selection, raw/qualified switch state, ages and reasons. Unknown numerics remainNaN. Browser/native exports agree field for field, including exact U64 identifiers in the file; JSON remains the lossless audit format if a viewer converts integers to floating point.

MegaLogViewer HD Lite4.6.14 opens/plots the new source, selection, qualification, reason and value fields in both formats. The actual application fixtures are fixed-input synthetic native probes, not coupled engine acceptance. A channel containing unknown samples can showNaN extrema. The earlier viewer's calculated AFR graph also displayed misleading values for unavailable lambda; inspect input/source/availability/validity fields and JSON before interpreting vendor-calculated summaries. Opening a log does not validate calibration or physical fuel/spark.

The earlier ENGINE LOG003 (91 fields) and direct SIL003 (48 fields) evidence remains historical. Current [own009 offline editing and inhibited USB service](engine-usb-tuning.md) preserve the older fields and add secondary metadata. Earlier online identity rejection remains unresolved; own009 online vendor acceptance is unverified. Trigger MSL remains available.

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

The [idle update](engine-idle-control.md) documents the additive `idle.available` object, target/feedforward/P/I/D/state/reason fields and strict null handling. An absent legacy idle object is unavailable. Historical schemas1/2 retain232 bytes and the base idle proposal; current schemas3/4 use250 bytes.

The [semi-sequential increment](engine-semi-sequential.md) introduced the schema5/own006 strategy and negotiated engine-radio schema2. Earlier identities/evidence described here remain historical records; byte offsets, CAS, bounded logging and selected physical-output inhibition are retained.

The earlier [transient fueling development](engine-transient-enrichment.md) uses schema6/own007, one5120-byte tune page and a320-byte runtime block, with105-field engine MSL004 and62-field direct SIL MSL004. Earlier layout/evidence descriptions in this document are historical. Selected physical-output policy and online vendor limits remain unchanged.

The earlier [load-model development](engine-load-model.md) adds the source-tagged `load_model` object,126-column engine and83-column direct SIL MSL005, own0085376/416-byte tuning and negotiated250-byte engine-radio schema3. Earlier packet/log/identity descriptions above are historical; their source/report bytes are preserved. Availability and null/NaN semantics remain explicit.

Current [secondary-table software integration](engine-secondary-tables.md) adds full configuration/selection/input metadata to each coherent sample,188-column native/browser engine and145-column direct SIL MSL006, own0098192/640-byte tuning and negotiated250-byte radio schema4. Unknown raw input time remains null/NaN; an invalid future raw switch timestamp remains loggable without advancing control clocks. Selection is reported directly because F32 logs can round a strict F64 threshold crossing to equality. Every non-Off secondary mode blocks older engine screen schemas and explicitly falls back to sensor telemetry.
