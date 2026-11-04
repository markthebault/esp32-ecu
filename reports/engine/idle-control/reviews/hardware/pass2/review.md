# Independent idle accessory review, pass 2

Reviewed 2026-11-04. Read-only review of the separate `IAC-DRAFT1` accessory, its generator, and the default physical policy. This is a placement/netlist review. No routing, manufacturing release, enclosure fit, real valve behavior, or electrical qualification was established. No production files were changed by this reviewer.

The revised draft has the intended pin-level circuit and no connected-net discrepancy. The initially interchangeable supply/valve plugs and unused-output net-name warning were corrected by the implementing agent during this review. The carrier take-off, return wiring, actual module straps, protection branch, routing and powered acceptance remain incomplete. Keep physical outputs disabled.

## Independently reproduced checks

Evidence is alongside this report: `audit.py`, `audit.json`, `schematic.xml`, `erc.json`, `drc.json`, `sources.json`, and the fetched pinned terminal footprint. `audit.json` records the hashes of the reviewed design and policy files.

| Check | Result |
|---|---|
| Native KiCad | 9.0.8 |
| Schematic ERC, all severities | 0 violations |
| PCB placement DRC, all severities | 0 violations |
| Native schematic-to-PCB parity | 0 issues after OUTB_NC correction |
| Unconnected items | 28, intentionally unresolved in this unrouted draft |
| Contract-to-schematic-to-PCB connected pads | All 38 agree |
| Contract parts / PCB footprints | 19 / 19 |
| Copper tracks / zones | 0 / 0 |
| Board | 80 x 50 mm, two copper layers, 1.6 mm thickness |
| Mounts | Four unplated 3.2 mm holes at 72 x 42 mm centers |
| Adapted archived footprint copies | Nine source/copy hashes verified; parsed trees identical after removing only declared version, false-jumper and construction-point metadata |
| New J2 footprint | Tenth unique footprint matches freshly fetched official KiCad bytes at pinned commit and recorded SHA256 |

ERC and placement DRC cannot assess an unrouted current path. The 28 unconnected items must remain prominent whenever these results are reported.

## Pin and power contract

At `scripts/build_idle_accessory.py:20`, J1 is GPIO3, RUN_5V, regulated +5V logic and ground. Archived A4 U3 pad13 is GPIO3 and is currently NC; U9 pin6/TP6 is RUN_5V, TP3 is +5V and TP1 is ground. No carrier connector or ready-made take-off is implied.

