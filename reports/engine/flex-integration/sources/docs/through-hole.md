# A2: through-hole ECU development carrier

A2 replaces the A1 assembly choice. The user-soldered carrier has **no SMD components**. Open `hardware/a2-through-hole/esp32-ecu.kicad_pro`. This is a bench prototype, not a qualified vehicle ECU or a manufacturing release. The firmware is an inhibited monitor, with portable engine-control experiments; it still lacks a complete engine scheduler and full profile loader.

## Parts you solder at home

| Function | Physical assembly |
|---|---|
| Resistors | Axial bodies about 6.3 x 2.5 mm, 10.16 mm hole spacing; ordinary leaded resistors |
| Small capacitors | Leaded ceramic discs, approximately 5 mm diameter, 5 mm lead spacing |
| Timing capacitors | Leaded film capacitors, 7.2 x 5 mm footprint, 5 mm lead spacing |
| Electrolytics | Radial cans, 8 mm diameter, 3.5 mm lead spacing |
| Logic, watchdog, CAN, ADC | DIP-8, DIP-14 or DIP-16; 2.54 mm pins, 7.62 mm row spacing; solder the chips directly to the PCB, without IC sockets |
| Power drivers and 3V3 regulator | Upright TO-220 parts with 2.54 mm leads |
| Input clamps and diodes | Leaded axial packages; the large input TVS is mounted vertically |
| Board connectors | Through-hole, polarized XH/VH plugs, plus service headers |
| ESP32 and buck converter | Purchased assembled modules; only their large sockets/headers are soldered on this carrier |

Solder from the underside with a standard temperature-controlled iron, flux and lead cutters. Resistors, small capacitors and diodes go first; then the DIP ICs, TO-220 parts, tall capacitors and connectors. Observe diode bands, capacitor polarity and the DIP pin-1/notch markings. The DIP ICs are soldered directly; the ESP32-S3 remains on plug-in female headers. Insert the purchased modules after inspection and current-limited supply checks. Clip underside leads to no more than about 2 mm above the solder joint surface and check the actual remaining insulation clearance.

The BOM is an engineering BOM. Generic passive entries still need exact voltage, power, tolerance, temperature, dielectric, ESR and package selection. In particular do not replace timing film capacitors with arbitrary electrolytics. Do not force a different part's leads into a footprint because its electrical name is similar.

## Plug-in ESP32-S3

Use an **Espressif ESP32-S3-DevKitC-1-N8R8, hardware v1.1**, purchased with male pins already fitted, and two **1 x 22 female sockets on 2.54 mm pitch**, with **22.86 mm between rows**. The example image shows the intended plug-in construction, but its ESP32-WROOM-32 board is not the S3 pinout. This carrier is specifically for the 44-pin S3 board. Boards sold as “ESP32” or “ESP32-S3” can have different widths, pin counts and mappings. Verify the actual purchased board against the header table and mechanical drawing before ordering PCBs.

A2 ARM is GPIO47, avoiding the v1.1 RGB LED on GPIO38. Interlock remains GPIO48. GPIO35/36/37 are unused, allowing the N8R8 module's octal PSRAM connections. Build `through_hole_a2`, not the original A0 firmware environment. PSRAM is not required by this firmware. The 3D module model is a dimensioned assembly envelope, not manufacturer detailed CAD.

The DevKit's 3V3 pins are supplied by the carrier. Its 5 V pin is deliberately unconnected. **Do not attach either powered USB port while the carrier is supplying it.** Flash using J2 and a 3.3 V external UART adapter without its power wire. Boot/reset are on J2. Electrically isolate/disconnect carrier power and external signals if programming the removed module by USB. This follows Espressif's mutually exclusive USB/5V/3V3 supply options. Mechanically retain the plug-in modules before any vibration testing. Radios are not started, and the conductive enclosure is intended for wired operation.

## Sensor and actuator plugs

The pin authority is `hardware/a2-through-hole/connector-pinout.csv`. PCB pin 1 has a square pad. For the eight individual sensors, use JST B3B-XH-A headers, XHP-3 housings, and compatible SXH contacts/wire. Pre-crimped pigtails avoid needing a specialist crimper. Check each actual sensor's connector pin numbers and voltage requirements; colors are not authoritative.

