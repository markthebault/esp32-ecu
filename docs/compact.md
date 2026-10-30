# A3-120 compact carrier

Use `hardware/a3-compact`. The PCB outline is 120 × 120 mm with mounting holes on 112 × 112 mm centers. The ESP32-S3 DevKitC-1 v1.1 plugs into two 1 × 22 female headers. Other DIP parts are soldered directly, without IC sockets. All carrier joints are through-hole. Small factory-soldered parts stay on the purchased DevKit and buck module.

Ordinary DIN0207 axial resistors stand upright on 2.54 mm pitch. R150 remains horizontal. BAT85 diodes use the vertical footprint and its indicated polarity. The upright construction saves area without asking for fine-pitch hand soldering. Use the assembly plot and BOM, inspect each joint and keep trimmed tails at most 3 mm long below the board.

This is a bench prototype. The firmware includes measurement configuration and diagnostics, with every actuator command OFF. It does not implement a functioning engine controller. Do not connect it as a replacement OEM ECU based on these files alone.

The six copper layers are F / GND / signal / signal / GND / B. The native KiCad board and project are the authority for the copper stack and routing. Refer to `reports/a3/validation-summary.json`, fresh ERC/DRC reports and the PDF manual before fabrication. Electrical CAD checks do not establish power/thermal margins, automotive surge immunity, EMC, sensor compatibility or vehicle qualification.

## Matching case

`enclosure/a3` contains a 138 × 150 × 44 mm base and 142 × 154 mm lid, nominally 47 mm high assembled. The four PCB supports use short M3 heat-set inserts, M3 × 6 screws and 0.8 mm nylon washers. Eight lid screws sit outside the continuous splash gasket. Four rear M16 openings take correctly sized cable glands or sealed blanks; PCB JST headers remain inside the enclosure.

The H4 support includes solder-tail reliefs for the actual R35/D210 locations. Align and dry fit the board, trim tails and check clearance. The native nominal solid checks do not establish a physical fit with a particular printer.

Cut the gasket from 2 mm closed-cell silicone sheet. Do not print it in rigid filament. Add conductive lining and internal bonds, then the dielectric tray and lid insulator. The printed plastic and water gasket do not provide EMI shielding by themselves. Splash resistance and shielding still need physical tests; no IP rating is claimed.

## Configuration and instructions

See `docs/web-configuration.md` and `output/pdf/esp32-ecu-a3-build-calibration-debug-manual.pdf`. The sensor/connector guide source is `config/interface-guide.json`, shared between the web UI and PDF. Firmware environment `compact_a3_web` serves the interface over a bench service AP. `compact_a3` keeps Wi-Fi off. Both keep outputs inhibited.

Full regeneration scripts replace routing. Preserve the checked native files and reports when making local changes. The A2 source board is retained separately as an earlier 200 mm revision.
