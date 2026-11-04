# A5 idle-interface carrier draft

This separate **120 × 120 mm, six-layer native KiCad9 copy** adds a permanent GPIO3 bias and keyed idle logic connector to the A4 N16R8 development carrier. It preserves A3/A4 sources, manufacturing files and the historical ZIP. **Fabrication, powered actuator integration and module fit remain on hold.** The firmware remains inhibited.

The [native project](esp32-ecu.kicad_pro), [net contract](net_contract.json), [full reference BOM](bom.csv) and [source provenance](source-provenance.json) define this revision. The two additional fitted references are:

| Reference | Function |
| --- | --- |
| R154, upright 2.2 kΩ 1% | Permanent IDLE_CMD/GPIO3-to-GND bias, retained when the accessory harness is unplugged |
| J21, JST B4B-PH-K-S(LF)(SN) | 2 mm PH4: 1 IDLE_CMD/GPIO3, 2 RUN_5V, 3 +5V, 4 GND |

The 4-wire harness connects J21 to the separate [IAC-DRAFT2](../idle-isolated/README.md) XH4 J1, pin1→pin1 through pin4→pin4. Use the [harness addendum](../idle-isolated/harness-bom.csv). J21 supplies the optocoupler LED/buffer domain only. Do not connect its ground or 5 V to the accessory actuator logic/coil domain. R151 remains the inherited 1 MΩ chassis bleed; it is not the new idle resistor.

Combined U9 RUN drive still needs acceptance with R47/R50/R53, Q7, ten HCT inputs and the accessory attached. The ST 500 µA Q7 input bound is at 10 V/25°C, with a different fault-sink case; the revised 2.2 kΩ accessory buffer budget is conditional. Measure loaded RUN/MAIN_IN over startup, temperature and faults. R154 adds nominal 1.5 mA GPIO source load at 3.3 V, which must also be included in the loaded GPIO/opto test.

All 2,973 inherited track/via objects retain their exact integer geometry and named nets. Only 25 new track/via objects are appended. All 219 original footprint pad geometries remain, with the intended U3 socket pad13 NC→IDLE_CMD net change. Zones are refilled by KiCad9; their boundary/net/layer definitions remain subject to the independent comparison. New copper avoids the full provisional inward antenna rectangle. The evidence records native ERC/DRC/connectivity/parity and the independent geometry audit. Those checks establish neither physical signal quality nor RF/thermal/fit acceptance.

The selected 44-pin Type-C N16R8 still lacks measured socket row spacing, board dimensions and stack height. The existing 22.86 mm row spacing and 10 mm inward antenna extension remain provisional. Elevation does not eliminate RF detuning by carrier copper or case lining. The actual GPIO3/JTAG eFuse routing must be read without changes before output qualification. The onboard RGB pin conflict remains; use only the documented separate GPIO38 LED. [A4's module-fit limitations](../a4-n16r8/README.md) continue to apply.

The inherited A3 enclosure has no qualified J21 cable access or accessory-board mounting. The accessory uses back-mounted parts and different live TO220 tabs, requiring a physical assembly/insulation/clearance trial. No new Gerber, case or packaged-firmware release is claimed. See [the hardware/debug guide](../../docs/engine-idle-isolation.md) for evidence and reproduction.
