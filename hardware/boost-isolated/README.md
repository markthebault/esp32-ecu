# BOOST-DRAFT1 isolated THT accessory

This **90×60mm, two-layer, through-hole development board** provides a separate optical boost-command/RUN path and low-side inductive driver. It derives from the retained IAC-DRAFT2 board. DIP devices solder directly, without sockets. The carrier remains120×120mm. **Fabrication, valve connection and physical engine outputs remain on hold.**

Use [the native project](isolated.kicad_pro), [schematic](isolated.kicad_sch), [contract](net_contract.json), [reference BOM](bom.csv), [grouped BOM](bom-grouped.csv), [shared harness BOM](../boost-control/harness-bom.csv) and [source provenance](source-provenance.json). Native ERC, all-severity DRC, connectivity and schematic parity have zero findings. Electrical experiments and their independent review are described in [the hardware guide](../../docs/engine-boost-hardware.md).

| Connection, PCB pin order | Function |
| --- | --- |
| J1 ZH4,1/2/3/4 | BOOST_CMD / RUN_5V / CARRIER_5V / CARRIER_GND |
| J2 fixed screw terminal,1/2 | External protected switched9–16V branch / dedicated actuator return |
| J3 VH6,1/2 | Valve positive / BOOST_LS |
| J3 VH6,3..6 | Unconnected; leave housing cavities empty |

A7 J21 pins5/2/3/4 connect to J1 pins1/2/3/4. J1 uses B4B-ZR-3.4(LF)(SN) and ZHR-4. J3 uses B6P-VH and VHR-6N, with only two contacts fitted. Its larger position count distinguishes it from the existing idle/flex/auxiliary valve connectors. Verify the actual keyed mating view and continuity; a cable-side drawing can be mirrored. A5/A6 PH4 and this A7 loom are different revisions.

Q2/Q3 are **TN0702N3-G**, pin1SOURCE, pin2GATE, pin3DRAIN. Their lead order is not the old BJT's function order. R1=1k and R2=4k7 drive10k/100nF gate-source filters. The47Ω/2.2µF/100nF optical LED supply filter suppresses modeled hotplug feedthrough. It also stores energy and distorts short pulses. These component choices have conditional simulation support, without a physical minimum-pulse guarantee. Exact passive MPNs, formed leads and temperature behavior remain procurement/assembly holds.

The detector side retains two6N137s, SN74HCT02N, MCP100-485DI/TO, LM317AT and UCC27524P.B. Its IRLZ44NPBF switches the coil through33Ω gate resistance and10k gate-source bias. SB5H100 flyback has its band/cathode at valve positive. No valve/current rating is assigned. There is no current limit, thermal shutdown or coil/position feedback. A shorted drain-source path can energize the valve at ordinary coil current without blowing a fuse. Provide a separately operable, tested actuator disconnect.

ACT_GND carries coil current between Q1 source and J2. LOGIC_GND joins it only through NT1 at the source, with a separate Kelvin driver return. Keep the5mm optical copper barrier free of wiring, case metal, fixtures and mounting bridges. This is low-voltage return separation, without a certified isolation rating.

**Back assembly:** C1–C5,C10–C12,R13,R14. Trim and inspect opposite-side leads before fitting each DIP or back part. Q2/Q3 front silk outlines are omitted where back-capacitor holes cross; fabrication/courtyard/pin1 features remain. The fitted capacitor bodies, solder joints, formed leads, insulating standoffs and case must be checked physically. Four M3 holes have82×52mm centres. Q1's live tab is the drain; U6's live tab is regulator output. Do not use an uninsulated shared heatsink. No case or Gerber files are released here.

[Native front assembly drawing](assembly-front.svg) · [Mirrored back assembly drawing](assembly-back.svg). Use the declared assembly side and pad numbers rather than apparent left/right wire order.
