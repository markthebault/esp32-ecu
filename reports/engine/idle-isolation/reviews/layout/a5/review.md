# Independent A5 idle-interface delta review

Reviewed 2026-11-04 at base `497aabb4a0ea686b240182e42b4c64aefa280c32`. Scope: source preservation, two new THT parts, their copper and the PH4-to-XH4 idle harness contract. **The routed A5 delta passes this bounded audit. Combined source-loading, actual module/eFuse/RF/fit, powered tests and manufacturing release remain on hold.** This is not a new qualification of the inherited ECU circuitry. No production file, hardware or eFuse was changed.

The immutable128-file bundle `05bec06cd0e1f013429455eb64d617a0aee832cd44da4d9ceb63e16688d4d3d7` includes the captured A4/A5 projects and source generators. A5 PCB SHA256 is `12a0d3a36dda51e8d2e99e046480309d23a0c40471b02e0ab47458bea71bf33a`. Absolute-path native KiCad9.0.8 runs on a byte-identical writable cache project give **0 ERC, 0 DRC, 0 unconnected and 0 schematic-parity issues**, all severities/all track errors, no exclusions. Input snapshot/working bytes remained unchanged after execution. Commands/results and independent probes are bound in `review-manifest.json`.

## Concrete source-loading gap found

The earlier isolated-input architecture calculation counted R47 but omitted another existing RUN load: **R50=1k feeds Q7 MAIN_IN, with R53=10k to ground**. RUN also drives ten HCT inputs: eight U16/U17 inputs and U9 pins10/13. Their addition is unchanged A4 topology, but it matters when adding the idle buffer.

