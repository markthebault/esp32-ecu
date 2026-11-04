Archived development notes. Use the [current A3-120 project](../README.md) for new builds.

# Earlier revision notes

An extensible **generic ECU platform under development**, with editable KiCad files and ESP32-S3 bench firmware. A0 defines a hardware class, not a car model: 12 V, four-cylinder, naturally aspirated gasoline engines with high-impedance port injectors, active-high smart coils and Hall crank/cam sensors.

**This revision is not a working replacement for a vehicle ECU.** Engine scheduling is absent from the flashable image. The portable control algorithms are tested building blocks. No particular car is required to continue developing or bench-testing the platform. Installation later requires a compatible engine profile, wiring adapter and physical qualification.

## Generic platform architecture

The same core PCB and control software should serve multiple makes and models within a defined electrical envelope. Configuration changes belong outside the common control algorithms. Hardware that requires different drive or sensing circuitry belongs in an optional module or revised board.

| Layer | Responsibility | Current state |
|---|---|---|
| Common ECU core | Protected power, timing, acquisition, supervision, fuel/spark calculations and diagnostics | A0 PCB, bench acquisition and portable algorithm library exist; engine scheduling and complete control remain unfinished. |
| Engine profile | Trigger pattern, cylinder/firing arrangement, sensor curves, injector/coil characteristics, fuel/ignition tables and protection limits | Missing-tooth bench decoding is configurable. The full calibration/profile loader is not implemented. |
| Harness adapter | Translate a car's connectors to the ECU's published electrical interface | Per-installation wiring; it need not change the core board. |
| Optional modules | VR conditioning, electronic throttle, other injector/ignition drivers, extra channels and OEM network integration | Extension requirements, not implemented plug-in hardware. A0's I2C header alone is not an actuator expansion interface. |

The first design target is a **class of four-cylinder PFI engines**, independent of brand and year. Naturally aspirated direct-injection engines, incompatible coil interfaces and electronic throttles require additional hardware. Changing a profile cannot add missing power electronics or channels.

Mixture control, misfire response and catalyst protection belong in the common control architecture. Their sensor interfaces, thresholds and calibration are profile-specific. They remain incomplete in A0. Dashboard, immobilizer, transmission, ABS/ESC and A/C protocols are installation-specific integration modules, not something a wiring adapter automatically supplies.

