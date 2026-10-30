# ESP-NOW telemetry and screen pairing

This release adds ECU-side radio support. It does not build a screen. All engine outputs remain OFF. A paired receiver can request pairing and acknowledge data; it cannot change calibration, ARM, relays, fuel or ignition.

## Build and module selection

- Original A3 / genuine DevKitC-1 v1.1: `pio run -d firmware -e compact_a3_web`. Built-in WS2812 on GPIO38.
- Selected 44-pin Type-C **N16R8**: `pio run -d firmware -e compact_n16r8_web`. Dedicated board definition, 16 MB QIO flash and 8 MB octal PSRAM initialization. Still a single 2 MB factory app partition, no OTA. Remaining flash is not a filesystem. This variant uses a **separate status WS2812 on GPIO38**, not the supplier's disputed internal LED. No bench pulse build is allowed.

The selected supplier PDF and image are preserved under `hardware/references/`. The new module-fit draft is `hardware/a4-n16r8/`. Its socket row spacing and mechanical stack remain provisional; no A4 fabrication release is supplied. Old A3 zip/binaries are historical and do not include this radio feature.

## Pair and unpair

1. Open the existing ECU service UI on a dry bench, with J3 open at startup. The UART prints a new service Wi-Fi password at each boot. Select **Paired screens**.
2. Hold PAIR/BOOT for 3 seconds, or select **Start pairing**. This creates a fresh 30-second window and random 128-bit setup key. Neither this key nor existing peer keys is broadcast. The setup key appears only in the authenticated radio API/UI and UART.
3. The future screen must tune to channel 6, find the ECU beacon, and receive the setup key through its own local setup interface. Enter the 32 hexadecimal characters. A future screen may provide a QR scanner or configuration tool; no such screen feature is implemented here.
4. The screen sends a keyed request. The ECU presents the candidate's name and MAC. Approve with a short PAIR press or **Approve screen** in the UI. Approval applies only to the current candidate/window. One candidate is accepted per window.
5. The ECU installs the derived encrypted peer temporarily and sends key confirmation. The screen must return authenticated key confirmation before the ECU commits the peer to NVS. The window then closes and its setup key is erased from runtime pairing state. Existing peers remain paired when a window is cancelled or expires.
6. Four screens can be saved. Rebooting restores them and starts with pairing closed. When full, unpair a screen first. Pairing keys are stored separately from the calibration profile. Storage faults do not erase or overwrite the old saved blob automatically.
7. **Unpair** removes the saved peer key first, then removes the radio peer. Subsequent telemetry sends stop for that MAC. An already submitted packet may finish. The receiver's own local saved key cannot be erased remotely, but it no longer receives ECU telemetry and must pair again with a fresh key.

This uses an out-of-band setup key, rather than unauthenticated button-only radio discovery. Anyone who obtains that key during an open window could request pairing; check the candidate before approval. Lost windows require a fresh key. Radio jamming, physical flash extraction and compromised service clients are outside this implementation's protection. Peer keys are in ordinary NVS, not encrypted-at-rest storage.

## LED and button behavior

| State | RGB indication |
| --- | --- |
| Healthy sampling/radio/storage, no missing saved receiver | Steady green |
| Pairing window open, no detected fault | Blinking blue, approximately 2 Hz |
| Detected fault | Blinking red, approximately 2 Hz; overrides blue |

Faults include invalid readings on user-confirmed sensors, sensor-supply voltage outside 4-5.3 V, ADC transfer failure, capture overflow, sample age over one second, peer-storage/radio initialization errors, recent radio queue/send/storage failures, or a saved receiver not acknowledging within three seconds. No crank sync at an idle bench is not itself an LED fault. In the inhibited monitor, a healthy ADC/capture loop feeds the hardware watchdog without requiring crank sync, keeping idle pairing/service available; bench pulse builds retain the valid-trigger requirement. SAFE_N and the physical interlock remain separately visible in diagnostics; an inhibited watchdog with no simulated trigger does not itself imply a radio fault. A green LED is software status, not electrical/vehicle qualification. Reset and early startup may leave the LED dark until the radio task initializes.

PAIR is active-low GPIO0. Inputs are debounced for 30 ms. A button held at startup is ignored until released. A 3-second hold opens pairing once; holding longer does not repeatedly extend the window. A 50-1000 ms short press approves a pending candidate. There is no physical erase-all gesture. **Holding BOOT while resetting/powering up still enters the ESP32 ROM downloader.** Firmware cannot override this strap behavior. RESET preserves saved peers/profile.

