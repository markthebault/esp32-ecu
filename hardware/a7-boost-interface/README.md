# A7 shared idle/boost interface draft

This separate **120×120mm, six-layer, through-hole carrier** derives from A6. J21 is now a five-position JST ZH header and R180 permanently biases GPIO45 low. The ESP32 remains a plug-in44-pin N16R8 board. All physical engine and boost writes remain inhibited. **No fabrication release or powered-engine acceptance is granted.** A3 through A6, their manufacturing records and cases remain unchanged.

Open [the native project](esp32-ecu.kicad_pro), [schematic](esp32-ecu.kicad_sch), [contract](net_contract.json), [reference BOM](bom.csv), [grouped BOM](bom-grouped.csv) and [source provenance](source-provenance.json). Fresh native ERC, all-severity DRC, connectivity and schematic parity have zero findings. Independent review separately checks retained copper and pad geometry. These checks do not establish current capacity, RF, electrical transients or assembly fit.

| J21 PCB pin | Signal | Harness destination |
| --- | --- | --- |
| 1 | IDLE_CMD, GPIO3 | Original isolated idle J1 pin1 |
| 2 | RUN_5V | Idle J1 pin2 and boost J1 pin2 |
| 3 | +5V, optical inputs only | Idle J1 pin3 and boost J1 pin3 |
| 4 | Carrier GND | Idle J1 pin4 and boost J1 pin4 |
| 5 | BOOST_CMD, GPIO45 | Boost J1 pin1 |

J21 is **B5B-ZR-3.4(LF)(SN)**, with ZHR-5 housing. It replaces A5/A6's PH4 header. Use the dedicated [shared harness BOM and continuity map](../boost-control/harness-bom.csv); do not modify or reuse a PH4 loom by assumed pin position. Each crimp takes one specified conductor. Three insulated, strain-relieved joints split RUN,5V and GND. No actuator supply or return passes through this loom.

R180 is a2k2,1% ordinary compact leaded resistor in a vertical DIN0204 footprint. Its bias remains with J21 unplugged. GPIO45 is a strapping pin: confirm the actual module's memory-voltage/eFuse/reset/download behavior without burning eFuses. Firmware allocation is still inactive. GPIO38 retains A6's development flex-input assignment; it must not drive the older WS2812 wiring.

The existing pluggable-module geometry and inward10mm antenna reservation remain provisional. The new routes avoid that reservation, but inherited copper has no new RF qualification. Check real socket spacing, module elevation, header crimp access, ordinary-iron assembly and case clearance. The old A3 case/ZIP does not fit-qualify A7 plus its accessories.

[Native front assembly drawing](assembly-front.svg) · [Mirrored back assembly drawing](assembly-back.svg). These are source drawings, without a printed-fit claim.

See [the boost accessory](../boost-isolated/README.md) and [electrical experiments and debug procedure](../../docs/engine-boost-hardware.md). The independent actuator cutoff, actual coil, supply protection, loaded RUN headroom and physical timing remain open.