| Plug | Connection | Pins 1 / 2 / 3 |
|---|---|---|
| J11 | MAP | Ground / sensor 5 V / signal |
| J12 | TPS | Ground / sensor 5 V / signal |
| J13 | Coolant temperature | Ground / sensor 5 V / signal |
| J14 | Intake temperature | Ground / sensor 5 V / signal |
| J15 | External wideband controller output | Ground / sensor 5 V / 0-5 V output |
| J16 | Buffered post-catalyst output | Ground / sensor 5 V / buffered output |
| J17 | Hall crank sensor | Ground / sensor 5 V / signal |
| J18 | Hall cam sensor | Ground / sensor 5 V / signal |

Two-wire temperature sensors use pins 1 and 3, with a matching pull-up populated. The shared sensor supply has a 100 mA PTC, with temperature derating and slow trip. It cannot power an oxygen-sensor heater, wideband controller, injector, coil, or arbitrary 12 V sensor. Hall and NTC pull-ups remain DNP until the sensor requirements are known. Identical sensor housings need durable labels and a wiring check before energizing.

J1 is externally fused key-on logic power. J8 commands external relay coils. J9 carries four injector low sides and ground pins. J10 carries four 5 V smart-coil logic commands and a ground. These use larger 3.96 mm JST VH headers with matching VHR housings. Actuator 12 V remains external, fused and relay-switched. There is no direct coil-primary or GDI drive. The current targets remain 1.2 A per high-impedance injector and 150 mA per external relay, pending physical thermal/clamp tests. Driver current limits are much higher than these targets and do not replace branch fuses. TO-220 driver tabs are electrically live drains: do not share an uninsulated heatsink or touch them to the lining.

J19 is the dedicated actuator-current return. Both pins are ground. Use properly sized return wires to the engine/battery ground star; do not return injector current through sensor wires. Logic-power ground and actuator returns must be wired to the designated common reference, keeping the power loop away from sensor pairs.

J7 CAN now has **four** pins: CANH / CANL / ground / shield. MCP2562 is a DIP transceiver. With JP1 open it is in standby and does **not** deliver ordinary full-rate CAN reception. Close JP1 on an appropriate supervised bus to use firmware listen-only reception. JP2 termination is open by default. Do not add termination to an already terminated vehicle bus.

## Changes for interference control

These are implemented design measures, not measured immunity:

- Four-layer PCB with a continuous inner ground-reference region and no deliberate split through the sensor or logic area. Through-hole antipads and the edge antenna keepout still make local openings. Signals must not be routed on the ground-reference layer.
- Input TVS near J1, reverse-polarity diode, 47 µH radial input filter, local 47 µF and ceramic capacitors, and a 1 ohm/47 µF series-RC damping branch. Converter stability, cold-crank behavior and pulse survival remain physical tests. The converter is a purchased Pololu D36V6F5 module, not a bare fine-pitch power IC.
- Sensor/Hall front ends at the sensor edge. Raw cable inputs have RF shunt capacitors to CHASSIS before their series resistors; divided analog inputs retain local RC filters and leaded clamp diodes. Verify clamp leakage/offset over temperature and crank-edge delay over the full speed range.
- Schmitt input conditioning in a DIP SN74HC14, with two inversions per signal to preserve polarity. SPI clock and MOSI have 47 ohm source resistors.
- Local bypass capacitors beside DIP supplies, capacitor ground returns into the reference plane, and a short wide injector-return bus to J19 at the opposite end from the analog front ends.
- A separate CHASSIS copper region beside the sensor connectors and shield lug H5. H5 bonds by a short broad braid to the enclosure stud; J20 is an auxiliary CHASSIS connection. Sensor ground is not a substitute for a cable-shield termination.
- Conductive enclosure lining, insulated from the circuitry, and cable-shield bonding at enclosure entry. Plastic alone does not provide an RF shield.

This is **not galvanically isolated**. CHASSIS and circuit ground have a 1 Mohm static bleed and 4.7 nF RF coupling. Connect the internal enclosure bond to the installation's designated chassis reference through a sealed cable entry. Keep shields continuous to their specified termination, use signal/return twisted pairs, and separate sensor wiring from ignition/injector/relay wiring. Use short CAN stubs and a twisted CAN pair. Clip-on harness ferrites can be evaluated during testing; they are not a substitute for correct returns and shielding.