## Two sealed buttons and visible status

The existing J2 five-position header provides both contacts, so no new carrier holes or DIP sockets are needed:

| J2 pin | Signal | Connection |
| --- | --- | --- |
| 1 | GND | Common return to both normally-open momentary contacts |
| 4 | EN | RESET contact, other side to pin 1 |
| 5 | BOOT_N / GPIO0 | PAIR contact, other side to pin 1 |
| 2 / 3 | UART TX / RX | Leave isolated from button contacts |

Use a keyed internal plug and short twisted signal/ground pairs, away from noisy power wiring. These are 3.3 V logic contacts, never automotive 12 V. R9 already pulls BOOT_N up. Avoid adding a large capacitor on BOOT_N, which could hold the boot strap low during reset. Verify switch wiring and polarity unpowered.

A practical sealed arrangement without changing case holes is a **sealed two-button pendant** on a round jacketed cable through one existing M16 gland. Use a correctly sized single cable jacket, manufacturer gland seal, strain relief, and an external switch assembly with a specified membrane/actuator seal and sealed cable exit. A bundle of loose wires cannot be sealed by a single-hole gland. If panel-mounted buttons are preferred later, hole sizes, panel thickness and gasket land must follow the exact selected part, with separate leak testing. No unqualified panel holes have been added to the STL.

For the selected N16R8 board, the supplier pinout says internal RGB47 while its schematic says RGB48. A3 uses GPIO47 for ARM and GPIO48 for INTERLOCK. Neither may be driven as a status light. Connect a separate **3.3 V-data-compatible WS2812 module** to GPIO38 (U3 socket pad 32), GND and its specified supply. Include the module manufacturer's decoupling and a short series data resistor (typically 330 ohms); if using a 5 V LED that does not guarantee 3.3 V input, use a suitable level shifter. Keep this lead internal. Use a bonded transparent lens or sealed light pipe to see it through the enclosure, then test that seal. The supplied STL has no validated lens mounting. Do not infer IP protection from the LED module or switch label alone.

## Radio and antenna

The ECU uses its **STA MAC**, not its AP MAC, for ESP-NOW. STA stays disconnected from routers. Service Wi-Fi runs AP+STA on channel 6 and is still refused if J3 is closed at startup. If service AP is refused, the radio runs STA-only. There is one Wi-Fi initialization path at a time; radio and web do not compete to change channels. Wi-Fi power saving is disabled. No internet or router is required.

For the selected board, reserve the user-requested extra **10 mm antenna extension inward** from the first header row with a raised socket stack. Socket pitch, actual envelope and underside height still need measurement. Elevation does not remove RF keepout requirements. The A4 model is a provisional raised envelope, not the selected module's measured model. Copper, tall components and conductive foil above/below the antenna can detune or shield it. Conductive case lining needs a dielectric antenna window or a reviewed antenna arrangement before closed-box use. Range, coexistence, print fit, sealing and EMI tests remain undone.

## Receiver wire contract, version 1

Reference definitions: `firmware/include/ecu/espnow_protocol.hpp`, reference codec `tools/espnow_protocol.py`. No native C++ structure is sent. All integers and IEEE-754 float32 values are explicitly **little-endian**. Packets are at most 98 bytes, below the 250-byte legacy ESP-NOW limit. Use encrypted unicast for saved peers, with channel 6 and the derived 16-byte LMK; use the ECU STA MAC as the receiver's peer address. Use a private random PMK on each device. Only discovery and keyed pairing requests use unencrypted frames.

Every frame starts with 8 bytes: ASCII `ECN1`, uint8 version `1`, uint8 type, uint16 total packet length. Reject unknown versions/types, extra bytes and incorrect lengths.

