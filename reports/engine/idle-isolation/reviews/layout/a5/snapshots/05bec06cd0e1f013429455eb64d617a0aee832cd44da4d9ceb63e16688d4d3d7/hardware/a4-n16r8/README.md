# A4 N16R8 module-fit draft

Selected module: **AliExpress 44-pin dual Type-C ESP32-S3 N16R8**, 16 MB flash and 8 MB PSRAM. The unchanged supplier PDF and pinout image are in `../references/`. The PDF's selected cart option says N8R2; Mark explicitly selected **N16R8** in this conversation.

This is a separate copy of A3 with the selected module recorded. The 120 × 120 mm outline, routed nets, 2 × 22 sockets and all engine-output inhibition remain inherited. Existing A3 manufacturing files and packaged firmware target the earlier module and have not been relabelled as A4 releases.

**Fabrication hold:** 44 pins do not define row spacing, module width or socket stack height. The 22.86 mm row spacing and 8.5 mm raised underside are provisional. A 10 mm antenna extension is reserved inward from the first header row. The placed module model uses a new provisional raised envelope with the 10 mm inward extension; it is not a fit-qualified model of the selected board. Do not use it to establish the new module's clearance.

The antenna points toward the PCB interior. Elevating the module does not eliminate antenna detuning from carrier copper, tall components, foil lining or lid metal. The inherited rule area is an A3 provision; the new 10 mm antenna envelope and RF clearance need review against actual module geometry. Do not place other parts under the radiating portion based on elevation alone. The conductive case lining may prevent closed-box ESP-NOW reception. A dielectric antenna window/lining exclusion needs prototype range tests before release.

The pinout image labels the onboard RGB at GPIO47; the listing schematic labels it GPIO48. Both are used by A3 (ARM / interlock). **Do not drive either as an LED.** The selected firmware uses a separate WS2812 status LED on unused GPIO38, accessible at U3 socket pad 32. Use a short internal signal wire and matching GND/supply. GPIO38 must remain disconnected from every other accessory. The module's onboard RGB is unused. No bench pulse firmware is permitted for this module selection.

PAIR/BOOT and RESET dry contacts connect to the existing J2 service header. See [wireless setup and sealed button wiring](../../docs/espnow.md). Native KiCad files retain the same electrical nets; no fresh A4 ERC/DRC or mechanical-fit pass is claimed. KiCad 10 is required for these inherited sources.
