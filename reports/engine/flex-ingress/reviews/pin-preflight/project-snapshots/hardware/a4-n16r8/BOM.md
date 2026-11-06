> PROVISIONAL: selected N16R8 module; socket spacing and antenna fit unmeasured. No A4 fabrication release. See README.md and ../../docs/espnow.md.

# A4-N16R8 provisional bill of materials

Quantities are for **one board and one enclosure**. The design has 204 fitted electronic component references and four optional DNP resistors. The two ESP32 female socket strips are additional purchases.

[Download grouped shopping CSV](bom-shopping.csv) · [Per-reference assembly CSV](bom.csv) · [Connector pinout](connector-pinout.csv)

Rows marked **Exact part selection required** are specification lines, not fully sourced parts. Select the actual manufacturer part and confirm lead pitch, body size, ratings, ESR and temperature range. Prices and stock are not validated by this BOM. The design remains a bench prototype with outputs disabled.

H1-H4 mounting holes, H5 plated shield lug and TP1-TP6 test pads are fabricated PCB features, not extra electronic parts. H5 hardware is counted with the enclosure hardware. The ESP32 uses sockets; the other DIP chips solder directly to the carrier.

C5/C6 are 22 uF, 16 V radial electrolytics on the 5 V rail. Their stale X7R wording has been corrected to match the existing footprint. C9 still requires an exact electrolytic series with the stated ESR target and regulator stability review.

## PCB

