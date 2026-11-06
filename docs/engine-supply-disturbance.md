# Conditional supply and acquisition study

This study feeds authored circuit waveforms through the actual portable sensor binding, flex capture and engine controller. Physical engine outputs remain inhibited. It does not execute the ESP32, hardware supervisors, output scheduler or engine plant, and it does not qualify a board, sensor, harness, printed fit or vehicle.

The implementation is in `tools/run_flex_nonideal.py` and `tools/flex_circuit_control.cpp`. This is development work; a completed numerical run is separate from independent review, physical qualification and the wider Speeduino feature goal.

## Numerical setup

The original coincident ADC/flex switching witness failed with tiny time steps. KLU could reach the end while leaving repeated timestamps. Those outputs and diagnostic ablations are retained, and the accepted-input contract still rejects repeated/reversed times, nonfinite values, solver aborts and incomplete simulation duration.

The upstream [coincident-corner report887](https://sourceforge.net/p/ngspice/bugs/887/) and [analysis-option report888](https://sourceforge.net/p/ngspice/bugs/888/) describe a matching problem and workaround. This runner uses a netlist `.tran` card, starts it with `run`, and sets `minbreak=1e-15`. The control interpreter's `tran` command can ignore this option. Changing tolerances alone did not resolve our witness. The circuit component equations are unchanged by this remedy; a preserved pre-remedy deck is a regression fixture.

The actual ngspice ELF is hashed and retained in the owned run directory. An attested wrapper is resolved to its executable instead of treating the shell-script hash as the solver identity. Each run uses an owned minimal startup, one numerical thread and no user startup/external code models. The original toolchain and previous runs are retained.

## Model and data contract

The selected A6 compact frontend and native contract bind the declared component values and pins. Added supply impedances, capacitor ESR/ESL, loads, diode/GPIO equivalents and coupling capacitances are authored sensitivity parameters. They are not measured parasitics or manufacturer limits. The two regulator sources are independent equivalents; a positive-current mirror is not a Pololu/LD1117 control, dropout or thermal model. Constant F2 resistance is not a PTC heating/trip simulation.

The20/40/60mA sensor-load fixtures specify external current sinks. The modeled divider and NTC currents add to these values; they are not total board-current measurements or released load ratings.

The MAP/TPS sensor fixtures have fixed known physical values and ideal outputs proportional to SENSOR_5V. Their actual22kΩ/33kΩ/10nF board paths are modeled. Fixed-resistance NTC fixtures assume optional R32/R33 are fitted; their loaded board paths are included. Channels4..6 use ideal buffered/controller/battery voltages. These fixtures do not establish the behavior of a purchased sensor.

Only ADC7 has the explicit typical pin/hold/switch equivalent. Other channels omit ADC switching charge. The declared scan has48µs per24-bit transfer,3µs acquisition and a fixed control phase. Actual driver overhead, interrupt latency, sample skew and clock behavior are unmeasured.

Raw codes use an ideal held-signal/instant-reference conversion at acquisition end. This is **not a physical MCP3208 SAR model**. Each channel also records reference excursions over acquisition and an authored24µs conversion observation window. Their full-scale-LSB span is an indicator, not an ADC error bound. Reference changes during real successive approximation can produce behavior the point conversion does not predict; overlapping a burst with acquisition does not close that limitation.

`adc_ok=1` means assumed SPI API success. It is not inferred from reference voltage. An out-of-domain reference at the conversion point stops replay as an unsupported model condition, rather than inventing a transport failure. The separately recorded window-domain flag does not establish SAR behavior. Separate native fault probes exercise bad acquisition flags and numeric rail rejection.

Four assumed GPIO threshold pairs and ten integer-clock phases feed the real flex capture. Three engine strategies and both absolute/ratiometric calibration variants run through the same controller. RPM and phase synchronization are fixtures; no crank decoder, scheduler or physical output is executed. A pending capture fault is acknowledged only after a completed invalid control evaluation cuts both fuel and spark proposals.

## Coverage and completion

The short original ripple bursts fall between scans and remain negative exposure controls. Additional MAP-aligned, rail-aligned and scan-spanning bursts exercise acquisition. The3V3 carrier uses a frequency noncoherent with the declared scan. Sampling records disclose actual overlap per channel; changing scan phase can remove overlap even from a nominally aligned case. Source overlap alone does not prove a disturbance was delivered at the ADC; compare the recorded pin/reference values with the matching baseline.

Every output has a planned case inventory and explicit running/failed/complete status. Partial results after a timeout are not whole-matrix acceptance. Completed cases of a failed matrix can be inspected with an explicit exploratory option; the analysis stays marked incomplete. A resource timeout is distinct from a numerical abort and does not change simulation time or tolerances.

```sh
python3 -B tools/test_flex_nonideal.py
python3 -B tools/run_flex_nonideal.py --ngspice PATH_TO_NGSPICE45_2 --output .cache/NEW_SUPPLY_COARSE --ngspice-timeout-s 600
python3 -B tools/run_flex_nonideal.py --ngspice PATH_TO_NGSPICE45_2 --output .cache/NEW_SUPPLY_FINE --max-step-us .25 --ngspice-timeout-s 600
python3 -B tools/analyze_flex_nonideal.py --matrix .cache/NEW_SUPPLY_COARSE .cache/NEW_SUPPLY_FINE --output .cache/NEW_SUPPLY_COMPARISON
```

Analysis requires the exact unique24-replay inventory and canonical case/threshold/strategy/calibration file identity for every case. It independently reconstructs scan timing, piecewise-linear point voltages, codes, reference-window ranges, source overlap and stateful GPIO crossings from the strict raw traces, without importing the producer for those calculations. The reconstructed stimulus must match every native input line. It verifies all query/clock phases and compares every229-column native MSL007 value, unit and unknown marker with its phase-zero JSON observation, plus the source/period/retention header. Integer counters are exact; float comparisons account for the native nine-significant-digit log format. Frozen sources, the actual solver/startup and all inspected inputs are hashed. These are implementation/data-chain checks, not a second physical ADC model.

A separate isolated interpreter regenerates every circuit deck from the already hash-verified frozen producer and declared scenario, then compares its exact bytes. This deck check executes trusted project source; use the auditor only on owned experiment directories. It does not rerun the solver or independently validate the physical equations. The raw-to-sampling and GPIO reconstruction remains independent of the producer.

The first producer retained the inherited A5 contract's pre-run hash in `binding.carrier_sha256`, but omitted its bytes from the frozen source tree. The auditor recovers only a contract matching that original hash into a temporary authoring directory and discloses this recovery separately. The original run directories are unchanged. `--binding-source` supplies that exact contract outside this checkout. New producer runs retain it directly; this source-retention follow-up changes no circuit equations or control behavior.

The earlier independent review demonstrated three audit gaps: an empty replay inventory could pass, impossible sampling metadata was trusted, and changed MSL values passed dimensions-only checks. Recheck also exposed swapped threshold/file identities and false retention headers. The strengthened analyzer rejects those cases. Regression snapshots include actual native fault/ready records and masked rail values; mutating each of229 log columns must reject.

Comparison covers all sampled codes, clock-quantized GPIO inputs and native observations across numerical settings. Differences are reported explicitly; identical declared discrete inputs must produce identical native records. Neither identical records nor a successful circuit integration establishes physical ADC accuracy or engine operation.

## Completed conditional checkpoint

Both26-scenario grids pass the strengthened audit over42,903,134 raw rows and1248 controller replays. Sampled ADC codes, query timing and clock-quantized GPIO inputs are identical across1µs and0.25µs maximum steps. Native observations also agree after excluding only the separately recorded analog-reference debug value. An independent ASan/UBSan rebuild reproduces every native JSON transcript and MSL log byte for byte;23 authored tests and26 independent acceptance/rejection controls pass.

The [compact evidence packet](../reports/engine/supply-disturbance/README.md) retains exact sources, full audit reports and a strict review whitelist. Full raw waveforms, all native transcripts/logs and executables remain local and are not distributed in the packet; another machine must rerun the complete matrices for the raw audit.

Aligned5V bursts overlap acquisition but do not change this fixture's MAP/ADC7 point codes. Aligned3V3 bursts produce delivered reference/code changes. Ratiometric conversion reduces modeled supply-related MAP error, while numeric rail rejection still cuts every observation in the60mA/4.5Ω and40mA/7.5Ω external-load witnesses. Neither result establishes physical sensor accuracy, allowable sensor current or regulator/PTC behavior.

Physical power/reference quality, actual return paths/coupling, component tolerances and effective capacitance, threshold/delay corners, flash/RF/ISR load, supervisor/reset behavior, driver loads/heat, assembly and enclosure tests remain open. The circuit study also does not resolve online TunerStudio support or the remaining engine feature gaps.