## A2-R2 screw mounts and splash-resistant enclosure

The latest mechanical revision adds four enlarged M3 insert supports, eight lid screws, a continuous sheet-gasket groove, sealed-gland provisions and a rain skirt. All supports match the existing PCB holes; no PCB routing or firmware change is needed. Use the new base, lid and dielectric covers together.

Read [enclosure assembly, mounting hardware and splash sealing](../enclosure/a2/README.md) before printing. The base is 218 x 218 mm; the new overhanging lid is 222 x 222 mm. Gasket material, glands and inserts are purchased parts. The CAD checks pass, but physical fit, sealing and insert retention remain untested. There is no IP rating or immersion/pressure-wash claim.

The shield bond is now internal, with no unsealed side-stud hole. Keep conductive lining and bonds inside the water gasket and use the revised templates.

## Verification and remaining physical work

A2 reports are in `reports/a2/`, separate from A0/A1. ERC, DRC, exact pad/net mapping, through-hole-only carrier audit, GPIO-to-header audit, mounting datums and firmware builds are software/CAD checks. Closed STL meshes are geometry checks. They do not establish physical fit, EMI immunity, load-dump survival or engine operation.

Before connecting a fueled engine: measure watchdog startup/stall behavior, supply load steps and input-filter ringing, temperatures in the closed enclosure, coil/injector dummy-load switching and flyback, ADC offsets under load, false crank edges under ignition noise, resets, ESD and conducted/radiated immunity. Monitor raw ADC, crank counts, safe-state transitions and all outputs during testing. Actual vehicle operation also needs complete engine firmware, calibration and installation commissioning.

A2 watchdog U4 is MAX1232EPA+, with TD high and TOL low. Watchdog timeout is **500–2000 ms (1.2 s typical)**, reset time 250–1000 ms. The 3V3 supervisor is MCP120-315DI/TO with the D bondout (RESET / VDD / GND). These replace A1's SOT-23 supervisors. Software and boot must service the watchdog within the minimum timeout; no hardware timing guarantee is inferred from a successful build.

## Primary references

- [Espressif S3 DevKitC v1.1, header mapping and supply methods](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html)
- [Espressif mechanical drawing](https://dl.espressif.com/dl/DXF_ESP32-S3-DevKitC-1_V1_20210312CB.pdf)
- [TI SN74HCT08N DIP](https://www.ti.com/product/SN74HCT08/part-details/SN74HCT08N), [TI HCT221 timing](https://www.ti.com/product/CD74HCT221)
- [Analog Devices MAX1232](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX1232.pdf)
- [Microchip MCP120/130](https://ww1.microchip.com/downloads/cn/DeviceDoc/cn_11184d.pdf), [MCP2561/2](https://ww1.microchip.com/downloads/en/DeviceDoc/25167A.pdf)
- [ST VNP35N07-E](https://www.st.com/resource/en/datasheet/vnp35n07-e.pdf), [LD1117](https://www.st.com/resource/en/datasheet/ld1117.pdf)
- [Bourns RLB choke](https://www.bourns.com/docs/product-datasheets/rlb.pdf), [Diodes SB5100](https://www.diodes.com/datasheet/download/SB5100.pdf)
- [Pololu D36V6F5](https://www.pololu.com/product/3792)
- [TI EMI reduction and ground shielding](https://www.ti.com/lit/an/snva810/snva810.pdf)

Regeneration is a developer operation. `scripts/build_through_hole.py` replaces A2 placement and copper. The delivered PCB is already routed; do not regenerate it just to open or manufacture-review it. `--metadata` refreshes source sheets and BOM and must still be followed by parity checks. `scripts/add_a2_models.py` attaches the purchased module assembly envelopes for rendering. Routing used Freerouting 2.1.0 with explicit `--router.stop_pass_no=15 --router.max_threads=1 --router.optimizer.enabled=false`; its older `-mp` flag alone did not bound this run. Reviewed residual connections and sensitive timing routes were completed with the project repair scripts, then checked in KiCad. Those scripts are not general-purpose PCB routers.
