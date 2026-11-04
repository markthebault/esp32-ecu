# IAC-DRAFT2 isolated idle interface

This separate **90 × 60 mm, two-layer THT draft** replaces the IAC-DRAFT1 development path. It has routed copper and native ERC/DRC/connectivity/parity checks, with independent review and conditional circuit experiments in [the evidence](../../reports/engine/idle-isolation/). **Fabrication and powered valve integration remain on hold.** Every shipped firmware environment still disables physical idle writes. Nothing here qualifies a real engine, vehicle, isolation voltage, thermal behavior or enclosure fit.

Use the [native project](isolated.kicad_pro), [schematic](isolated.kicad_sch), [net contract](net_contract.json), [PCB BOM](bom.csv), [harness addendum](harness-bom.csv) and [footprint provenance](footprint-provenance.json). All fitted electrical parts are leaded. DIP devices solder directly, without sockets. NT1 is an unfitted copper connection at the MOSFET source, not an SMD part. Four unplated M3 holes have 82 × 52 mm centres. The older [IAC-DRAFT1](../idle-accessory/) and A3/A4 sources remain historical records.

| Connection | Pin order, PCB top view |
| --- | --- |
| J1, XH4 input | 1 IDLE_CMD; 2 RUN_5V; 3 CARRIER_5V; 4 CARRIER_GND |
| A5 J21, PH4 | 1 IDLE_CMD/GPIO3; 2 RUN_5V; 3 +5V; 4 GND. Harness maps 1→1 through 4→4 to accessory J1 |
| J2, fixed screw terminal | 1 separate externally protected, fused, relay-switched 9–16 V; 2 dedicated actuator return |
| J3, VH2 valve | 1 valve positive; 2 IAC_LS |

J1 and J3 deliberately use different connector families, and J2 uses a fixed screw terminal. Inspect the actual keyed mating view and continuity before power; a wire-side drawing may be mirrored. The new PH header is only on the separate [A5 carrier](../a5-idle-interface/README.md). Do not assume it exists on an A3/A4 board. Carrier J1 and sensor rails cannot supply the valve.

Two input-side 2N3904BU buffers drive the LEDs of two Vishay 6N137 DIP8 optocouplers. Carrier power/return reach only those buffers and LEDs. The detector side has its own LM317AT supply, MCP100-485DI/TO supervisor, SN74HCT02N NOR and UCC27524P.B gate driver. Both command and hardware RUN LEDs must conduct for a valid high command. Supervisor ENA and its 4.7 kΩ pulldown operate independently of that NOR. The 120/374 Ω 1% divider has a calculated DC range of 4.967–5.346 V under the declared datasheet assumptions. That calculation does not bound startup, overshoot, load transients or temperature of an assembly.

The driver switches an IRLZ44NPBF through 33 Ω, with 10 kΩ gate-to-source bias. SB5H100 flyback has its cathode/band at valve positive and anode at the drain. The intended valve is **two-wire, normally closed, energize-to-open, continuous PWM, actual current ≤2 A across 9–16 V and temperature**. There is no current limit, thermal shutdown, valve position/current feedback or separate valve-supply measurement on this draft. The firmware battery value is only a proxy. A drain-source short can energize a normal-current coil without blowing a fuse. An independently operable actuator-branch disconnect is required and remains to be specified and tested.

**Combined RUN drive remains a release hold:** U9 also supplies carrier R47/R50/R53, Q7 and ten HCT inputs. Buffered LEDs do not establish the loaded RUN voltage. R2 is now 2.2 kΩ; the ST 500 µA Q7 figure applies at 10 V/25°C, with a different fault-sink case. Measure actual RUN/MAIN_IN, startup, temperature and fault loading before powered integration.

## Assembly and return routing

The optical barrier has a 5 mm copper-free rule area. Do not bridge it with wires, flux contamination, case foil, a heatsink, mounting hardware or test equipment. This is low-voltage return separation, without a certified isolation rating.

ACT_GND carries coil current directly from Q1 source to J2. LOGIC_GND joins it only through NT1 at the Q1 source copper; it has a separate Kelvin path to U1. Do not add a second logic-to-power ground strap. A return open must not divert coil current into the carrier harness.

**C1–C5, C10, R13 and R14 mount on the back.** C4 is the local 100 nF bypass; C10 is the nearby 1 µF driver bulk capacitor. Their short seeded connections and the source-star path must survive any reroute. U1/U4 front silk outlines are omitted where back-component holes pass underneath; the fabrication layer, courtyard and pin1 marks remain. Read the side in the contract and fabrication drawings, rather than inferring placement from silk alone.

Assemble the front low-profile parts first, trim/inspect their soldered leads before fitting the back parts, and inspect the opposite-side leads before fitting each DIP. Back components and their lead ends must clear front bodies, solder joints and insulating supports. Do not solder a DIP over an uninspected lead end. Exact leaded capacitor/resistor selections, back-component height, lead trim, standoff height and enclosure clearance require a real assembly trial. The old A3 case/ZIP is not a fit model for this additional board. Both TO220 tabs are live at different potentials: Q1 is drain; U6 is regulator output. Do not share an uninsulated heatsink or contact the lining. Stock 1.10 mm TO220 holes have little diagonal lead margin; verify finished holes and the actual procured leads before fabrication approval.

## Debugging and outstanding acceptance

With all power removed, verify the harness pin order, diode/electrolytic polarity, no unintended carrier-to-actuator conductive path and no second LOGIC_GND/ACT_GND join. Use ordinary continuity measurements, not a megohmmeter through electronics. Verify the permanent A5 R154 bias even with J21 unplugged. Read actual GPIO3/JTAG eFuse routing without burning eFuses. Socket pitch, actual N16R8 geometry and antenna RF clearance remain unmeasured.

The first powered experiment must use a current-limited resistor fixture, with an independent actuator cutoff and appropriate isolated/differential measurement. Preserve protective earth; connecting ordinary scope ground clips across the barrier would defeat this experiment. Observe:

| Probe | Reference / interpretation |
| --- | --- |
| J1 pins1/2/3 | J1 pin4, carrier domain. Measure loaded GPIO, RUN and LED supply |
| U2/U3 LED current | Voltage across R3/R4 divided by actual resistance; temperature/storage timing unqualified |
| U6 output / U5 pin1 / U1 ENA | LOGIC_GND. Record startup, reset, rail dropout and release delay |
| U1 VDD/GND | Across pins6/3 at the package. Observe local bypass ringing |
| Q1 gate / drain | Relative to Q1 source, with correct probe isolation/rating |
| J2 return / J1 return | Separate current observations, including deliberately opened returns |

Capture cold startup, reset/download, RUN low, lost command, watchdog/interlock, J1 disconnects, each supply/return open and recovery. Test 0/100%, the actual minimum accepted 1 µs pulse and the full PWM range. A 40 µs test alone cannot establish the 1 µs path. The MCP100 assertion delay has no specified maximum; its 10 µs typical value is not a brownout guarantee. The exact procured UCC27524P/P.B guarantee, opto loading, GPIO levels, passive parts, valve R/L, independent disconnect, protected branch, power-loop temperature, rail stability and real mounting/sealing all remain release items. No board was flashed to enable idle.

Reproduction commands, simulation limitations and review closure are in [the idle hardware guide](../../docs/engine-idle-isolation.md). No manufacturing files are exported from this draft.
