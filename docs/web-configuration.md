# ECU Studio configuration service

The offline interface in `web/index.html` is served directly by the ESP32-S3. It needs no CDN, internet, cloud account or external JavaScript packages. `tools/web_server.py` runs the same page as a clearly labelled desktop simulator. Its readings are synthetic. It uses the firmware's C++ parser and conversion functions through a small host library.

## Device setup

1. Build the `compact_a3_web` PlatformIO environment. The `compact_a3` environment keeps the radio off. Both keep every actuator command and ARM off. A compile-time check rejects combining the service with dummy-load pulse firmware.
2. Remove the DevKit from the carrier before powering its USB port for flashing. Do not combine USB power with the carrier's 3V3 supply. Flash using PlatformIO, then remove USB power and reseat the unpowered module in the correct orientation.
3. Disconnect all actuator harnesses. Open J3 before powering on. Use a current-limited, fused 12 V bench supply. Confirm the 5 V and 3V3 rails first. Wi-Fi current peaks and regulator temperature still require hardware measurement.
4. Attach a 3.3 V UART adapter to J2: ground, ECU TX to adapter RX, ECU RX to adapter TX. Leave the adapter power lead disconnected. Use 115200 baud, 8-N-1.
5. Power up and read the UART log. The AP is named `ECU-Service-XXXX`. A new random WPA2 password is printed on each boot. The AP is refused if J3 is closed at service startup. There is no station mode or internet connection.
6. Join that network and open `http://192.168.4.1`. Use a dry bench with the lid open; conductive lining can block the radio. Do not rely on Wi-Fi while the enclosure is closed or an engine is operating.

## What can be configured

All six analog channels have an editable name, unit, voltage fault window, display filter and calibration confirmation. Conversion modes are voltage only, two-point linear, or a 2-16 point voltage table. CLT/IAT additionally support NTC beta parameters and a measured pull-up value. The pull-up checkbox records a physically fitted resistor; it does not add hardware.

The ADC reference measurement applies to all eight channels. Trigger total slots, missing teeth and RPM ceiling apply to the missing-tooth bench decoder. A geometry change resets synchronization. The cam input is counted, with no 720-degree phase decoding.

A profile changes diagnostic measurement and bench decoding. Fuel maps, ignition timing, DBW, OEM CAN protocols, immobilizer and emissions readiness are not implemented. The generic board is not a universal OEM ECU replacement.

## Save, import and recovery

Save validates the full profile and writes NVS before publishing it to the monitor loop. The UI reports a save only after commit succeeds. Profiles use schema version 1 and a revision counter. An edit based on an old revision receives HTTP 409 instead of overwriting another session's changes. Export before editing; import validates the complete profile and stages it in the editor. Save applies it.

Invalid or unreadable NVS activates the uncalibrated defaults and blocks saving, with an explicit storage fault. Firmware does not erase NVS automatically. Recover through a deliberate bench reflash/partition recovery after preserving any readable data. Do not erase the device to troubleshoot a wiring fault.

The API accepts at most 16 KiB per profile, rejects unknown/duplicate fields and non-finite values, and requires a per-boot session token for writes. Browser writes must have the same origin as the device. No CORS API is provided. Use the private service AP; HTTP itself is not encrypted.

## Connection guides and diagnostics

The Guides page also has a full build/debug manual reader. `config/manual.json` is extracted from the exact finished PDF and embedded in the firmware. Illustrations and printable templates remain in the release PDF/files. The 8 MB target uses a 2 MB factory application partition, with no OTA.

`config/interface-guide.json` is the single source for the web guides and PDF sensor/connector chapters. `config/defaults.json` is deliberately uncalibrated: it displays volts and does not assume a particular sensor curve. Run `python3 scripts/build_shared_guides.py` after changing its generator, build the PDF with `scripts/build_instruction_pdf.py`, then `python3 scripts/embed_web.py` before building firmware. Generated `firmware/main/web_assets.hpp` embeds those same files.

Diagnostics show all eight ADC codes and voltages, battery/sensor rails, SAFE_N, J3, crank/cam GPIO levels and edge counts, missing-tooth sync, capture overflow, CAN frame count and ARM state. CAN is 500 kbit/s listen-only. No decoded OEM data or actuator test commands are supplied. Exports contain the saved/draft profile, status and this browser session's connection events. Fault-injection buttons exist only in the desktop simulator.

Readout filtering uses elapsed time. Electrical faults are checked against instantaneous samples. UI requests time out; stale/disconnected readings lose their valid/live state. Event history is local to the open browser, not an ECU flight recorder.

## Desktop preview and checks

Install the pinned PlatformIO framework by building firmware, then run:

```sh
python3 tools/web_server.py --port 8765
python3 tools/test_web_config.py
sh scripts/test_firmware.sh
```

Open `http://127.0.0.1:8765`. State is kept in `.cache/web/profile.json`, separate from firmware defaults. The host bridge requires a C/C++ compiler and cJSON from the installed ESP-IDF package. Use `--host 0.0.0.0` only if you deliberately want a trusted LAN preview. The simulator is not a hardware-in-the-loop test.