| Type | Bytes | Payload after header |
| --- | --- | --- |
| 1 beacon | 24 | Random window ID, 16 bytes. Broadcast every 500 ms while waiting for a request. |
| 2 request | 96 | Window ID 16, screen nonce 16, name 24, HMAC-SHA256 proof 32. Name is 1-23 printable ASCII bytes, NUL-padded to exactly 24 bytes. |
| 3 key confirmation | 56 | Window ID 16, HMAC-SHA256 over the first 24 bytes with the derived LMK, 32 bytes. ECU retries every 250 ms after local approval. The receiver verifies, installs/saves the peer and echoes this authenticated confirmation until telemetry arrives. |
| 4 telemetry | 88 | Fields below. |
| 5 sensor metadata | 98 | uint32 profile revision, uint8 sensor index, uint8 conversion mode, NUL-terminated unit[16], label[64], uint32 ECU session ID. |
| 6 acknowledgement | 52 | uint32 session ID, uint32 most recent telemetry sequence, uint32 reserved=0, HMAC-SHA256 over first 20 bytes with LMK, 32 bytes. Send at least once per second. |

Pairing transcript is the concatenation of ASCII `ECU-NOW-PAIR-v1` (15 bytes), window ID (16), ECU STA MAC (6 raw bytes), screen STA MAC (6), screen nonce (16), name (24). Proof = HMAC-SHA256(setup key, transcript). LMK = first 16 bytes of HMAC-SHA256(setup key, transcript with its first byte changed from ASCII `E` to ASCII `K`). Use a cryptographic random nonce. Requests for saved MACs are ignored; unpair before replacing a key. Wrong proofs do not create candidates. The setup key must be transferred locally; it is not included in requests, beacons or telemetry.

| Telemetry offset | Field |
| --- | --- |
| 0-7 | Common header |
| 8, 12, 16, 20 | uint32 boot session ID, global packet sequence, sample uptime milliseconds (wraps), calibration revision |
| 24 | uint16 flags: bit 0 ADC OK, 1 SAFE_N high, 2 interlock high, 3 crank sync, **4 outputs inhibited (always set)**, 5 capture overflow, 6 analog/capture diagnostic fault |
| 26, 27 | uint8 sensor-valid mask and user-confirmed-calibration mask |
| 28-43 | Eight uint16 raw ADC channels |
| 44, 48, 52 | float32 RPM, battery volts, sensor-supply volts |
| 56-79 | Six float32 calibrated readings: MAP, TPS, CLT, IAT, wideband, postcat. Invalid values are NaN and their valid bit is clear. |
| 80 | uint32 CAN receive counter, wrapping low 32 bits |
| 84 | uint32 sample age at transmission, milliseconds |

Metadata mode values: 0 voltage, 1 linear, 2 lookup table, 3 NTC. Unit and label come from the saved profile, so a screen must not assume that a default voltage reading is kPa or temperature. Cache metadata by ECU session, revision and sensor index. Do not display a calibrated physical unit until matching metadata arrives. Metadata rotates every 500 ms, giving a full refresh in approximately three seconds.

The ECU targets a 50 ms four-slot radio cycle (up to 20 packets/s per peer); one in ten turns sends metadata instead of telemetry. Busy-radio intervals drop old samples rather than accumulate a backlog. Completion callbacks release one transmission at a time. No delivery or timing guarantee is implied. The application ACK proves the receiver processed a sequence; a MAC-layer success alone is not treated as connected.

On the future screen, accept only the saved encrypted ECU peer, reset sequence tracking on a new boot session, reject duplicate/out-of-order packets, and mark every reading **stale within one second** without a valid fresh telemetry frame. Add the transmitted sample age to receiver-local elapsed time; do not compare the two devices' uptime clocks directly. Invalid/NaN/unconfirmed readings must remain identifiable. Screens must stay on channel 6; joining another Wi-Fi channel interrupts this link. Acknowledgements have an HMAC in addition to link encryption, so an unencrypted packet spoofing a saved MAC cannot keep its connected indicator alive.

## Verification and limits

Run `sh scripts/test_radio.sh` after the PlatformIO framework is installed; host compilation needs a C++ compiler and OpenSSL development headers/library.

`tools/test_radio.py` checks the synthetic lifecycle and reference codec; `tools/test_web_config.py` covers authenticated radio API actions as well as calibration. `firmware/tests/espnow_test.cpp` checks native framing/endianness and button timing. The simulator clearly labels its synthetic candidate and never claims it is connected. The hardware transport, LED timings, real two-device pairing, reset persistence and RF range still require physical ESP32/receiver tests. The screen itself is outside this repository's scope.

Primary references: [Espressif ESP-NOW API](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/api-reference/network/esp_now.html), [official DevKitC-1 v1.1 reference](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html). The official board's GPIO38 LED assignment does not establish the supplier clone's internal LED wiring.