| Qty | Optional | Item | MPN / specification | References / use | Package | Selection |
| ---: | ---: | --- | --- | --- | --- | --- |
| 3 | 0 | 47u 63V | Select exact part | C1, C2, C45 | Radial electrolytic / D8 / P3.50 mm | Exact part selection required |
| 2 | 0 | 100n 100V | Select exact part | C3, C46 | Ceramic disc / D5 / P5.00 mm | Exact part selection required |
| 2 | 0 | 22u 16V electrolytic | Select exact part | C5, C6 | Radial electrolytic / D8 / P3.50 mm | Exact part selection required |
| 1 | 0 | 22u 10V ESR 0.3-1R | Select exact part | C9 | Radial electrolytic / D8 / P3.50 mm | Exact part selection required |
| 17 | 0 | 100n | Select exact part | C10, C14, C15, C16, C28, C32, C33, C34, C35, C36, C37, C38, C39, C40, C41, C42, C43 | Ceramic disc / D5 / P5.00 mm | Exact part selection required |
| 3 | 0 | 1u | Select exact part | C11, C12, C29 | Boxed film / 7.2 x 5 / P5.00 mm | Exact part selection required |
| 1 | 0 | 10u | Select exact part | C13 | Radial electrolytic / D8 / P3.50 mm | Exact part selection required |
| 8 | 0 | 10n | Select exact part | C20, C21, C22, C23, C24, C25, C26, C27 | Ceramic disc / D5 / P5.00 mm | Exact part selection required |
| 2 | 0 | 100p C0G | Select exact part | C30, C31 | Ceramic disc / D5 / P5.00 mm | Exact part selection required |
| 1 | 0 | 4.7n 100V | Select exact part | C47 | Ceramic disc / D5 / P5.00 mm | Exact part selection required |
| 4 | 0 | 270n 5% FILM | Select exact part | C61, C62, C63, C64 | Boxed film / 7.2 x 5 / P5.00 mm | Exact part selection required |
| 4 | 0 | 68n 5% FILM | Select exact part | C81, C82, C83, C84 | Boxed film / 7.2 x 5 / P5.00 mm | Exact part selection required |
| 6 | 0 | 1n C0G 100V | Select exact part | C150, C151, C152, C153, C154, C155 | Ceramic disc / D5 / P5.00 mm | Exact part selection required |
| 2 | 0 | 100p C0G 100V | Select exact part | C156, C157 | Ceramic disc / D5 / P5.00 mm | Exact part selection required |
| 1 | 0 | 1.5KE27CA | 1.5KE27CA | D1 | D DO-201AD P5.08mm Vertical AnodeUp | MPN specified; stock not checked |
| 1 | 0 | SB5100 | SB5100-B | D2 | D DO-201AD P15.24mm Horizontal | MPN specified; stock not checked |
| 21 | 0 | BAT85 | BAT85,113 | D3, D100, D101, D110, D111, D120, D121, D130, D131, D140, D141, D150, D151, D160, D161, D170, D171, D200, D201, D210, D211 | D DO-35 SOD27 P3.81mm Vertical AnodeUp | MPN specified; stock not checked |
| 2 | 0 | P6KE24CA | P6KE24CA | D22, D23 | D DO-15 P12.70mm Horizontal | MPN specified; stock not checked |
| 1 | 0 | PTC 100mA radial | MF-R010 | F2 | PTC MF R010 | MPN specified; stock not checked |
| 1 | 0 | FUSED_KEY_12V | B2P-VH(LF)(SN) | J1 | JST VH B2P-VH 1x02 P3.96mm Vertical | MPN specified; stock not checked |
| 1 | 0 | UART_FLASH_3V3_ONLY | Select exact part | J2 | PinHeader 1x05 P2.54mm Vertical | Exact part selection required |
| 1 | 0 | NORMALLY_OPEN_INTERLOCK | Select exact part | J3 | PinHeader 1x02 P2.54mm Vertical | Exact part selection required |
| 1 | 0 | EXPANSION_3V3 | Select exact part | J4 | PinHeader 1x05 P2.54mm Vertical | Exact part selection required |
| 1 | 0 | CAN_H_L_G_SHIELD | B4B-XH-A(LF)(SN) | J7 | JST XH B4B-XH-A 1x04 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | EXTERNAL_RELAYS | B4P-VH(LF)(SN) | J8 | JST VH B4P-VH 1x04 P3.96mm Vertical | MPN specified; stock not checked |
| 1 | 0 | INJECTOR_LOW_SIDES | B8P-VH(LF)(SN) | J9 | JST VH B8P-VH 1x08 P3.96mm Vertical | MPN specified; stock not checked |
| 1 | 0 | SMART_COIL_5V_LOGIC | B5P-VH(LF)(SN) | J10 | JST VH B5P-VH 1x05 P3.96mm Vertical | MPN specified; stock not checked |
| 1 | 0 | MAP | B3B-XH-A(LF)(SN) | J11 | JST XH B3B-XH-A 1x03 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | TPS | B3B-XH-A(LF)(SN) | J12 | JST XH B3B-XH-A 1x03 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | CLT | B3B-XH-A(LF)(SN) | J13 | JST XH B3B-XH-A 1x03 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | IAT | B3B-XH-A(LF)(SN) | J14 | JST XH B3B-XH-A 1x03 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | LAMBDA_WB | B3B-XH-A(LF)(SN) | J15 | JST XH B3B-XH-A 1x03 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | POSTCAT_BUF | B3B-XH-A(LF)(SN) | J16 | JST XH B3B-XH-A 1x03 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | CRANK | B3B-XH-A(LF)(SN) | J17 | JST XH B3B-XH-A 1x03 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | CAM | B3B-XH-A(LF)(SN) | J18 | JST XH B3B-XH-A 1x03 P2.50mm Vertical | MPN specified; stock not checked |
| 1 | 0 | POWER_RETURN | B2P-VH(LF)(SN) | J19 | JST VH B2P-VH 1x02 P3.96mm Vertical | MPN specified; stock not checked |
| 1 | 0 | SHIELD_BOND | B2P-VH(LF)(SN) | J20 | JST VH B2P SHIELD Compact | MPN specified; stock not checked |
| 1 | 0 | CAN_TX_ENABLE_OPEN | Select exact part | JP1 | PinHeader 1x02 P2.54mm Vertical | Exact part selection required |
| 1 | 0 | CAN_TERMINATION_OPEN | Select exact part | JP2 | PinHeader 1x02 P2.54mm Vertical | Exact part selection required |
| 1 | 0 | 47uH input filter | RLB0914-470KL | L2 | L Radial D10.0mm P5.00mm Fastron 07P | MPN specified; stock not checked |
| 7 | 0 | VNP35N07-E | VNP35N07-E | Q1, Q2, Q3, Q4, Q5, Q6, Q7 | TO-220-3 vertical | MPN specified; stock not checked |
| 1 | 0 | 100R 0.25W | Select exact part | R7 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 31 | 0 | 10k | Select exact part | R8, R9, R11, R12, R14, R15, R38, R44, R45, R47, R51, R52, R53, R54, R55, R65, R66, R67, R68, R85, R86, R87, R88, R105, R106, R107, R108, R115, R116, R117, R118 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 8 | 0 | 1k | Select exact part | R13, R48, R49, R50, R101, R102, R103, R104 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 2 | 0 | 4.7k | Select exact part | R16, R17 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 7 | 0 | 22k 1% | Select exact part | R20, R22, R24, R26, R28, R30, R36 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 7 | 0 | 33k 1% | Select exact part | R21, R23, R25, R27, R29, R31, R37 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 0 | 2 | 2.49k 1% NTC | Select exact part | R32, R33 | DIN0207 axial / 2.54 mm upright | Optional - DNP |
| 1 | 0 | 120k 1% | Select exact part | R34 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 1 | 0 | 10k 1% | Select exact part | R35 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 2 | 0 | 33k | Select exact part | R40, R42 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 0 | 2 | 2.2k HALL PULLUP | Select exact part | R41, R43 | DIN0207 axial / 2.54 mm upright | Optional - DNP |
| 1 | 0 | 120R | Select exact part | R46 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 8 | 0 | 100k 1% | Select exact part | R61, R62, R63, R64, R81, R82, R83, R84 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 4 | 0 | 220R | Select exact part | R111, R112, R113, R114 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 1 | 0 | 1R 0.5W damping | Select exact part | R150 | DIN0207 axial / 10.16 mm horizontal | Exact part selection required |
| 1 | 0 | 1M | Select exact part | R151 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 2 | 0 | 47R | Select exact part | R152, R153 | DIN0207 axial / 2.54 mm upright | Exact part selection required |
| 1 | 0 | Pololu D36V6F5 | Pololu 3792 | U1 | Upright purchased module | MPN specified; stock not checked |
| 1 | 0 | LD1117V33 | LD1117V33 | U2 | TO-220-3 vertical | MPN specified; stock not checked |
| 1 | 0 | ESP32-S3 44-pin Type-C N16R8 | ESP32-S3 44-pin Type-C N16R8 | U3 | Plug-in DevKit / 2x22 | MPN specified; stock not checked |
| 1 | 0 | MAX1232EPA+ | MAX1232EPA+ | U4 | DIP-8 / W7.62mm | MPN specified; stock not checked |
| 1 | 0 | MCP120-315DI/TO | MCP120-315DI/TO | U5 | TO-92, wide inline | MPN specified; stock not checked |
| 1 | 0 | MCP3208-CI/P | MCP3208-CI/P | U6 | DIP-16 / W7.62mm | MPN specified; stock not checked |
| 1 | 0 | SN74HC14N | SN74HC14N | U7 | DIP-14 / W7.62mm | MPN specified; stock not checked |
| 1 | 0 | MCP2562-E/P | MCP2562-E/P | U8 | DIP-8 / W7.62mm | MPN specified; stock not checked |
| 5 | 0 | SN74HCT08N | SN74HCT08N | U9, U10, U11, U16, U17 | DIP-14 / W7.62mm | MPN specified; stock not checked |
| 4 | 0 | CD74HCT221E | CD74HCT221E | U12, U13, U14, U15 | DIP-16 / W7.62mm | MPN specified; stock not checked |

