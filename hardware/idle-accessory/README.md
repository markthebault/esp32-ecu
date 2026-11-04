# Idle accessory placement and netlist draft

This is a separate 80 × 50 mm, two-layer, through-hole accessory with four M3 mounting holes on 72 × 42 mm centres. It preserves the A3/A4 carriers and manufacturing records. DIP 8 and TO220 devices solder directly; resistors stand upright. The copper is **unrouted**, with 28 connections outstanding. There are no manufacturing files or established case-fit dimensions for this accessory.

The [native KiCad project](idle.kicad_pro), [pin contract](net_contract.json), [BOM](bom.csv) and [footprint provenance](footprint-provenance.json) are review material. Native KiCad 9 checks give ERC 0, placement DRC 0 and schematic parity 0, plus the 28 unrouted connections. Those checks establish neither an electrically qualified board nor a printable or sealed fit.

| Connection | Pins / function |
| --- | --- |
| J1, four-pole XH | 1 GPIO3 from module socket pad 13; 2 hardware RUN_5V from TP6; 3 logic 5V from TP3; 4 ground from TP1 |
| J2, fixed screw terminal | 1 externally fused, switched, reverse/transient-protected actuator 12V; 2 dedicated actuator return |
| J3, two-pole VH | 1 valve positive; 2 IAC_LS |

J2 is a fixed [Phoenix Contact 1715721](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-15-2-508-1715721) screw terminal. It cannot accept the J3 valve plug. Review found that identical supply/valve plugs would bypass the switch if exchanged, so the draft uses different connection systems. Terminal torque, wire retention and harness strain relief still require selection/testing.

The candidate chain is GPIO3 → 1 kΩ → [UCC27524P.B PDIP 8](https://www.ti.com/product/UCC27524/part-details/UCC27524P), then 220 Ω → [VNP35N07-E TO220](https://www.st.com/en/automotive-analog-and-power/vnp35n07-e.html). ENA receives hardware RUN_5V through 1 kΩ and has a mandatory 4.7 kΩ pull-down. INB and ENB are grounded; OUTB is unconnected. The switch input has 10 kΩ to source. Its metal tab is the live low-side drain. SB5H100 flyback has its cathode at valve positive and anode at IAC_LS. The 100 nF/1 µF capacitors decouple logic VDD. Exact leaded passive parts, insulation, thermal arrangement and valve remain procurement/qualification items.

The intended load is a two-wire, normally closed, energize-to-open continuous-duty PWM valve on a 9–16 V protected branch, bounded to 2 A. Neither the carrier's 1 A input branch nor its sensor/logic rails supply the valve. Software checks the existing board battery reading as a supply proxy; this draft has no valve-current, position or independent valve-supply feedback. Closing the command does not establish immediate mechanical closure.

**Physical release blockers remain:**

- GPIO3 is a JTAG strap. Read the actual module's eFuse routing without changing it. A permanent 2.2 kΩ carrier-side bias is required at the take-off; accessory R2 disappears when J1 is unplugged. The archived carrier has no new take-off connector or rework implemented.
- The draft joins logic and actuator grounds. If the J2 return opens, coil current can return through J1 and the carrier. Resolve isolation/return protection and verify that fault before powered integration.
- Route and review power/flyback loops and decoupling; specify the external fuse, relay/protection branch and actual valve; characterize current, decay, reset/backfeed and switch temperature. Mechanical mounting, antenna clearance, glands and sealing are unmeasured.

All shipped firmware environments keep idle GPIO writes compiled out. No configuration or UI option changes that policy. The selected N16R8 additionally rejects the experimental physical-idle flag. The draft is not ready for fabrication or powered valve testing.

Reproduce the generated draft only after inspecting local edits:

```sh
/usr/bin/python3 scripts/build_idle_accessory.py --replace-generated
kicad-cli sch erc hardware/idle-accessory/idle.kicad_sch --format json -o NEW_ERC.json
kicad-cli pcb drc hardware/idle-accessory/idle.kicad_pcb --schematic-parity --format json -o NEW_DRC.json
```

Only new footprint copies were adapted for the Linux KiCad 9 loader. The Mac KiCad 10 sources remain intact. The Phoenix terminal comes from a pinned official KiCad commit. Model paths are records, not a verified 3D assembly. See the [idle control guide](../../docs/engine-idle-control.md) for software, tuning and evidence.
