# Prepared TunerStudio integration request

This is a local reviewable draft. It has not been sent to EFI Analytics or anyone else.

We are developing an open-source ESP32-S3 bench ECU research controller. We want supported TunerStudio integration using our own controller identity, without imitating a MegaSquirt or Speeduino signature.

- Project: https://github.com/markthebault/esp32-ecu, development branch `feature/engine-development-sil`.
- Definition: `tuning/esp32-ecu-development.ini`, identity `ESP32ECU DEV 004 INHIBITED`.
- MS-envelope framing, raw/framed `F` returns 002; `f` advertises protocol 2 and 256-byte read/write chunks. `Q` returns our identity.
- One 4768-byte little-endian calibration page. Staged writes; a burn validates/persists/activates the whole tune and resets control. 216-byte runtime block; stable session origin and separate active/backend/sample revisions.
- Native Linux PTY/TCP reproduction and target native USB Serial/JTAG implementation. Target physical engine writes are compiled out. Physical USB behavior remains unmeasured.
- Tested unmodified TunerStudio MS Lite 3.3.01 parses the INI and handles offline MSQs, but logs `Unsupported Controller Firmware` after valid discovery responses, before any calibration read/write/burn commands.
- The same own003 identity was rejected with both incorrect F003 and corrected F002 responses. Own004/F002 is also rejected. The attached project evidence separates those cases.

We would like the supported onboarding process for an independent controller, any required controller identity registration, commercial/license terms and protocol/definition requirements. Please advise whether a compatible own-controller transport/driver is available. We can provide a minimal INI, MSQ, bounded wire capture, application log and native endpoint reproduction. We make no claim of online compatibility until this is resolved and verified in the application.

Primary references: [EFI definition specification](https://www.efianalytics.com/TunerStudio/docs/EFI%20Analytics%20ECU%20Definition%20files.pdf), [EFI custom-controller FAQ](https://www.tunerstudio.com/index.php/support/faqs/24-faqs), [serial protocol description](https://www.msextra.com/doc/pdf/Megasquirt_Serial_Protocol-2014-10-28.pdf). The proprietary definition PDF is not redistributed in this repository.