## Board / modules

| Qty | Optional | Item | MPN / specification | References / use | Package | Selection |
| ---: | ---: | --- | --- | --- | --- | --- |
| 1 | 0 | Fabricated A4-N16R8 provisional PCB | HOLD: no manufacturing release for A4; module fit and antenna checks pending | Carrier | 120 x 120 x 1.6 mm; six copper layers | Select exact part for fit |
| 2 | 0 | ESP32 female socket strips | 1x22, 2.54 mm, through-hole | U3 left/right socket rows | Two strips; row spacing 22.86 mm | Select exact part for fit |
| 0 | 2 | DevKit male pin strips if not supplied | 1x22, 2.54 mm, through-hole | Only for an unpinned DevKit | Two matching strips | Select exact part for fit |

## Harness

| Qty | Optional | Item | MPN / specification | References / use | Package | Selection |
| ---: | ---: | --- | --- | --- | --- | --- |
| 3 | 0 | Mating crimp housing | VHR-2N | J1, J19, J20 | JST VH 3.96 mm | Manufacturer family identified; stock not checked |
| 1 | 0 | Mating crimp housing | VHR-4N | J8 | JST VH 3.96 mm | Manufacturer family identified; stock not checked |
| 1 | 0 | Mating crimp housing | VHR-5N | J10 | JST VH 3.96 mm | Manufacturer family identified; stock not checked |
| 1 | 0 | Mating crimp housing | VHR-8N | J9 | JST VH 3.96 mm | Manufacturer family identified; stock not checked |
| 8 | 0 | Mating crimp housing | XHP-3 | J11, J12, J13, J14, J15, J16, J17, J18 | JST XH 2.50 mm | Manufacturer family identified; stock not checked |
| 1 | 0 | Mating crimp housing | XHP-4 | J7 | JST XH 2.50 mm | Manufacturer family identified; stock not checked |
| 28 | 0 | JST XH crimp contacts | SXH-001T-P0.6 | All XH mating housings | AWG 28-22; use matching crimp tooling | Contact family identified; match actual wire |
| 23 | 0 | JST VH crimp contacts | SVH-21T-P1.1 OR SVH-41T-P1.1 | All VH mating housings | 21T: AWG 22-18; 41T: AWG 20-16 | Wire-dependent selection required |
| 2 | 0 | Five-position service plug | 1x5 female crimp housing + matching contacts | J2 UART and J4 expansion | 2.54 mm single row | Select exact part for fit |
| 1 | 0 | Interlock mating plug | 1x2 female crimp housing + matching contacts | J3 | 2.54 mm single row | Select exact part for fit |
| 0 | 2 | Jumper shunt caps | 2.54 mm two-pin shunt | JP1 receive enable / JP2 termination | Standard 2.54 mm pitch | Select exact part for fit |