At generator line23, U1 uses ENA1, INA2, GND3, grounded INB4, NC OUTB5, VDD6, OUTA7 and grounded ENB8. R3/R4 explicitly bias ENA off if RUN is disconnected. R1/R5 bias INA off if the PWM lead is disconnected. This is consistent with the driver’s active-high enables, internally pulled-high EN pins and inputs whose allowed voltage is independent of VDD. VDD is regulated logic5V. The device’s UVLO provides an additional low-output mechanism during power transitions. These behaviors match the [TI UCC27524 datasheet](https://www.ti.com/lit/ds/symlink/ucc27524.pdf), §§5,7.3,8. The actual layout must still establish short bypass paths and power-sequence behavior.

At line24, Q1 pin1 is INPUT, pin2 and live tab are IAC_LS, and pin3 is SOURCE/ground. R6 limits input drive and R7 provides a local input-to-source pulldown. The switch is suitable for evaluating this low-frequency PWM topology, but its internal current limitation is far above the declared2A load and does not regulate coil current. Its protection feedback is on its input; this circuit has no independent current/fault readback. Numeric on-resistance characterized at10V must not be presented as guaranteed at this5V drive. See the [ST VNP35N07-E datasheet](https://www.st.com/resource/en/datasheet/vnp35n07-e.pdf), diagram, electrical tables and §3. Do not ground the metal tab or attach uninsulated mounting hardware to it.

At line25, D1 pad1/cathode/band is the same positive node as J3 valve+, and pad2/anode is IAC_LS. This is the correct freewheel polarity. The [Vishay SB5H100 datasheet](https://www.vishay.com/docs/88722/sb5h90.pdf) identifies the cathode band and axial DO201AD package. A diode-clamped coil decays after switch-off; commanded duty zero does not demonstrate immediate valve closure. Actual inductance, decay, voltage overshoot and thermal behavior remain unmeasured.

## Findings corrected during review

1. **Interchangeable actuator supply and valve plugs bypassed control.** Initially J2 and J3 were both B2P-VH. Swapping the two harness plugs preserved the shared positive node and directly grounded valve−, energizing the valve continuously regardless of Q1, PWM or RUN. J2 is now fixed Phoenix1715721 screw supply entry while J3 remains the VH valve plug (`build_idle_accessory.py:21-22`). The harness plugs can no longer simply swap between these two board interfaces. Ordinary polarity/wiring errors remain to be addressed by marking, assembly inspection and protection.
2. **Unused output net-name mismatch.** U1pad5 initially used OUTB NC in the PCB-generated NC net and OUTB_NC in the schematic-exported net. The generator now uses OUTB_NC consistently; the fresh parity result is0.

For the replacement J2, the [manufacturer’s1715721 page](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-15-2-508-1715721) specifies5.08mm pitch,0.9mm square pins and1.3mm PCB holes, matching the pinned footprint. Installed height is13.8mm. It also specifies0.5–0.6Nm torque,7mm strip length, and physical support while tightening. These are assembly requirements, not evidence of enclosure fit or vibration endurance. The fetched footprint source is [official KiCad at commit7ebfa6b](https://raw.githubusercontent.com/KiCad/kicad-footprints/7ebfa6b23cc292a56f751b7b5f4a0e12eeef69dd/TerminalBlock_Phoenix.pretty/TerminalBlock_Phoenix_MKDS-1%2C5-2-5.08_1x02_P5.08mm_Horizontal.kicad_mod).

## Remaining physical integration and release blockers

1. **GPIO bias must remain at the carrier when unplugged.** R2 is electrically on the GPIO side of R1 but physically on the accessory (`build_idle_accessory.py:28`). Removing J1 also removes this strap bias from the module. The eventual take-off must provide a permanent2.2k pulldown at U3pad13/carrier, with the accessory resistor retained, changed or omitted explicitly as part of the combined load calculation. Do not describe the current accessory-only R2 as a permanent carrier strap.
2. **Actual GPIO3 eFuse routing remains unknown.** With default STRAP_JTAG_SEL=0 GPIO3 does not select JTAG; with strap selection enabled and both paths allowed, low selects GPIO39–42 pad JTAG, conflicting with existing WDI/SAFE_N/I2C uses. Read and retain actual eFuse state without writing it, apply the complete truth table, and reject incompatible modules. Observe the required3ms strap hold after EN rise. GPIO45 would expose flash-voltage selection risk and is not a better substitution. These constraints come from [Espressif ESP32-S3 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf), §3 and Tables3-2/3-4/3-5.
3. **Return wiring has an alternate current path.** J1pin4 logic return and J2pin2 power return are the same net, also containing Q1source. An open J2return can divert valve current through J1/XH and the carrier’s logic/supply return. Define the complete star/return geometry, harness gauge, connector limits and the open-return fault response before a powered harness is accepted. Merely naming J2 “POWER RETURN” does not prevent the alternate path. A physical fault test needs a reviewed current-limited fixture.
4. **External protection and load remain a contract.** J2 must be9–16V from a separately fused, switched actuator branch with specified reverse and transient protection, not the carrier1A logic input or sensor5V. No fuse, reverse diode, TVS, actuator bulk capacitor, supply relay or upstream harness is supplied by this PCB draft. Define that upstream assembly and fuse coordination, local supply loop impedance/decoupling, and interruption behavior.2A is a maximum actual coil-current acceptance bound across cold/hot, voltage and duty, not an onboard current limit or an assumed valve rating.
5. **Layout and parts are unfinished.** Keep all28 connections unrouted until current-loop paths, source/logic reference, inductive return, trace/via capacity, bypass placement and clearance are reviewed. Exact resistors/capacitors, connector contacts/housings, wire termination, standoffs and tab insulation are not all procurement-ready. All electrical footprints are THT and U1 is direct-soldered PDIP8 with no socket, consistent with the assembly preference. [TI’s exact UCC27524P record](https://www.ti.com/product/UCC27524/part-details/UCC27524P) confirms PDIP8 and equivalence toP.B, but directTI stock was unavailable when checked. Its current main electrical tables do not explicitly label theP package; freeze the guaranteedP/P.B temperature, threshold and UVLO data with the actual procured source rather than silently substituting another package.
6. **The accessory is additional space.** The80x50mm outline does not enlarge the archived120mm carrier, but neither the accessory’s mounting volume, screw/wire access, terminal height, live TO220tab clearance nor antenna/RF relationship has been fitted into the enclosure. No printed fit or sealed enclosure claim follows from these CAD checks.

`firmware/include/ecu/idle_hardware.hpp:4-11` defaults ECU_IDLE_DUMMY_LOADS to0, requires the separate engine dummy-load opt-in, and rejects that opt-in for the selectedN16R8 board. The selected-board physical inhibit is appropriate while these points remain unverified. The target currently uses a GPIO sink in the common GPTimer owner, so this draft does not claim LEDC ownership or a demonstrated peripheral output. This pass did not qualify target jitter or engine/idle scheduling under load.

Before physical acceptance, use the routed-board review and then a current-limited resistor load fixture. Scope GPIO3, RUN/ENA, driver output, switch input/drain, rails and load current through power-up/down, ENreset, boot/download, missing5V, disconnected signals/returns, interlock/supervisor/watchdog and stalled producer. Only then evaluate an identified continuous-duty two-wire normally-closed energize-to-open12V valve with measured R/L, polarity, allowed PWM range, current, closure decay, heat and fault behavior. Host and native CAD tests do not replace those measurements.
