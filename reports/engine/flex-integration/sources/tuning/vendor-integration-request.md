# Prepared TunerStudio integration request

This is a local reviewable draft. It has not been sent to EFI Analytics or anyone else.

Proposed recipient: `support@efianalytics.com`, as published in EFI's [support instructions](https://www.efianalytics.com/products/manuals/Setup_EFI_Analytics_Class1_BT_RS232.pdf). Proposed subject: **Independent ESP32-S3 controller: supported TunerStudio integration**. The [prepared email](vendor-integration-email.txt) and [diagnostic attachment](../reports/engine/tuning-online-009/vendor-support.zip) are local files.

We are developing an open-source ESP32-S3 bench ECU research controller. We want supported TunerStudio integration using our own controller identity, without imitating a MegaSquirt or Speeduino signature.

- Project: https://github.com/markthebault/esp32-ecu, development branch `feature/engine-development-sil`.
- Current definition: `tuning/esp32-ecu-secondary.ini`, identity `ESP32ECU DEV 009 INHIBITED`, schema 8. Historical definitions and captures remain records.
- MS-envelope framing, raw/framed `F` returns 002; `f` advertises protocol 2 and 256-byte read/write chunks. `Q` returns our identity.
- One 8192-byte little-endian calibration page. Staged writes; a burn validates/persists/activates the whole tune and resets control. A 640-byte runtime block carries source, age, validity, phase, load and secondary-table diagnostics; stable session origin and separate active/backend/sample revisions are retained.
- Native Linux PTY/TCP reproduction and target native USB Serial/JTAG implementation. Target physical engine writes are compiled out. Physical USB behavior remains unmeasured.
- Unmodified TunerStudio MS Lite 3.3.01 parses the current INI and handles offline MSQs. A fresh own009 online trial on 2026-11-04 records 1,640 correctly framed/CRC-validated exchanges and 328 explicit `Unsupported Controller Firmware: ESP32ECU DEV 009 INHIBITED` warnings, before any calibration/runtime read, write or burn command.
- Historical own003 was rejected with both incorrect F003 and corrected F002 responses. Own004/F002 was also rejected. Earlier immutable repository packets retain those trials; the new attachment uses current own009.
- The same application connects online to a separate genuine Speeduino production reference pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`, through native RX/TX queues and its real parser/loop. It reads calibration and runtime, edits a VE cell from 85 to 86, receives write/burn acknowledgements, checks the changed whole-page CRC and saves the matching MSQ. This reference test uses synthetic static ADC inputs and a stopped engine; it is not a physical USB/engine test.
- Independent native checks exercise our current Session/Stream, full-page/runtime framing, allocation/CAS/persistence failure behavior and maximum-frame splits. Separate stream-aware capture tools disclose fragmented/coalesced frames, errors and incomplete capture tails. [Current application diagnosis and reproduction](../docs/engine-tuning-application.md) identify the sources and evidence.

We would like the supported onboarding process for an independent controller, any required controller identity registration, commercial/license terms and protocol/definition requirements. Please advise whether a supported own-controller transport/driver is available and which additional integration checks are required. The prepared packet supplies the current INI, bounded wire captures, application logs, screenshots, source hashes and native endpoint reproduction. Online compatibility for our own identity remains unresolved.

Primary references: [EFI definition specification](https://www.efianalytics.com/TunerStudio/docs/EFI%20Analytics%20ECU%20Definition%20files.pdf), [EFI custom-controller FAQ](https://tunerstudio.com/index.php?Itemid=38&id=24&option=com_content&view=article), [serial protocol description](https://www.msextra.com/doc/pdf/Megasquirt_Serial_Protocol-2014-10-28.pdf). The proprietary definition PDF is not redistributed in this repository.