## Enclosure

| Qty | Optional | Item | MPN / specification | References / use | Package | Selection |
| ---: | ---: | --- | --- | --- | --- | --- |
| 4 | 0 | M3 x 6 mm pan-head screws | M3 x 6 mm pan-head screws | PCB mounts, with 0.8 mm nylon washers | See enclosure/a3/dimensions.json and assembly manual | Select exact part for fit |
| 4 | 0 | M3 nylon washers, 0.8 mm thick, about 6 mm OD | M3 nylon washers, 0.8 mm thick, about 6 mm OD | Insulate PCB screw heads | See enclosure/a3/dimensions.json and assembly manual | Select exact part for fit |
| 8 | 0 | M3 x 8 mm pan-head screws | M3 x 8 mm pan-head screws | Lid; use the specified washers | See enclosure/a3/dimensions.json and assembly manual | Select exact part for fit |
| 8 | 0 | M3 flat washers, 0.8 mm thick | M3 flat washers, 0.8 mm thick | Lid clamping | See enclosure/a3/dimensions.json and assembly manual | Select exact part for fit |
| 14 | 0 | ruthex RX-M3Sx4.0 short heat-set inserts | ruthex RX-M3Sx4.0 short heat-set inserts | 4 PCB + 8 lid + 2 internal shield bonds; 4.0 mm nominal bore | See enclosure/a3/dimensions.json and assembly manual | Select exact part for fit |
| 1 | 0 | 2.0 mm soft closed-cell silicone gasket sheet | 2.0 mm soft closed-cell silicone gasket sheet | Cut one continuous 3 mm wide ring using template; nominal 25% compression | See enclosure/a3/dimensions.json and assembly manual | Select exact part for fit |
| 4 | 0 | M16 cable glands or gasketed blanking plugs | M16 cable glands or gasketed blanking plugs | Match jacket OD and use panel sealing washers; no loose wires through single-hole glands | See enclosure/a3/dimensions.json and assembly manual | Select exact part for fit |
| 2 | 0 | Internal bond screws | M3 x 5 mm pan-head | Base and lid shield-bond bosses | Use the specified terminal/washer stack | Select exact part for fit |
| 1 | 0 | PCB shield-lug bolt | M3 x 6 mm | H5 | Check underside nut clearance | Select exact part for fit |
| 1 | 0 | PCB shield-lug nut | M3 nut | H5 | Check underside clearance | Select exact part for fit |
| 3 | 0 | Shield-bond ring terminals | M3 hole; match the selected bond conductor | H5, internal base and lid bonds | Use the specified stack thickness | Select exact part for fit |
| 3 | 0 | Shield-bond star washers | M3 | H5, internal base and lid bonds | Ensure electrical contact without an unsealed wall penetration | Select exact part for fit |
| 1 | 0 | Conductive lining and bond set | Conductive foil/coating + conductive seam bonds + insulated braid | Base/lid lining, J20/H5 and internal bonds | Cut/fit to supplied templates | Select exact part for fit |
| 1 | 0 | Print-material allowance | Suitable filament for actual temperature, fluids and printer | Base, lid, tray, lid insulator and coupon | Use enclosure/a3 STL/STEP | Select exact part for fit |

