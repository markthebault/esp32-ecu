# Protected boost hardware development

The new [A7 carrier](../hardware/a7-boost-interface/README.md) and [BOOST-DRAFT1 accessory](../hardware/boost-isolated/README.md) extend the [boost software and turbo comparison](engine-boost-development.md). They are routed THT development sources, with physical engine outputs inhibited. A3–A6 and IAC-DRAFT2 remain unchanged. There is no fabrication, powered-valve or case-fit release.

## Circuit and harness

A7 replaces the old PH4 idle header with J21 ZH5. Its first four signals retain IDLE_CMD/RUN_5V/+5V/GND order; pin5 adds GPIO45 BOOST_CMD. R1802k2 supplies permanent GPIO45 bias. A dedicated Y loom joins the original idle XH4 input and the new boost ZH4 input. The [harness BOM](../hardware/boost-control/harness-bom.csv) counts nine ZH and four XH contacts, one conductor per crimp, plus three insulated fanout joints. Actuator current uses its own J2 supply/return.

The boost input uses two TN0702N3-G devices with source/gate/drain pin order1/2/3. The [Microchip datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/TN0702-N-Channel-Enhancement-Mode-Vertical-DMOS-FET-Data-Sheet-20005941A.pdf) provides25°C pulsed resistance points; it does not supply a complete low-bias/full-temperature switching model. The fitted ngspice profile is checked against those points, while separate hot/capacitance profiles remain authored sensitivity hypotheses. The [JST ZH drawing](https://www.jst-mfg.com/product/pdf/eng/eZH.pdf) supplies the nominal header geometry. Footprint source URLs, exact hashes and licenses are under [boost-control/footprints](../hardware/boost-control/footprints/).

Two6N137 LED channels, driven through input filters, feed an HCT NOR. Command and hardware RUN must both be represented at the detector. Local supervision gates a separate UCC27524P.B driver. The LM317 supply, source-star/Kelvin return, gate bias and flyback stage derive from IAC-DRAFT2. The ordinary-iron PCB preference is preserved. Exact leaded passive parts, connector crimps and physical mounting still require acceptance.

Combined RUN loading includes the existing carrier logic/Q7 and both original idle input buffers. Neither the old Q7 assumption nor an ideal source resistor guarantees a real HCT output level. Actual loaded RUN/MAIN_IN, startup, temperature, fault loading, GPIO45 boot behavior and the procured PDIP driver limits remain open. The [TI part page](https://www.ti.com/product/UCC27524/part-details/UCC27524P) identifies P.B as equivalent to P; the model's2.4/1.0V hysteresis is still a declared surrogate, not an inferred package-wide guarantee.

## Electrical experiments

The authored ngspice model includes both original idle input buffers on the shared trunk, the new filtered MOS inputs, optical forward-current sensing, detector logic/supervision, local driver/power stage, and a declared36Ω/30mH coil on a fixed12V supply. Warm cases start with detector power ready, but zero coil current and unenergized input/filter states. Cold startup integrates from zero. The source-star, sources, optocouplers, regulator and power transistors remain conditional lumped models; there is no extracted PCB/harness impedance, measured device timing or calibrated valve.

Phase1 input experiments test nominal, adverse and tolerance hypotheses, including low optical-current sensitivity and refined explicit pulses. Their acceptance covers those declared experiments only. The input filter suppresses modeled hotplug pulses, but1µs commands are lost;40µs also fails in the full-stage nominal case. At100µs and above, tested pulses transfer with width distortion. These observations do not assign a physical minimum pulse or establish PWM accuracy over temperature.

The full-stage matrix exercises cold/warm startup, command/RUN low and wire opens, common trunk power/return opens, boost-stub opens, actuator branch opens, rail dropout, late supervision, hotplug/capacitance sensitivity, lower RUN drive and short pulses. Unsafe controls retain a drain-source short and a deliberate return bridge. A drain short continues ordinary coil current despite a low gate; it cannot be solved by configuration or a fuse alone.

Stored logical boost-channel9 transitions from both controller/plant runs can be replayed into the electrical circuit. Channel9 is a native trace identifier; the inhibited carrier candidate is GPIO45. Every source clock/sequence is validated, and original control-cut causes are retained. Fixture terminal interventions are rejected. The charged-coil and actual-gas overboost windows are distinct from nominal replay. The circuit starts with zero coil current on its own fixed supply, without feedback to the engine plant. This is an electrical edge replay, not a new coupled engine validation.

Reproduce into a new directory with the captured ngspice binary and the retained research runs:

```sh
uv run --with numpy python3 -B tools/test_boost_circuit.py
uv run --with numpy python3 -B tools/run_boost_circuit.py \
  --accessory hardware/boost-isolated --carrier hardware/a7-boost-interface \
  --ngspice .cache/engine/flex-frontend-review/toolchain/ngspice \
  --output .cache/engine/boost-circuit-new \
  --engine-run .cache/engine/boost-coupled-study-004/open-40-ours/run \
  --engine-start-s 5.5 \
  --engine-run .cache/engine/boost-coupled-study-004/charged-map-rail-ours/run \
  --engine-start-s 5.9
```

Omit edge-run arguments for the24 standalone cases. Pair each custom start argument with one run. Unknown case names, invalid windows, reordered histories and fixture shutdowns fail explicitly. Decks, full traces, source snapshots, binary/Python identities and validation results are retained. Current checkpoint evidence is under [boost hardware](../reports/engine/boost-hardware/README.md).

## Assembly and debug acceptance

Before power, check each numbered harness conductor against the PCB pin numbers, not apparent left/right order. Inspect all three fanout joints, pull-test the actual crimps, confirm positive electrolytic and flyback polarity, and measure the permanent GPIO45 bias with the accessory unplugged. Check that actuator return cannot reach carrier GND through hardware, mounting or test equipment. NT1 is the single source return star; no extra ground strap is fitted.

The first powered experiment needs a current-limited resistive fixture and independently operable actuator disconnect. Physical engine writes remain disabled. Reference carrier measurements to J1 pin4 and detector measurements to LOGIC_GND. Use correctly isolated/differential measurement without defeating protective earth or the optical barrier. Record loaded GPIO/RUN, optical resistor drops, U6 output, supervisor LOCAL_OK, U1 VDD/GND/ENA, Q1 gate/source/drain and both separate return currents.

Capture startup, reset/download, watchdog/interlock, lost command, every supply/return open and recovery, stored-current decay, full PWM range and the actual shortest delivered pulse. A nominal simulation cannot bound the supervisor's unspecified maximum assertion delay. No current/thermal shutdown or valve feedback is added here. Actual valve R/L and plumbing, separately protected switched power, current/temperature/transients, exact PDIP guarantees, minimum pulse/width fidelity, RF, formed leads, back clearance, sealing and printable enclosure fit remain open. This increment does not complete [the feature goal](engine-feature-coverage.md).
