# Prepared TunerStudio integration request

This is a local reviewable draft. It has not been sent to EFI Analytics or anyone else.

Proposed recipient: `support@efianalytics.com`. Proposed subject: **Independent ESP32-S3 controller: supported TunerStudio integration**. The [email draft](vendor-integration-email.txt) and [current diagnostic ZIP](../reports/engine/tuning-apps-011/vendor-support.zip) are local. Earlier own009 draft/evidence remain in Git and the immutable historical packet.

We are developing an open-source ESP32-S3 bench ECU research controller and want supported TunerStudio integration under our own identity.

- Project: https://github.com/markthebault/esp32-ecu, branch `feature/engine-development-sil`.
- Current definition: `tuning/esp32-ecu-boost.ini`, identity `ESP32ECU DEV 011 INHIBITED`, tune schema10.
- Raw/framedF returns002; capabilityf advertises protocol2 and256-byte chunks;Q returns the own identity.
- One12288-byte little-endian calibration page. Staged writes; burn validates/persists/activates the whole tune and resets control. Runtime1152bytes/1159framed carries source, age, validity, phase/load/secondary/flex/boost diagnostics; origin remains stable and separate from active/backend/sample revisions.
- Native Linux PTY/TCP reproduction uses the shared C++ Session/Stream. Target native USB Serial/JTAG exists with physical engine writes compiled out. Physical USB/load/timing remain unmeasured.
- Unmodified TunerStudio MS Lite3.3.01 parses the current INI, edits all three boost tables and saves matching MSQ calibration offline. A previous three-field unit-label error is corrected without changing binary values/identity.
- A fresh own011 online trial records1685 complete CRC-valid exchanges and337 exact unsupported-firmware warnings before any page/runtime/write/burn request. Captured tails are complete. The earlier own009 rejection is separately preserved.
- The same unmodified JAR previously connected to a separate genuine Speeduino production reference at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. It read pages/runtime, edited VE85→86, received write/burn acknowledgements, checked matching CRC and saved the MSQ. The reference is a stopped-engine source fixture with synthetic ADCs and process-local EEPROM, not a physical ECU/persistence test.
- Independent checks cover native page/runtime framing, full-file byte reconstruction, unit metadata, current editor bounds, actual application edits, browser CAS/roundtrip, split host writes, captured discovery and application rejection. No proprietary executable, private registration data or vendor definition PDF is included.

We request the supported onboarding process for an independent controller: identity registration, commercial/license terms, protocol/definition requirements and any supported own-controller transport/driver. Please identify additional integration checks needed. The attachment supplies the current definition, bounded raw wire capture, actual application files/logs/screenshots and reproduction notes. We have not imitated another controller's identity or patched the application.

[Current diagnosis and reproduction](../docs/engine-tuning-application.md). The prepared message remains unsent. Supported online operation and wider ECU feature parity remain unfinished.
