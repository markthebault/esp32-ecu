# A6 compact frontend development checkpoint

The [A6 native project](../hardware/a6-flex-rgb/esp32-ecu.kicad_pro) is a routed 120 × 120 mm six-layer development draft. It combines the protected GPIO38 flex-input candidate, ordinary RGB driver and the inherited isolated-idle interface. Physical engine outputs remain inhibited. Fabrication, sensor connection, module/enclosure fit and physical operation remain on hold.

The selected circuit is [FLEX-G38-FRONTEND-COMPACT-DRAFT2](../hardware/flex-input/frontend-compact.json). The original frontend and A3/A4/A5 sources remain preserved. Use the matching [BOM](../hardware/a6-flex-rgb/BOM.md) and [pinout](../hardware/a6-flex-rgb/connector-pinout.csv), including the new internal J20 PH2 shield connector. Earlier carrier shopping lists and assembly coordinates differ.

Nine low-power resistors use smaller ordinary leaded MRS16 parts at unchanged resistance. The three 750 Ω pullup resistors retain their 0.6 W parts. C158/C159 use C315 C0G parts, C160 uses a C315 X7R part, and C164 adds a local 3.3 V bypass at the comparator pullup. The direct-solder DIP comparator is rotated to shorten its critical connections. J20's PH2 package stays inside the previous VH2 courtyard; both contacts remain CHASSIS, with no normal load current. H5 remains the chassis lug.

The feedback and bypass connections were routed before restoring the rest of the copper. These are added copper lengths, with no added vias in these local branches:

| Connection | Length | Layer |
| --- | ---: | --- |
| U18 output to R160 feedback | 3.798 mm | B.Cu |
| R160 feedback to U18 input | 6.165 mm | In2.Cu |
| C160 to U18 supply | 3.333 mm | F.Cu |
| C164 to R163 pullup supply | 2.257 mm | F.Cu |
| C159 to U18 reference input | 6.612 mm | F.Cu |

Input and comparator-output tracks occupy different layers with an intervening ground plane. All 87 priority copper objects retain their geometry after the full-board routing and stub removal. These facts do not extract capacitance, inductance or ground-return impedance.

Native checks report zero ERC violations, physical DRC findings, open connections, dangling copper and schematic-parity findings. The 264 footprints correspond to 260 schematic components plus four unnumbered mechanical holes; all 779 named schematic/PCB pad bindings match. The width audit checks every track and through via. Three intentionally invalid copies exercise supply, power and unauthorized injector-neck checks. The three exact inherited INJ1 0.8 mm necks remain explicit current/thermal holds.

The nominal compact circuit matrix contains 62 ngspice cases, 3,978,182 retained raw rows and 4,300 Capture observations. It includes intentional delay/loading rejection witnesses. The original 62 emitted decks remain byte-identical for the legacy profile. Nominal new-profile waveforms put the smaller resistors' peak at 45.54 mW and the three pullup resistors' peaks at 422.50 mW each. These are comparisons with nominal P70 references, not assembled derating or pulse/thermal qualification.

Guide version 1.9 identifies A6's PH2 housing and contacts separately from earlier carriers. Its exact data is served by the host and appears in the compiled flash data of all three web builds. The configuration/API suite passes 20 tests. Existing tuning, screen, capture and control formats are unchanged by this layout increment.

The [evidence packet](../reports/engine/a6-compact/README.md) records native checks, full nominal waveforms, independent review, exact compiled ELFs, source bindings and reproduction commands.

Remaining gates include effective X7R capacitance over bias/temperature/aging, ESR/ESL and supply transients; physical parasitics and return paths; formed leads, finished holes and the ceramic manufacturer's soldering process; assembled heat and fault duration; actual N16R8 dimensions, RF and enclosure fit; target timing, loads and HIL. The external sensor plug contradiction and the fact that FLEX_12V is not an 18 V regulator also remain unresolved. Native and nominal-model checks establish none of those physical properties.

This checkpoint does not close other cylinder counts, OEM/VR triggers, boost, VVT, knock, staging, online TunerStudio support or the wider [Speeduino coverage gaps](engine-feature-coverage.md).