Use [the engine profile template](../docs/engine-profile.template.json) while developing against simulated engines and dummy loads. Make/model/year are optional identification metadata. The [vehicle commissioning record](../docs/vehicle-profile.template.json) is needed when validating an actual installation, not as a prerequisite for generic platform work. Configurable ECUs expose these engine-dependent settings separately; see the [rusEFI configuration guide](https://rusefi.com/docs/guide/).

## Open the design

- [KiCad project](../hardware/esp32-ecu.kicad_pro)
- [Eight-page schematic](../hardware/esp32-ecu.kicad_sch)
- [Four-layer PCB](../hardware/esp32-ecu.kicad_pcb), 200 × 200 mm development format
- [BOM](../hardware/bom.csv) and [electrical contract](../hardware/net_contract.json)
- [Hardware design and limits](../docs/hardware.md)
- [Bench and vehicle validation](../docs/validation.md)
- [Generic engine profile](../docs/engine-profile.template.json) and [later installation record](../docs/vehicle-profile.template.json)

Symbols and footprints are project-local. Use KiCad 10 or newer. `reports/` contains the actual CAD reports and design calculations. No manufacturing release is claimed; the BOM still has generic passives and bench headers.

## What is implemented

The PCB has a TVS, reverse-polarity diode, wide-input buck regulator, supervised 3.3 V rail, external watchdog, physical interlock, four protected injector low sides and four pulse-limited smart-coil signals. It also provides eight analog inputs, conditioned Hall inputs, a silent-by-default CAN interface, three external-relay low sides, UART programming and I2C expansion.

The normal firmware reads the ADC, captures crank edges with MCPWM, decodes a configurable missing-tooth wheel (60-2 by default), counts cam edges, receives CAN at 500 kbit/s without transmitting, and reports raw readings over UART. ARM, pump, fan, injection and ignition remain off. Wi-Fi and Bluetooth are not started.

The host-tested C++ core includes configurable missing-tooth decoding, sensor/voltage/staleness checks, speed-density batch fuel demand, a bounded lambda trim and a deadline-checked edge queue. It does not contain a usable engine tune. Cam phase, sensor transfer curves, engine event planning and target hardware-compare integration remain to be implemented behind the generic profile interface.

## Build and check

```sh
sh scripts/test_firmware.sh
uv run --with platformio --no-project python -m platformio run -d firmware -e esp32s3
sh scripts/check_hardware.sh
```

To change the simulated/bench wheel without editing the decoder, run `uv run --with platformio --no-project python -m platformio run -d firmware -e esp32s3 -t menuconfig` and open **ECU bench trigger profile**. Configure total wheel slots, missing teeth and capture speed ceiling. These settings describe incoming test signals; they do not enable engine actuation. The portable decoder tests cover both 60-2 and 36-1 wheels. The JSON engine profile template is a design contract, not an input file loaded by the current firmware.

The monitor image is `firmware/.pio/build/esp32s3/firmware.bin`. `bootloader.bin`, `partitions.bin` and the ELF are in the same build directory. Use PlatformIO to supply correct flashing offsets. Flash only an assembled bench board through a **3.3 V UART adapter**:

```sh
uv run --with platformio --no-project python -m platformio run -d firmware -e esp32s3 -t upload
uv run --with platformio --no-project python -m platformio device monitor -d firmware -b 115200
```

J2 is GND, board TX, board RX, EN, BOOT. Ground BOOT while resetting EN to enter the ROM bootloader. Power through fused J1. Do not feed 5 V UART levels or power into J2.

The separate `bench` environment emits one-channel, nominally 1 ms pulses once per second, only when J3 and supervision permit. **Use resistor/LED dummy loads only. Leave all vehicle wiring and relay coils disconnected, including MAIN_LS.** The hardware MAIN relay command follows ARM. This image cannot run an engine.

```sh
uv run --with platformio --no-project python -m platformio run -d firmware -e bench
```

## Change the hardware

`scripts/design.py` is the electrical source. Generated native files can also be edited in KiCad; a full regeneration replaces those edits. KiCad's bundled Python provides `pcbnew` on macOS:

```sh
KICAD_PYTHON=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3
"$KICAD_PYTHON" scripts/build_hardware.py
"$KICAD_PYTHON" scripts/route_board.py
java -Xmx4g -Djava.awt.headless=true -jar /path/to/freerouting.jar --gui.enabled=false -de .cache/esp32-ecu.dsn -do .cache/esp32-ecu.ses -inc ground -mp 30 -mt 1 -da
"$KICAD_PYTHON" scripts/route_board.py --import-session .cache/esp32-ecu.ses
sh scripts/check_hardware.sh
```

The router used during development is Freerouting 2.1.0. Router completion alone is insufficient: the supplied board also needed four residual logic routes and explicit ground fanouts. Review/finish remaining nets in KiCad after regeneration; `finish_routes.py` repairs only the known A0 residual nets from `reports/drc.json`. Router results are not deterministic. `--update-metadata` preserves existing copper and placement while updating values and notes; it rejects net or footprint changes. A passing router run is followed by KiCad DRC, schematic parity and visual inspection.

Continue generic development with a signal generator, multiple simulated engine profiles and dummy loads. A specific vehicle is needed at the installation and commissioning stage to validate its adapter, calibration, OEM interfaces and physical behavior. Supporting another compatible engine should require profile and adapter work, rather than a new core PCB.

## Hand-solder revision and printable enclosure

The new **A1** project is [hardware/a1-hand-solder/esp32-ecu.kicad_pro](../hardware/a1-hand-solder/esp32-ecu.kicad_pro). It uses large 1206 hand-solder pads, socketed ESP32 development board, a purchased converter module, and eight individual locking sensor sockets. It is separate from the earlier A0 project and its reports. Use the `hand_solder_a1` firmware environment because the ARM GPIO differs.

See [assembly, sensor pinouts and printing instructions](../docs/hand-solder.md). Printable base and lid, STEP and FreeCAD source are in [enclosure/](../enclosure/). Physical assembly, printed fit and vehicle qualification remain untested.

## Current carrier: A2, genuinely through-hole

**A2 supersedes A1 for home soldering.** All carrier components use through-hole pads: axial resistors, radial capacitors, directly soldered DIP chips and TO-220 power parts. The ESP32-S3-DevKitC-1-N8R8 plugs into two female 22-pin sockets. Small parts on purchased modules are factory assembled.

Open [hardware/a2-through-hole/esp32-ecu.kicad_pro](../hardware/a2-through-hole/esp32-ecu.kicad_pro). Read [A2 assembly, shield/ground wiring and printing](../docs/through-hole.md). Use `through_hole_a2` firmware. The shield-ready enclosure and insulating print parts are in [enclosure/a2/](../enclosure/a2/); the A1 base has different cable entries. EMI control measures are included, but measured immunity and physical assembly/fit are not established. No complete engine scheduler was added.

A2-R2 now includes enlarged PCB screw supports and a gasketed splash-resistant enclosure design. See [mounting and sealing instructions](../enclosure/a2/README.md). Physical splash testing remains outstanding.