The [SN74HCT08 data](https://www.ti.com/lit/ds/symlink/sn74hct08.pdf) tests VOH at4mA and gives1uA maximum input leakage per input at the tabulated endpoints. [ST VNP35N07-E](https://www.st.com/resource/en/datasheet/vnp35n07-e.pdf), Table4, bounds Q7 input supply current to500uA at **VIN10V, VDS0V and Tcase25C**. It does not establish a500uA maximum at this lower input voltage or over the full intended temperature range. Table9's20mA input fault-sink figure at5V is also incompatible with treating500uA as a fault bound.

With an explicitly conditional500uA normal-current proxy,5.25V RUN, existing5% R47/R50/R53, a1% idle base resistor and ten1uA HCT inputs, the source budget including a base-emitter short is:

| Accessory RUN resistor | Conditional total | Margin against4mA |
| --- | ---: | ---: |
| R2=1.8k1% | 4.46570mA | -0.46570mA |
| R2=2.2k1% | 3.93004mA | 0.06996mA |

The branch calculation is `I_R50 = V_RUN/(R50+R53) + I_Q7*R53/(R50+R53)`. Simply adding500uA to an independent11k branch is not exact. The2.2k change improves the budget by0.53566mA; it does **not** prove the assumed5V/full-temperature Q7 current or arbitrary fault behavior. That separate accessory value correction has been applied; its final geometry/hash is bound by the accessory review. No assumed forced-beta value is promoted to a full-temperature NPN saturation/storage guarantee.

The prior blanket<=4mA claim should be withdrawn. Freeze the passive tolerances and measure loaded RUN, MAIN_IN, the idle LED/buffer, main-switch startup and fault response with both boards connected. Preserve the physical-output inhibit while unresolved. `run-loading-probe.json` retains the arithmetic and assumptions.

## Source preservation and actual copper

`review_probe.py` uses its own raw-S-expression parser on the original KiCad10 files, independently of the author's compatibility converter and routing geometry function. It confirms:

- All **219 original footprints /661 pads** retain placement, local pad geometry, layers and net names, except the intended **U3 pad13:NC→IDLE_CMD**. Their Fab/silk/courtyard line/arc/shape geometry also remains unchanged.
- All **2973 original track/via objects** retain exact geometry, layer and net name by UUID; all are locked. Exactly25 new objects were appended:12 IDLE_CMD,4 RUN_5V and9+5V objects. The new GND pads connect through the refilled existing ground zones, with native connectivity clean.
- All original global and footprint zone boundaries, nets, clearances, thermal parameters and keepout rules remain. KiCad9 serializes away explicit default island-mode0; native comparison confirms mode0 is retained. Filled copper polygons were deliberately recomputed and are not asserted byte/geometrically identical. Loading the compatibility baseline warned that legacy fill is converted on a best-effort basis; this reinforces the fabrication/RF hold.
- All62 recorded A4 source hashes match the captured/current archive. Against HEAD,59 match byte-for-byte; three CSV files differ only by normal checkout CRLF versus Git LF. No A4 electrical or physical source change was found. The original PCB hash remains `462f8438cde1533ccd08fe9396cc6bb2a89a2166380fe8b0adcd2e30d4015f0c`.
- Original R151 remains the1M CHASSIS-to-GND bleed. It was not reused for GPIO bias. The new resistor is uniquely **R154**,2k2 at `(13,27)`. New **J21** is at `(26.5,16)`. Both have only through-hole pads. The final board has221 references and retains its120x120mm outline and six copper layers.

Only the documented board-text annotations change; original non-text board geometry is retained. The raw audit and native checks agree that the router's rounded protected copper was discarded rather than accepted as a replacement.

## Bias, harness and provisional antenna boundary

The native schematic and PCB independently agree:

| Carrier connection | Accessory J1 connection |
| --- | --- |
| U3 pad13 /J21 pin1, IDLE_CMD(GPIO3) | pin1 command |
| J21 pin2, RUN_5V from U9 pin6 | pin2 RUN |
| J21 pin3,+5V | pin3 carrier-side LED/buffer power |
| J21 pin4,GND | pin4 carrier-side return |

R154 connects IDLE_CMD to carrier GND directly. Removing J21/the whole accessory harness leaves the U3-to-R154 bias intact; it does not depend on a connector contact or accessory ground. At3.3V, the new2k2 pulldown adds nominal1.5mA GPIO source load before the accessory base path. Therefore the loaded GPIO/LED test must include this permanent bias, rather than validating the accessory alone. The [ESP32-S3 primary data](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf) do not turn its high-impedance VOH entry into an arbitrary loaded-output guarantee.

Carrier J21 is JST **PH4,2mm**, while accessory J1 is **XH4,2.5mm**. The harness is a keyed PH4-to-XH4 cable wired1→1 through4→4; the headers do not mate directly. Inspect actual mating-face orientation/continuity and retain strain relief/case-access acceptance. The [JST PH catalog](https://www.jst-mfg.com/product/pdf/eng/ePH.pdf) lists B4B-PH-K-S and its through-hole layout. The new official KiCad footprint was independently downloaded from pinned commit `7ebfa6b23cc292a56f751b7b5f4a0e12eeef69dd`; SHA256 matches `149a484d86b4c190df4b961d6c6edac68b655349b248c0ca03135294c291e8f1`.

Every new track/via bounding box and both new part courtyards lie outside the reserved provisional antenna rectangle **x14..44/y29..40mm**. This establishes the new delta's exclusion only. It does not qualify inherited copper, an actual inward antenna/module geometry, socket spacing/height, cable proximity or RF performance. The selected44-pin N16R8 supplier pin order and GPIO3/eFuse/JTAG state remain to be checked on the actual module. No eFuse write is required or authorized by this review. Firmware idle physical writes remain inhibited.

`source-manifest.json` records primary URLs and available byte hashes; inaccessible web-only PDFs have no claimed hash. Primary source PDFs/extracts are local research inputs, not redistribution artifacts. Reproduce with `/usr/bin/python3 .cache/engine/idle-isolated-layout-review/a5/review_probe.py`; the probe checks current A4 bytes against its frozen evidence as well as HEAD. This report approves no fabrication, powered actuator, engine, RF or vehicle release.
