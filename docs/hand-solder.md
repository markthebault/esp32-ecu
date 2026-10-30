# A1: home assembly revision

Open `hardware/a1-hand-solder/esp32-ecu.kicad_pro`. A0 remains a separate, earlier design. Do not use A0 firmware on A1: ARM moves from GPIO38 to GPIO47 to avoid the DevKitC v1.1 RGB LED. The inhibited monitor build is `hand_solder_a1` in PlatformIO. No engine scheduler was added by this revision.

## Assembly choices

- Resistors: 1206 (3.2 x 1.6 mm) with extended hand solder pads. Capacitors: 1206 ceramics/film where applicable, and the existing large electrolytics. Voltage, dielectric, tolerance and ESR requirements still apply; footprint size does not select a suitable component.
- Logic and ADC: visible-lead SOIC, 1.27 mm pitch. Drivers and LDO: SOT-223. No QFN or hidden thermal pad parts on this carrier.
- The few remaining small packages are SOT-23 and SOT-23-5, with 0.95 mm lead pitch. These are accessible with an iron but need tweezers, flux, a fine chisel tip, and magnification. This is hand-solderable SMD, not an all-through-hole kit.
- Clamp diodes: axial BAT85 mounted vertically. Their forward drop and leakage must be measured over the intended temperature/fault range. This change does not establish ADC or GPIO surge survival.
- Processor: purchased ESP32-S3-DevKitC-1-N8R8 **v1.1**, with two 22-pin female sockets at 22.86 mm row spacing. Measure the actual purchased board before ordering the PCB. Do not substitute a different development board or revision without reviewing its LED, pin map and dimensions.
- Buck: purchased, assembled Pololu D36V6F5 (#3792), mounted vertically by its four 2.54 mm pins. It is a 5 V, up-to-600 mA module whose achievable current depends on input voltage and temperature. The protected-input TVS, reverse diode and input electrolytic remain on the carrier. Its 50 V input limit is not a load-dump certification.
- Injector timing uses 270 kΩ with 100 nF C0G rather than requiring a 270 nF film chip in 1206. The nominal RC product is unchanged; scope the actual window and tolerances.
- Watchdog: TPS3828-33DBVR, open-drain reset with nominal 1.6 s watchdog. U18 monitors the 5 V rail, replacing the old buck PGOOD function. The old TPS3431 timing selection does not apply. Scope startup and heartbeat loss before enabling dummy loads.

Populate small ICs and passives first, then drivers, electrolytics, sockets and connectors. Use the assembly SVG for reference designators. Inspect every joint and test for shorts before inserting the ESP32 or converter. First power up on a current-limited bench supply with J3 open and no actuators connected.

Power the DevKit through the carrier 3V3 pins only. Its 5 V pin is unconnected. **Do not connect either DevKit USB power port while the carrier is supplying it.** Use the carrier's J2 with an external 3.3 V UART adapter and no adapter power wire. The DevKit documentation lists USB, 5 V and 3V3 as mutually exclusive supply methods. Socket contacts require mechanical retention before any vibration testing.

## Plug-in connectors

`hardware/a1-hand-solder/connector-pinout.csv` is the PCB pin authority. The square pad is pin 1. All eight sensor sockets are JST XH 2.50 mm: B3B-XH-A headers, XHP-3 housings, SXH-001T-P0.6 contacts with compatible wire. Buy correctly crimped pigtails if no matching crimper is available. Do not infer wire color or the sensor manufacturer's pin numbering from these PCB numbers.

| Connector | Sensor | PCB pins 1 / 2 / 3 |
|---|---|---|
| J11 | MAP | Ground / sensor 5 V / MAP signal |
| J12 | TPS | Ground / sensor 5 V / TPS signal |
| J13 | Coolant temperature | Ground / sensor 5 V / CLT signal |
| J14 | Intake temperature | Ground / sensor 5 V / IAT signal |
| J15 | External wideband controller | Ground / sensor 5 V / 0-5 V output |
| J16 | Buffered post-catalyst signal | Ground / sensor 5 V / buffered output |
| J17 | Hall crank | Ground / sensor 5 V / crank signal |
| J18 | Hall cam | Ground / sensor 5 V / cam signal |

Two-wire temperature sensors use pins 1 and 3 only, with the appropriate on-board pull-up populated. A wideband controller normally uses its own fused supply: do not power it, an oxygen-sensor heater, or any 12 V sensor from pin 2. Unused pins should be left unpopulated in the mating housing. Sensor 5 V has a shared 100 mA PTC and is not eight independent power channels. Hall pull-ups and NTC pull-ups remain DNP until sensor requirements are known. Different sensors use identical housings, so label both cable ends and verify every harness before power-up.

J1 power, J8 relay coils, J9 injector low sides, and J10 smart-coil logic use larger JST VH 3.96 mm headers with VHR-2N/4N/8N/5N mating housings respectively, and contacts selected for the actual wire gauge (for example SVH-21T-P1.1 for its specified wire range). J7 CAN is XH three pin, CANH / CANL / ground. These are internal, unsealed connectors. Injector and coil 12 V still come from external fused, relay-switched wiring; the sensor connectors do not supply actuators. No direct ignition coil primary connections.

## Printable enclosure

Files in `enclosure/`: `base.stl`, `lid.stl`, optional `cable_blank.stl`, STEP parts, editable `ecu-a1-enclosure.FCStd`, and source generator `scripts/build_enclosure.py`.

- Assembled outer size: 218 x 218 x 47 mm. Allow a 230 x 230 mm build area if using a 5 mm brim. The base and lid are printed separately, flat outside faces on the bed; lid locating lip faces up during printing and down during assembly.
- Base/floor/lid nominal walls: 3 mm. PCB: 200 x 200 x 1.6 mm, on four 6 mm bosses. 2.5 mm pilot holes are intended for appropriate M3 plastic-thread screws, not forced machine screws. Trial the hole diameter on a small sample first.
- Four M3 x 6 PCB screws; four approximately M3 x 10 pan-head plastic-thread lid screws with washers. Check actual screw engagement before tightening. Board underside clearance is 6 mm. A 25 mm top-side component envelope leaves 8.4 mm to the lid underside.
- Four 16.2 mm cable-entry holes accept measured M16 cable glands or suitable grommets. Adjacent 3.2 mm holes accept cable ties for strain relief. The optional blank is a glue-in/retained plug, not a threaded or sealing component. Check actual gland nut clearance and harness bend radius before final printing.
- Start with 0.2 mm layers, four perimeters and 30% infill. Supports may be needed at horizontal cable holes. Deburr holes and remove support before installing wiring. Verify fit with a first print; shrinkage and printer accuracy are unknown.
- PETG is reasonable for a cool indoor bench prototype. Select material using its supplier's measured thermal and flammability data for the installation. This design is for a protected cabin location. No under-hood, waterproof, fire containment, or thermal qualification is claimed. The printed shell provides no conductive EMC shield.

The native CAD and closed STL checks verify geometry, not printed fit or vehicle operation. A0 test reports do not qualify A1. A1's own checks are under `reports/a1/`. Full firmware engine control, surge, thermal, EMI, vibration, actuator, and vehicle commissioning tests remain outstanding.

## Manufacturer references

- [Espressif DevKitC header map and power options](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html), with the linked v1.1 guide for the required revision.
- [Espressif mechanical drawing](https://dl.espressif.com/dl/DXF_ESP32-S3-DevKitC-1_V1_20210312CB.pdf).
- [Pololu D36V6F5 specifications and connection details](https://www.pololu.com/product/3792).
- [TI TPS3828 datasheet](https://www.ti.com/lit/ds/symlink/tps3828.pdf).
- [TI SN74LVC14A](https://www.ti.com/product/SN74LVC14A).
