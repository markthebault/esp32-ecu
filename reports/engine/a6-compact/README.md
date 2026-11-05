# A6 compact development evidence

This packet accompanies the [routed native development draft](../../../hardware/a6-flex-rgb/README.md). The PCB is not released for fabrication, sensor connection or engine operation. All physical engine outputs remain inhibited. [Scope and remaining gates](../../../docs/engine-a6-layout.md) distinguish native geometry and nominal circuit checks from physical qualification.

- [Validation](validation.json): 264 footprints, 260 schematic components, 779 named pad bindings, zero ERC/DRC/open/parity findings.
- [Native DRC](native-drc.json), [ERC](native-erc.json) and [fresh XML netlist](native-netlist.xml).
- [Width audit](copper-width-audit.json) and [three executed negative controls](width-rule-update.json). The exact three inherited INJ1 necks are conditional geometry exceptions, with current/thermal acceptance still open.
- [Local routing receipt](local-analog-routing.json), [BOM counts](bom-summary.json) and [new-waveform resistor arithmetic](resistor-power.json).
- [Nominal circuit archive](nominal-circuit.tar.xz): all 62 source decks, raw gzip waveforms, logs, Capture results and source snapshots. It includes intentional rejection cases and does not imply every condition yields valid sensor data.
- [Legacy deck equivalence](legacy-deck-equivalence.json) and [compact metadata equivalence](compact-metadata-model-equivalence.json). The latter rename clarifies nine resistor body envelopes as maximum dimensions; all 62 compact decks remain byte-identical.
- [Guide runtime check](guide-runtime.json), [20 API tests](web-api-tests.log), [firmware build result](firmware-builds.json) and [firmware archive](firmware-builds.tar.xz). The archive retains all three exact ELFs losslessly, generated assets, build logs, SDK configuration copies and 304 source inputs. Default-cache preservation copies remain in the local build workspace; their before/after manifests are included.
- [Publication metadata delta](publication-delta.json): the native board, project, rules, schematic and library bytes are unchanged from the reviewed candidate. Only three contract fields record the completed native checks and the development HOLD state.

[Independent review](review.json) accepts development-draft publication with explicit holds and no concrete publication blocker. Its [readable verdict](review.txt), [inspection](independent-native-inspection.json), [numerical checks](independent-model-inspection.json) and [negative controls](independent-native-negative-controls.json) accompany the source-bound result. The complete [review source freeze](independent-review-sources.tar.xz) and [review probes and rerun](independent-review-probes.tar.xz) retain the evidence. Global per-user instructions remain in the local freeze; their exclusion from distribution is recorded in [publication omissions](publication-omissions.json).

The reviewer confirmed no remaining same-layer input/comparator-output parallel witness. It identified 2.25 mm projected parallel overlap between FLEX_IN on In2 and ADC7 on adjacent In3, with no ground plane between those signal layers. This geometry does not establish excessive coupling or a functional defect; a physical parasitic bound still requires a specified stack and extraction or measurement. Supply stability, current/thermal limits, assembly and fit remain explicit holds. There is no fabrication, sensor-hookup or engine-operation approval.

From the repository root, check the distributed source/artifact hashes with `sha256sum -c reports/engine/a6-compact/SHA256SUMS`. This verifies packet integrity, not physical ECU behavior. The [formatting note](formatting-note.json) records incidental whitespace retained in the exact reviewed native/library and generated document copies.

From the repository root, reproduce native checks with KiCad 9 and fresh output paths:

```sh
kicad-cli sch erc --severity-all --exit-code-violations --format json \
  --output .cache/NEW_A6_ERC.json hardware/a6-flex-rgb/esp32-ecu.kicad_sch
kicad-cli pcb drc --severity-all --schematic-parity --exit-code-violations \
  --format json --output .cache/NEW_A6_DRC.json hardware/a6-flex-rgb/esp32-ecu.kicad_pcb
/usr/bin/python3 scripts/audit_a6_copper.py \
  --board hardware/a6-flex-rgb/esp32-ecu.kicad_pcb --output .cache/NEW_A6_WIDTH.json
```

Run the conditional nominal circuit/Capture experiments with Python/numpy, ngspice 45.2 and the C++ compiler/sanitizers:

```sh
python3 -B tools/test_flex_frontend.py
python3 -B tools/run_flex_circuit.py \
  --frontend hardware/flex-input/frontend-compact.json \
  --ngspice PATH_TO_NGSPICE45_2 --output .cache/NEW_A6_CIRCUIT
```

The default circuit command still selects the preserved original profile. Select the compact profile explicitly. Its capacitors are nominal ideal parts; effective X7R values, ESR/ESL, supply transients and physical PCB capacitances remain unqualified. The sensor supply and external plug mapping remain unresolved. Do not infer physical sensor/target behavior from these commands.

Build the matching inhibited firmware in a fresh directory with default-cache preservation:

```sh
python3 -B scripts/build_firmware_preserved.py \
  --output .cache/engine/NEW_A6_BUILD --environment compact_n16r8_flex_dev
```

Historical GPIO38 WS2812 builds are incompatible with A6's protected input allocation. These commands never flash a device. Full Speeduino parity, online TunerStudio integration and physical/HIL qualification remain open.
