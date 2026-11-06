# Opt-in ESP-NOW engine telemetry

This extends the [existing pairing and sensor protocol](espnow.md). It implements the ECU sender plus a [reference receiver](../tools/engine_receiver.py); it does not build a screen. The channel remains 6, encrypted unicast uses the saved 16-byte LMK, and peers remain limited to 4. Peer Storev1 and types 1–6 keep their existing byte layouts. Capabilities are volatile, reset at reboot/unpair/slot reuse and do not change the saved peer blob.

Types7..13 use the existing8-byte `ECN1`, version1, type, little-endian uint16 length header. No native structure is transmitted. Integers are unsigned little endian; floats are IEEE-754 float32. The largest datagram is250bytes; schemas1/2 retain232bytes. Schema5 uses two authenticated datagrams per observation; schema6 uses three and carries boost diagnostics. Current schema7 adds a fourth cylinder part and is required for1..8-cylinder profiles and wider worker contexts. Send/receive callbacks only signal or queue bounded work; authentication, JSON and framing run in the task, consistent with [Espressif's API guidance](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/network/esp_now.html).

## Negotiate and recover

1. Load the saved ECU STA MAC and LMK. Send a type 7 read-only query with session/counter/features/schema all 0 and a fresh cryptographic 16-byte client nonce. Start a local monotonic timer for this request. A query does not enable engine telemetry.
2. Within 1 second, verify type 8's full HMAC with the LMK, echoed nonce, enums, lengths and reserved/status fields. Reject responses from any other MAC. Record the current capability counter/mode, nonzero boot session, boot nonce, sequence floor and ECU reply-send time.
3. To enable, send type7 with that boot session, counter+1, feature bit0 set, schema7 (or an explicit compatible legacy schema1..6) and a new nonce. Accept the matching authenticated reply before using data. To disable, increment the counter with features/schema0. Counter0 is reserved for queries. Updates must be strictly newer; retry the exact same request bytes if a reply is lost. A same-counter request with changed bytes is rejected. At UINT32_MAX, re-pair/reboot is required before another update; never wrap the counter.
4. A rebooted screen queries the ECU's accepted counter instead of assuming 0. Queries report the current mode without modifying it. An ECU reboot starts disabled again. A query with session 0 discovers the current boot. Query/reply state is not persisted to NVS.
5. Refresh the timed nonce query at most 5 seconds later and after a 1 second gap in authenticated engine frames, including no first data within 1 second of a reply. The reference receiver invalidates its cached display while querying. Use a fresh random nonce every time. Never accept an unsolicited, expired or nonce-mismatched reply.

The query sequence floor prevents a screen that lost RAM state from accepting recorded same-boot engine frames at or below that floor. Derive the full 32-byte engine MAC key as:

`HMAC-SHA256(LMK16, ASCII("ECU-NOW-ENGINE-v1") || boot_nonce16 || session_u32_LE)`

The ASCII domain is 17 bytes. Use all 32 derived bytes for engine data/ACK HMACs, not only the first 16. A fresh boot nonce separates engine frames even if the random 32-bit session happens to collide, after a fresh nonce negotiation. This does not retrofit unlimited replay protection into the legacy sensor protocol. Pairing/LMKs remain the trust boundary; compromised keys/ECU/service clients and jamming remain outside this protection.

| Type 7 request, 76 bytes | Type 8 reply, 108 bytes |
| --- | --- |
| 0..7 common header | 0..7 common header |
| 8 session u32, 0 allowed for query | 8 current nonzero session u32 |
| 12 counter u32, 0 for query | 12 accepted update counter u32 |
| 16..31 fresh client nonce | 16..31 echoed client nonce |
| 32 feature mask u32 (only bit 0) | 32 current feature mask u32 |
| 36 schema u32 (1..6 enabled,0 disabled/query) | 36 current schema u32 |
| 40 reserved u32=0 | 40 status u32=0 |
| 44..75 HMAC-SHA256(LMK16, bytes 0..43) | 44..59 per-boot random nonce |
| | 60 engine packet sequence floor u64 |
| | 68 ECU reply-send ESP uptime µs u64 |
| | 76..107 HMAC-SHA256(LMK16, bytes 0..75) |

## Engine packet, type 9

Total232bytes for schemas1/2 or250 for schemas3..7. Multipart BASE retains the schema4 layout with its negotiated schema field. Schema5 needs matching type11; schema6 also needs type12; schema7 also needs type13. HMAC verification with the derived key precedes any sequence/freshness update. Reject incorrect lengths, nonzero reserved bytes, unsupported schema/enums, wrong boot/source, duplicate/out-of-order packet IDs and reversed sender time. Packet IDs are global u64 and can have gaps. The source proposal sequence is independently u64. Preserve these as integers, not JavaScript Number values; the web API uses decimal strings.

| Offset | Field |
| --- | --- |
| 0..7 | Common header |
| 8 | Boot session u32 |
| 12 | Engine packet sequence u64 |
| 20, 22 | Negotiated schema u16 (1..6), flags u16 |
| 24, 28 | Sensor-sample and control-evaluation ages at send, u32 ms |
| 32, 36 | Tune and sensor-profile revisions, u32 |
| 40, 48 | Source proposal sequence and earlier worker-current command sequence, u64 |
| 56, 60 | Source external-configuration phase epoch and worker executor-generation epoch, u32; distinct domains |
| 64, 68, 72 | Controller fault bits, phase-loss count, rejected-cam count, u32 |
| 76 | Cam error, float32 crank degrees |
| 80..89 | Ten u8: state, strategy, source, phase reason, input-valid mask, current timing cause, last timing cause, virtual mask, physical-command mask, board flags |
| 90..91 | Reserved0 for schemas1..3; compact secondary mode/source/status for schema4 below |
| 92 | ECU transmission ESP uptime µs, u64 |
| 100, 104, 108 | Worker tune revision u32, worker sensor revision u32, worker observation age u32 ms |
| 112..143 | Eight input floats: RPM, MAP kPa, TPS %, CLT °C, IAT °C, lambda, battery V, sensor V |
| 144..199 | Fourteen proposal floats: RPM, VE %, target lambda, advance °BTDC, PW ms, dwell ms, deadtime ms, air mg, warmup ratio, afterstart ratio, accel ratio, EGO ratio, duty %, idle % |
| 200..231, schemas1/2 | HMAC-SHA256(engine_key32, bytes0..199) |
| 200, schemas3/4 | Four2-bit resolved source codes, fuel/spark/lambda/trim, low to high |
| 201, schemas3/4 | Pressure mode bits0..1, baro source bit2, available bit3, arithmetic valid bit4, AFR mode bits5..6, MAP guard available bit7 |
| 202,206,210,214, schemas3/4 | Unaligned F32: fuel coordinate, AFR factor, baro kPa, EMAP kPa |
| 218..249, schemas3/4 | HMAC-SHA256(engine_key32, bytes0..217) |

State values 0..5 and fault bits match `engine.hpp`; strategy 0=batch/wasted, 1=sequential four cylinders, 2=semi-sequential four cylinders (schemas2/3/4). Source 1=target control observation, 2=synthetic control observation. Phase reasons match `engine_phase.hpp`, timing causes match `timing_executor.hpp`. Schema1 permits strategies0/1 and current/last timing causes0..16. Schema2 adds strategy2 and timing cause17 (`idle_pwm_fault`), with the same offsets and size. Unknown enum values reject. The receiver must enforce the exact authenticated negotiated schema on every frame, including after upgrades or downgrades. Input validity bits follow the eight input floats. An invalid input is NaN with its bit clear. Unknown proposal/cam floats are NaN. Infinite values are rejected. Board bits 0..3 mean ADC OK, SAFE high, interlock high and capture overflow. Masks represent software state, without pin readback.

Flags, low to high bits 0..15: present, inputs fresh at control evaluation, storage OK, crank synchronized, phase synchronized, phase required, proposal submitted to worker queue, dummy-load physical policy compiled, phase/revision context matched, proposal active, fuel cut, spark cut, pump proposal, fan proposal, inputs qualified at evaluation, sender display freshness. The selected N16R8 build keeps the dummy policy clear and engine outputs inhibited.

Unknown ages are UINT32_MAX. Finite old ages saturate at UINT32_MAX−1. The sender reads ESP uptime before GP time at publication, calculates GP-source durations, then adds later ESP elapsed time. Publication/transmission never resets the source/control timestamp when observe skipped a step. Worker ages are separate. Sender display freshness means sample/control ages≤1000 ms at transmission; it does not establish current command validity or physical execution.

The receiver must add network/receiver age. The reference implementation uses the authenticated timed query as a clock interval, a 2% relative clock-rate allowance plus 2 ms quantization, and refreshes within 5 seconds. Its conservative transit bound is `max(0, local_elapsed_since_query_send − sender_elapsed_since_reply_send) + ceil(0.02×local_elapsed) + 2ms`. Source/control/worker ages are first rounded upward by `100/98` to cover a slow source clock, including history before the query. Add transit and subsequent receiver-local elapsed time. A repeated source sequence cannot change immutable payload or lower a previous age bound; an unknown repeated age remains unknown. After a gap, fresh negotiation is required. These are explicit clock assumptions, not measured oscillator/RF guarantees. Never compare raw ECU and screen uptime origins or trust a newly arrived packet's freshness bit alone.

## Acknowledge and rate

Type 10 is 56 bytes: common header 0..7, session u32@8, received engine packet sequence u64@12, reserved u32=0@20, HMAC-SHA256(engine_key32, bytes 0..23)@24..55. ACK the newest authenticated, processed complete observation promptly. Schema5 requires both parts before an ACK; schema6 requires all three. The ECU requires a sequence it actually submitted within the last 1 second and within its last 8 complete submissions for that peer and packet family (engine or legacy sensor, independently). Promptly acknowledge the newest. The1s age limit still applies when eight observations span more than1s. It rejects duplicates, old ACKs and reversed time before advancing ACK state. The same recent-send/serial rule applies to legacy type6, including legitimate uint32 rollover through0. A MAC-layer send success is not a screen ACK.

Normal per-peer budget remains up to20 datagrams/s. Legacy peers retain their sensor cadence. Schemas1..4 normally receive16 engine observations,2 legacy sensor packets and2 metadata packets/s. Schema5 uses those same16 engine datagram slots for8 complete two-part observations. Schema6 reserves both metadata and sensor slots ahead of pending parts, leaving16 engine datagrams/s for about5.33 complete observations/s over longer windows. A four-peer native15s schedule produces80 complete observations per peer, all six metadata channels,500ms sensor/metadata intervals and at most200ms from BASE to BOOST. Those are deterministic software-model results. Capability replies borrow slots and are rate limited; radio congestion/pairing/CPU delays can reduce rates. Busy periods do not create an unbounded backlog. Metadata keeps its session/revision contract, and its session is stamped at transmission. No rate/delivery guarantee is implied.

The UI distinguishes recent link ACKs from complete-engine ACKs, including separate pending BASE/FLEX/BOOST submissions. Sensor ACKs cannot hide a missing complete-engine ACK for3 seconds. Complete fault observations can be acknowledged while their flex value remains unusable. Neither an ACK nor a worker command observation proves an output executed or a screen displayed it. HTTP failure clears both ACK readbacks to unknown. Unpair stops subsequent sends and resets stream keys/capabilities/ACK history for that slot.

## Reproduce

`tools/test_engine_observability.py` compares native C++ and independent Python packet bodies/full HMACs, key length, nonce/counter recovery, replay, clock bounds, stale gaps, unknown values and 64-bit IDs. Native tests cover both ACK widths and recorder limits. [The observability guide](engine-observability.md) links engine-plant, UI, viewer and independent review evidence. Future screen firmware can use `EngineReceiver` as an executable contract; it must implement ESP-NOW peer storage/transport and display behavior separately. No screen, actual RF exchange, range or sealed-enclosure qualification was performed here.

The cylinder-trim update keeps this schema unchanged. Its fourteen proposal floats remain untrimmed base demands. Applied per-cylinder PW/advance/fuel/duty and masks are available through web/JSON/engine MSL002, not this radio frame. Receivers must not present the scalar PW/advance as the applied value for every cylinder.

The [semi-sequential increment](engine-semi-sequential.md) adds schema2 while preserving schema1. Negotiation is independent per peer; schema is part of the authenticated counter/nonce transcript. A retry at the same counter cannot change it. Query replies report the currently accepted version. Firmware emits the chosen version consistently in every representable mode. If a schema1 peer cannot represent the current load model, strategy or current/last timing fault, its engine slots fall back to the existing sensor stream. API fields `engine_telemetry_blocked`, `engine_upgrade_needed` and `engine_block_reason` distinguish this from an offline screen; the UI asks for a screen firmware update. Historical fault17 can keep that fallback active after the current fault clears. No mode is silently relabelled. The232-byte frame still carries base scalar proposals, not per-cylinder applied values or executed pulse traces. The v1 key-domain transcript remains unchanged because the negotiated payload schema is authenticated inside the body.


Schema3 carries [load-model source meanings](engine-load-model.md). Source codes0/1/2 mean MAP kPa, physical TPS percent and100×IMAP/EMAP percent. Pressure codes0/1/2 mean Off100kPa, MAP/100kPa and MAP/baro. AFR codes0/1/2 mean Off, target and measured. Baro source0 is fixed/manual;1 is calibrated live. Available does not imply all optional numbers or valid control. Unknown numeric fields remain NaN. Spark/lambda/trim coordinates in the Python receiver are derived approximately from authenticated F32 inputs when arithmetic is valid; inactive/missing inputs remain unknown. Their precision can differ from the core's F64 lookups. Detailed reason, auxiliary role and AFR state require web/log diagnostics.

Schemas1/2 are emitted only for the legacy MAP/target model with the postcat role. New load modes require schema3 or4; the API/UI disclose an upgrade requirement and fall back to the legacy sensor stream. Authentication covers schema and the correct variable body length. A negotiated version cannot be silently downgraded, and a repeated source snapshot cannot alter its appended payload. HMAC derivation, ACK layout, sequence/counter/nonce, freshness and replay rules remain unchanged. `test_load_radio.py` checks independent bytes, every250 individual tamper positions, malformed lengths/enums, downgrade, old-byte preservation and new-mode fallback.


## Secondary summary, schema4

Schema4 retains every schema3 field, its218-byte authenticated body and250-byte total frame. Former reserved bytes90/91 carry two compact secondary observations:

| Byte | Bits | Meaning |
| --- | --- | --- |
|90|0..2 /3..5|Fuel/spark mode:0 Off,1 multiply,2 add,3 conditional,4 input;5..7 reject|
|90|6 /7|Fuel/spark secondary selected (`active`)|
|91|0..1 /2..3|Fuel/spark source:0 MAP,1 physical TPS,2 IMAP/EMAP;3 rejects|
|91|4 /5|Fuel/spark observation available|
|91|6 /7|Fuel/spark calculation evaluated|

Unavailable observations are canonical empty: mode/source0 and active/evaluated clear. An active Off rule rejects. Active selection can be known before arithmetic completes; check evaluated, controller faults, sample age and global flags. This compact frame does not carry cell meaning, secondary coordinates/values, input qualification/age or detailed reasons; use web/USB/log diagnostics for them. The existing scalar advance/PW remain base proposals rather than per-cylinder applied execution.

Every non-Off configured secondary mode requires schema4, including a currently inactive conditional/input rule. Schemas1..3 keep their exact historical byte meanings and cannot silently label a secondary result as primary-only. The ECU reports `engine_telemetry_blocked`, an upgrade reason and explicit sensor-stream fallback. Off rules remain compatible with older schemas, subject to their existing strategy/timing/load limits.

The receiver enforces the exact authenticated negotiated schema and includes the new bytes in repeated-source immutability. HMAC key domains, full MAC lengths, counters, nonce retries, query floor, clock assumptions, ACKs and payload budget remain unchanged. `tools/test_secondary_radio.py` independently checks225 mode/source pairs, every tampered byte, signed invalid metadata, downgrade, retry/replay and legacy byte preservation. These are software contracts; no physical screen or RF test was performed.

## Complete flex observation, schema5

Schema5 preserves every schema4 base field, including bytes90/91 and200..217. Its separate type11 datagram is232 bytes. Both parts use the same session and64-bit packet sequence. The full32-byte base HMAC in the extension binds that exact base, preventing mixed observations. Each part has its own full HMAC with the existing32-byte engine key. The [machine contract](../config/engine-radio-v5.json) remains a development contract; no screen application or actual RF qualification is supplied.

| Offset | Type11 field |
| --- | --- |
|0..7|Common header|
|8,12|Session u32, packet sequence u64|
|20,22|Schema u16=5, reserved u16=0|
|24..55|Full base HMAC-SHA256|
|56..111|Seven u64: sample µs, window start µs, last edge µs, raw edges, fault generation, acknowledged generation, configuration epoch|
|112..151|Ten F32: frequency Hz, low pulse µs, ethanol %, fuel °C, unfiltered ethanol %, unfiltered fuel °C, sample age at control ms, fuel %, spark addition °, temperature %|
|152..175|Six producer-calibration F32: low Hz, high Hz, fault Hz, tolerance Hz, stale ms, filter ms|
|176,180|Flex flags u32, actual producer tune revision u32|
|184..190|Seven u8: source, reason, capture reason, last fault, correction reason, observed window cycles, configured cycles|
|191|Reserved0|
|192,196|Raw-sample age at original base preparation/send anchor, u32 ms; original producer stale limit, u32 µs|
|200..231|HMAC-SHA256(engine_key32, bytes0..199)|

Record enums and flags follow `flex_runtime.hpp`; unknown bits/enums/infinity reject. Unknown F32 values use canonical NaN `0x7fc00000`. Unavailable raw age isUINT32_MAX and an unavailable Record has stale limit0. The stale limit is rounded from the producer's F32 calibration to microseconds with positive half-up rounding, matching C++ `llround`. A raw source without a completed window has unknown age, including timestamp0. A synthetic scalar fixture may legitimately originate at epoch0 but cannot qualify as raw capture. Target control cannot claim synthetic flex origin; a claimed matching configuration requires matching nonzero producer/base revisions.

The sender retains one immutable pair per peer for at most250ms. SDK failures retry those exact bytes, without replacing the snapshot or restarting its age. It rechecks current time immediately before every submission. Both successful SDK submissions are required to enter the engine ACK window, which uses the original preparation time. Capability exchanges, unpair and key changes cancel pending pairs; capability replies also retire pairs made while the reply was waiting. Sequence exhaustion never wraps.

The reference receiver buffers at most two sequences for250ms from their first fragment. Either order works. Duplicates cannot extend that deadline. Partial observations never reach the public display, ACK, latest-completed sequence or engine liveness. Expired, evicted or authenticated conflicting sequences are retired separately from the last complete sequence, so they cannot later complete or be ACKed. A changed signed duplicate quarantines the sequence even if its changed fields fail semantic validation. Fresh queries clear partial state; per-boot repeated-source immutability and age floors survive clock-query refresh.

All receiver `now_ms` arguments mean current processing time from one monotonic clock, not a delayed packet's historical receive stamp. Clock reversal through any time-bearing API, including status reads, requires a fresh timed query. Raw age uses the original sample, then adds fragment wait, negotiated transit,2% clock allowance and local elapsed. A conservative F32/control-age lower bound also covers the first pair. Repeated proposals preserve the full flex Record and previous age bounds; explicit unknown age remains unknown. Compare against the original producer deadline. New ADC/control snapshots cannot renew an old raw sample. Base data can remain fresh after flex qualification expires.

Required invalid/unknown/future/expired flex requests red blinking at zero RPM as well as during operation; held samples are rechecked each radio loop. Flex Off adds no fault dependency. The indication is an advisory software policy and does not prove target execution, LED operation or CPU health.

Schemas1..4 remain byte-identical and suppress engine telemetry when corrections or a secondary ETH condition require flex; their slots retain explicit sensor fallback. A schema5 receiver may acknowledge a complete invalid/fault observation: receipt, value quality and control permission are separate. `flex_control_allowed` in the reference status covers the flex gate alone, not global engine safety.

Reproduce with fresh output directories:

```sh
PYTHONPATH=tools python3 -B -m unittest test_flex_radio test_engine_observability test_load_radio test_secondary_radio
python3 -B scripts/test_radio_service.py --output .cache/engine/NEW_RADIO
python3 -B tools/check_radio_service_fixtures.py .cache/engine/NEW_RADIO .cache/engine/NEW_INTEROP.json
uv run --offline --with playwright==1.64.0 python -B tools/test_flex_radio_ui.py --fixtures .cache/engine/NEW_RADIO --output .cache/engine/NEW_BROWSER
```

The actual sender/handler code executes against native SDK API models. These checks do not execute the RTOS task, ESP-IDF transport, radio, physical LED or a screen. The [frozen evidence](../reports/engine/flex-radio/README.md) binds source, native frames, browser checks, final linked builds and independent review. Earlier evidence packets remain historical and unchanged.


## Boost pressure and valve proposal, schema6

The [schema6 machine contract](../config/engine-radio-v6.json) preserves the BASE layout and FLEX record, changing their schema fields to6. It adds a144-byte type12 BOOST datagram. All three have one session and packet sequence, and both extensions bind the full BASE MAC. Each part has its own full HMAC. No extension introduces a new timestamp or refreshes the original observation.

| Offset | Type12 field |
| --- | --- |
|0..7|Common header|
|8,12|Session u32, packet sequence u64|
|20,22|Schema u16=6, reserved u16=0|
|24..55|Full BASE HMAC-SHA256|
|56..87|Eight F32: bounded duty %, raw demand %, target absolute kPa, feedforward %, error kPa, P %, I %, D %|
|88,96|PID updates and overboost events, u64|
|104|Boost flags u32, bits0..10 from `boost_control.hpp`|
|108,109|Reason u8=0..16, mode u8=0..2 (Off/open/closed loop)|
|110|Available bit0, pressure enabled bit1, engine inhibit bit2; other bits0|
|111|Reserved0|
|112..143|HMAC-SHA256(engine_key32, bytes0..111)|

Unknown F32 values are canonical NaN. Applied proposal duty is0..100%, but finite raw demand and PID terms can exceed that range. Unavailable records have no values, counters, flags, reason or inhibit decision; configured pressure/mode can remain known. Counters retain all64bits. A pressure inhibit must agree with the parent faulted state, nonzero faults, fuel/spark cuts, no pump or active engine proposal, and zero scalar pulse/dwell/duty. Worker timing cause18 is supported in schema6. Worker faults describe an earlier command and do not rewrite the current controller proposal.

A valid MAP may reach400kPa only with pressure enabled. The source input-valid mask still applies the exact configured/calibrated ceiling. A schema6 BASE with MAP above110kPa stays private until BOOST confirms the pressure context. The receiver does not reconstruct sensor calibration or controller qualification from rounded wire values.

The sender holds at most one immutable three-part observation per peer within the original250ms deadline, rechecked immediately before each SDK submission. It enters the ACK window only after all three submissions succeed and retains the original preparation time. Pending observations can finish in their original context after the live profile changes. Query, mode/schema update, key change and unpair cancel them. Legacy schemas1..5 still withhold new boost pressure profiles; their sensor fallback also requires a fresh sensor publication.

The receiver holds at most two observations, supports all six arrival orders and uses the same absolute250ms assembly deadline, retirement, duplicate, clock-query and repeated-source rules as schema5. Neither one nor two parts can publish data, advance a completed sequence, ACK or renew the1s engine gap. Both full BASE bindings must match. Every boost byte joins repeated-proposal immutability, including counters and unknown values. Source/control ages include assembly wait, conservative clock/transit bounds and local elapsed; an unknown repeated age cannot become fresh after a query.

`boost_observation_fresh` means an available diagnostic record with bounded source/control ages at most1s. It is not a20ms actuation authorization. Pressure-valid, valve-allowed and engine-inhibit statuses are explicitly named `at_source`; their original values remain identifiable when the display becomes stale. The receiver never drives an engine or valve. Flex freshness retains its own producer deadline and can expire before the boost diagnostic display.

The paired-screen page distinguishes BASE pending, FLEX pending, BOOST pending, complete-observation ACK and old-screen upgrade/fallback. Counters distinguish submitted datagrams from complete observations and reception. The actual sender service is exercised in a native SDK API model, including all four peer slots; RF, RTOS scheduling, actual screen application, physical valve and engine operation remain unmeasured.

```sh
PYTHONPATH=tools python3 -B -m unittest test_boost_radio test_flex_radio test_engine_observability test_load_radio test_secondary_radio
python3 -B scripts/test_radio_service.py --output .cache/engine/NEW_SCHEMA6_RADIO
python3 -B tools/check_radio_service_fixtures.py .cache/engine/NEW_SCHEMA6_RADIO .cache/engine/NEW_SCHEMA6_INTEROP.json
uv run --offline --with playwright==1.64.0 python -B tools/test_flex_radio_ui.py --fixtures .cache/engine/NEW_SCHEMA6_RADIO --output .cache/engine/NEW_SCHEMA6_BROWSER
```


## Complete cylinder profiles, schema7

[The machine contract](../config/engine-radio-v7.json) preserves existing BASE/FLEX/BOOST layouts with authenticated schema7 fields and adds a236-byte type13 CYLINDERS datagram. Each extension binds the complete BASE HMAC. All four are prepared from one immutable source observation and must authenticate, match session/sequence/schema/base MAC, and complete within the original250ms assembly deadline before display or ACK. Partial or duplicate parts cannot renew observation liveness or deadlines. Query, capability update, key/boot change and unpair retire pending assembly. Repeated proposal checks include the entire cylinder payload across clock queries.

| CYLINDERS field | Offset | Bytes |
| --- | ---: | ---: |
| Common header | 0 | 8 |
| Session / packet sequence / schema7 / zero reserved | 8 | 16 |
| Full BASE HMAC-SHA256 | 24 | 32 |
| Proposal count1..8 / earlier-worker count0..8 / fitted injector4 / fitted coil4 | 56 | 4 |
| Valid mask / trims-enabled bool / capacity / spark-clamp / retard-floor masks | 60 | 5 |
| Reserved zero | 65 | 3 |
| Full worker virtual mask / physical command mask, U32 each | 68 | 8 |
| C1..8 rows: pulse-ms / advance-degrees / fuel-percent / duty-percent, F32 each | 76 | 128 |
| Full CYLINDERS HMAC-SHA256 | 204 | 32 |

Proposal masks fit proposal count. Worker masks fit the independently declared earlier worker count, with0 meaning unknown/no command and requiring zero masks. Full masks must agree with BASE's low bytes; physical command masks are limited to fitted4+4 IDs. Logical IDs are INJ1..4=0..3, IGN1..4=4..7, idle8, boost9, INJ5..8=10..13, IGN5..8=14..17. Unknown/inactive cylinder values are canonical quiet NaN `0x7fc00000`; the reference receiver displays them as null. None of these masks is electrical readback or remote control permission.

The sender retains the existing per-peer datagram budget and both metadata/sensor reservations. In a15s,1200-slot native API-model replay with four peers, each gets60 complete observations,30 metadata packets across all six sensor channels and30 sensor packets; maximum BASE-to-CYLINDERS time is150ms. Capability/pairing/CPU/RF congestion can reduce rates. This is a deterministic sender model, not a throughput or latency guarantee. Tests cover fourth-part SDK failure/exact retry, original expiry, partial ACK rejection, all24 arrival orders, authenticated semantic failures, every-byte tampering and wider earlier workers.

Schemas1..6 are withheld whenever the current proposal count is not4 or an earlier worker count/mask cannot fit the old contract. Current4/earlier-worker8 also requires schema7. Compatible four-cylinder bundles retain their earlier bytes; sensor fallback remains independent and requires fresh sensor data. The paired-screen UI reports the pending cylinder part and complete-observation ACK separately. Actual screen implementation, two-device/RF/load testing and physical operation remain open.
