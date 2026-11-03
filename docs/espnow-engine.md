# Opt-in ESP-NOW engine telemetry

This extends the [existing pairing and sensor protocol](espnow.md). It implements the ECU sender plus a [reference receiver](../tools/engine_receiver.py); it does not build a screen. The channel remains 6, encrypted unicast uses the saved 16-byte LMK, and peers remain limited to 4. Peer Storev1 and types 1–6 keep their existing byte layouts. Capabilities are volatile, reset at reboot/unpair/slot reuse and do not change the saved peer blob.

Types 7–10 use the existing 8-byte `ECN1`, version 1, type, little-endian uint16 length header. No native structure is transmitted. Integers are unsigned little endian; floats are IEEE-754 float32. The largest packet is 232 bytes, within the 250-byte v1 ESP-NOW payload limit. Send/receive callbacks only signal or queue bounded work; authentication, JSON and framing run in the task, consistent with [Espressif's API guidance](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/network/esp_now.html).

## Negotiate and recover

1. Load the saved ECU STA MAC and LMK. Send a type 7 read-only query with session/counter/features/schema all 0 and a fresh cryptographic 16-byte client nonce. Start a local monotonic timer for this request. A query does not enable engine telemetry.
2. Within 1 second, verify type 8's full HMAC with the LMK, echoed nonce, enums, lengths and reserved/status fields. Reject responses from any other MAC. Record the current capability counter/mode, nonzero boot session, boot nonce, sequence floor and ECU reply-send time.
3. To enable, send type 7 with that boot session, counter+1, feature bit 0 set, schema 1 and a new nonce. Accept the matching authenticated reply before using data. To disable, increment the counter with features/schema 0. Counter 0 is reserved for queries. Updates must be strictly newer; retry the exact same request bytes if a reply is lost. A same-counter request with changed bytes is rejected. At UINT32_MAX, re-pair/reboot is required before another update; never wrap the counter.
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
| 36 schema u32 (1 enabled, 0 disabled/query) | 36 current schema u32 |
| 40 reserved u32=0 | 40 status u32=0 |
| 44..75 HMAC-SHA256(LMK16, bytes 0..43) | 44..59 per-boot random nonce |
| | 60 engine packet sequence floor u64 |
| | 68 ECU reply-send ESP uptime µs u64 |
| | 76..107 HMAC-SHA256(LMK16, bytes 0..75) |

## Engine packet, type 9

Total 232 bytes. HMAC verification with the derived key precedes any sequence/freshness update. Reject incorrect lengths, nonzero reserved bytes, unsupported schema/enums, wrong boot/source, duplicate/out-of-order packet IDs and reversed sender time. Packet IDs are global u64 and can have gaps. The source proposal sequence is independently u64. Preserve these as integers, not JavaScript Number values; the web API uses decimal strings.

| Offset | Field |
| --- | --- |
| 0..7 | Common header |
| 8 | Boot session u32 |
| 12 | Engine packet sequence u64 |
| 20, 22 | Schema u16=1, flags u16 |
| 24, 28 | Sensor-sample and control-evaluation ages at send, u32 ms |
| 32, 36 | Tune and sensor-profile revisions, u32 |
| 40, 48 | Source proposal sequence and earlier worker-current command sequence, u64 |
| 56, 60 | Source external-configuration phase epoch and worker executor-generation epoch, u32; distinct domains |
| 64, 68, 72 | Controller fault bits, phase-loss count, rejected-cam count, u32 |
| 76 | Cam error, float32 crank degrees |
| 80..89 | Ten u8: state, strategy, source, phase reason, input-valid mask, current timing cause, last timing cause, virtual mask, physical-command mask, board flags |
| 90..91 | Reserved 0 |
| 92 | ECU transmission ESP uptime µs, u64 |
| 100, 104, 108 | Worker tune revision u32, worker sensor revision u32, worker observation age u32 ms |
| 112..143 | Eight input floats: RPM, MAP kPa, TPS %, CLT °C, IAT °C, lambda, battery V, sensor V |
| 144..199 | Fourteen proposal floats: RPM, VE %, target lambda, advance °BTDC, PW ms, dwell ms, deadtime ms, air mg, warmup ratio, afterstart ratio, accel ratio, EGO ratio, duty %, idle % |
| 200..231 | HMAC-SHA256(engine_key32, bytes 0..199) |

State values 0..5 and fault bits match `engine.hpp`; strategy 0=batch/wasted, 1=sequential four cylinders. Source 1=target control observation, 2=synthetic control observation. Phase reasons match `engine_phase.hpp`, timing causes match `timing_executor.hpp`. Input validity bits follow the eight input floats. An invalid input is NaN with its bit clear. Unknown proposal/cam floats are NaN. Infinite values are rejected. Board bits 0..3 mean ADC OK, SAFE high, interlock high and capture overflow. Masks represent software state, without pin readback.

Flags, low to high bits 0..15: present, inputs fresh at control evaluation, storage OK, crank synchronized, phase synchronized, phase required, proposal submitted to worker queue, dummy-load physical policy compiled, phase/revision context matched, proposal active, fuel cut, spark cut, pump proposal, fan proposal, inputs qualified at evaluation, sender display freshness. The selected N16R8 build keeps the dummy policy clear and engine outputs inhibited.

Unknown ages are UINT32_MAX. Finite old ages saturate at UINT32_MAX−1. The sender reads ESP uptime before GP time at publication, calculates GP-source durations, then adds later ESP elapsed time. Publication/transmission never resets the source/control timestamp when observe skipped a step. Worker ages are separate. Sender display freshness means sample/control ages≤1000 ms at transmission; it does not establish current command validity or physical execution.

The receiver must add network/receiver age. The reference implementation uses the authenticated timed query as a clock interval, a 2% relative clock-rate allowance plus 2 ms quantization, and refreshes within 5 seconds. Its conservative transit bound is `max(0, local_elapsed_since_query_send − sender_elapsed_since_reply_send) + ceil(0.02×local_elapsed) + 2ms`. Source/control/worker ages are first rounded upward by `100/98` to cover a slow source clock, including history before the query. Add transit and subsequent receiver-local elapsed time. A repeated source sequence cannot change immutable payload or lower a previous age bound; an unknown repeated age remains unknown. After a gap, fresh negotiation is required. These are explicit clock assumptions, not measured oscillator/RF guarantees. Never compare raw ECU and screen uptime origins or trust a newly arrived packet's freshness bit alone.

## Acknowledge and rate

Type 10 is 56 bytes: common header 0..7, session u32@8, received engine packet sequence u64@12, reserved u32=0@20, HMAC-SHA256(engine_key32, bytes 0..23)@24..55. ACK the newest authenticated, processed engine frame promptly, ideally every frame. The ECU requires a sequence it actually submitted within the last 1 second and within its last 8 submissions for that peer and packet family (engine or legacy sensor, independently). Eight engine packets span about 0.5 seconds at 16 Hz; do not hold an earlier engine ACK for 1 second. It rejects duplicates, old ACKs and reversed time before advancing ACK state. The same recent-send/serial rule now applies to legacy type 6, including legitimate uint32 rollover through 0. A MAC-layer send success is not a screen ACK.

Normal per-peer budget remains up to 20 slots/s. Legacy peers retain their sensor cadence. An opted-in peer normally receives 16 engine packets, 2 legacy sensor packets and 2 metadata packets/s. Capability replies borrow slots and are rate limited; radio congestion/pairing/CPU delays can reduce rates. Busy periods do not create an unbounded backlog. Metadata keeps its session/revision contract, and its session is stamped at transmission. No rate/delivery guarantee is implied.

The UI reports each peer's negotiated engine schema, authenticated connectivity and source age separately. **Connected** means a recent authenticated acknowledgement; the screen can still have stale engine data. Neither an ACK nor a worker command observation proves an output executed. Unpair stops subsequent sends and resets stream keys/capabilities/ACK history for that slot.

## Reproduce

`tools/test_engine_observability.py` compares native C++ and independent Python packet bodies/full HMACs, key length, nonce/counter recovery, replay, clock bounds, stale gaps, unknown values and 64-bit IDs. Native tests cover both ACK widths and recorder limits. [The observability guide](engine-observability.md) links engine-plant, UI, viewer and independent review evidence. Future screen firmware can use `EngineReceiver` as an executable contract; it must implement ESP-NOW peer storage/transport and display behavior separately. No screen, actual RF exchange, range or sealed-enclosure qualification was performed here.