## External / bench

| Qty | Optional | Item | MPN / specification | References / use | Package | Selection |
| ---: | ---: | --- | --- | --- | --- | --- |
| 1 | 0 | External logic-supply fuse and holder | 1 A fuse + compatible inline holder | J1 fused 12 V input | Off-board | Select exact part for fit |
| 1 | 0 | Bench programming / diagnostic adapter | 3.3 V logic USB-UART, 115200 baud | J2 | Off-board equipment | Select exact part for fit |
| 1 | 0 | Bench supply and measurement tools | Current-limited 12 V supply, multimeter and suitably referenced oscilloscope | Commissioning | Off-board equipment | Select exact part for fit |

## Selection and assembly notes

- Ordinary axial resistors mount upright on 2.54 mm pitch; R150 remains horizontal and needs the stated power rating in the selected body size. Match specified resistor/capacitor tolerance and C0G/film requirements.
- Radial electrolytics use 3.50 mm lead pitch and an 8 mm diameter envelope. Boxed film and disc ceramic footprints use 5.00 mm lead pitch. Confirm height and actual lead dimensions.
- The mating-housing list counts one plug per connector. The contact list is the maximum all-cavity count: 28 XH and 23 VH positions before spares. Leave unused cavities empty, including the supply cavity on passive NTC and externally powered controller interfaces.
- The two VH contact options share one combined quantity. Select the correct terminal for each wire; do not buy the total quantity of both options by mistake. Check actual wire lengths, shields, branches and crimp tooling separately.
- Vehicle-side sensor plugs, sensors, external wideband controller, VR conditioner, relays, coils, injectors and actuator branch fuses are installation-dependent and are not specified by this generic carrier BOM.
- Printed base/lid, insulating tray, lid insulator and coupon come from the supplied files. Gasket sheet, conductive lining, glands and metal hardware are separate purchases. Select actual gland/blank parts for the cable jackets and the stated 24 mm flange envelope.

Manufacturer references: [Pololu D36V6F5 / #3792](https://www.pololu.com/product/3792), [JST XH housings and contacts](https://www.jst-mfg.com/product/pdf/eng/eXH.pdf), [JST VH housings and contacts](https://www.jst-mfg.com/product/pdf/eng/eVH.pdf).

Regenerate with `python3 scripts/build_bom.py`. The native `net_contract.json`, connector pinout and enclosure hardware CSV are the inputs.

Wireless accessories: one separate 3.3 V-data-compatible WS2812 status module, a sealed two-button pendant and matched gland, and a sealed status-light window. Exact parts and physical fit remain to be selected. These are accessory lines in `bom-shopping.csv`, not fitted PCB references. See `../../docs/espnow.md`.
