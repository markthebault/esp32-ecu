# Independent conditional idle circuit review

Reviewed 2026-11-04 by `/root/idle_isolation_review`, separately from the earlier architecture assessment. Production files were read-only. Reviewer decks, probes, immutable snapshots and results are confined to this cache directory. No hardware writes, OS changes, services, subagents or external messages were used.

**No remaining concrete high/medium implementation finding was identified within the declared conditional model scope after the evidence and documentation corrections below.** This is not acceptance of the physical circuit, routed PCB, real device limits, valve, engine or vehicle. Combined RUN loading remains an actual release hold, not a solved consequence of buffered LEDs.

The final reviewed input is `.cache/engine/idle-isolation/circuit-precision/results.json`: 25 cases, source guards unchanged, ngspice45.2 binary hash verified. Its runner hash is `aece1686d6f33c343f31d06f7d9ac566f8dcdf973b3d85ffbd6db7d041ecf711`. The accessory PCB hash is `dd12136d7c7dec1464d7119dcd1fefe8740fa3743c33520e7c524a3910bb3d2e`; A5 PCB hash is `12a0d3a36dda51e8d2e99e046480309d23a0c40471b02e0ab47458bea71bf33a`. Exact source/doc hashes are in `final-audit.json` and `review-manifest.json`.

## Corrections and scope findings

1. **Low, corrected: default decimal export precision merged distinct internal timestamps.** The initial exports had no reversals/nonfinite data but repeated printed times, including 104 in cold_start and 106 in a short-pulse trace. The repeated intervals were much smaller than the declared experiment steps and did not change the conditional conclusions. Root added `set numdgt=17`, per-case time-order diagnostics and reversal rejection. The final independent audit finds zero repeated timestamps and strict increasing time in all 25 complete exported windows. All final decks differ from the preceding run only by that export command; the electrical network/integration/window commands are unchanged.

2. **Low, clarified: cold source sequence and peak current are conditional.** Cold_start ramps actuator input from0 to12V over10ms, while an ideal carrier5V source is applied at time0 to an initially uncharged ideal100nF through ideal10mΩ wires. It is not every physical supply ramping together. Halving the timestep in an independent rerun changes the sampled carrier inrush peak from2.499A to4.925A, while final coil/current state is unchanged. Results now explicitly mark the peak as not a physical bound and describe the source sequence. Late carrier-return current is separate.

3. **Documentation release hold, clarified rather than electrically closed:** code/results already identify R47/R50/R53, the conditional500µA Q7 proxy and10µA HCT proxy. The main guide and both hardware READMEs now explicitly state that combined U9 RUN loading, Q7's different normal/fault conditions and loaded GPIO/R154 behavior remain unqualified. The ST500µA point is not a guaranteed5V/full-temperature load; the different fault sink is not modeled. My additional500Ω MAIN_IN sensitivity load raises modeled RUN source current from3.175mA to5.562mA. That load is a declared conductance experiment, not a VNP fault macromodel. The ideal Thevenin RUN source continuing to drive does not establish U9's4mA logic-high guarantee under that condition.

4. **Evidence requirement addressed independently:** source hashes alone do not bind a changed deck/log/trace. `reviewed-data-sha256.json` now binds all80 final input files, including every generated deck/log/gzip vector file, results and plots. Root's publication manifest must preserve those bytes or record a new reviewed input. Raw pulse vectors retain their declared1.9-2.2ms window; they are not represented as full0-8ms waveforms. Cold retains0-0.8s and other warm cases0-8ms. Source guards and complete declared-window checks pass.

Time-weighted trapezoid summary means were already corrected by root before the final review. I independently recomputed final coil, rail and gate means, pulse widths and maxima from every final vector file. They match the recorded values. The final pulse average covers the last50µs; other final averages cover the last500µs, using the actual exported time range.

## Electrical coherence and independent controls

The deck is an explicit lumped network, not an RPM/duty oracle. It contains generic BJT/LED and MOS device equations, finite resistors/capacitances, a coil/flyback path and declared behavioral transfer blocks. Optical controls observe input-side LED current without adding a conductive control path. The pass element draws its output current from the actuator branch, and gate-drive switches charge/discharge their capacitances from local rails. Input-side source impedance, permanent GPIO bias, base/LED resistors and existing RUN branches are visible in the network.

LOGIC_GND/ACT_GND are represented by one ideal local node; PCB Kelvin paths, shared-impedance errors and bypass placement are not electrically extracted. HCT/PG outputs are ideal behavioral voltage sources with a lumped standing rail load, so no complete semiconductor power/thermal ledger is accepted. GPIO/RUN source resistances, NPN storage, optical poles, supervisor timers, regulator dynamics and MOS capacitance are assumptions. They are labeled accordingly.

Eight independent ngspice controls and two final-precision spot reruns are retained under `probes/`:

| Control | Independent conditional result |
| --- | --- |
| Baseline repeat | Final coil1.482A, gate5.140V |
| Actuator return open | Late carrier-return current23.88mA; coil decays with finite stored energy |
| Same return open plus deliberate domain bridge | Late carrier-return current1.535A, coil remains energized |
| Drain-source short with command low | Gate approximately0V while coil remains1.486A |
| Optical receiver forcibly blocked, LED drive retained | Gate off; final coil approximately12nA |
| Supervisor output forcibly blocked | Gate off; final coil approximately12nA |
| Extra MAIN_IN conductance | RUN source demand exceeds4mA; no actual U9/VNP guarantee follows |
| Cold half-step | Sampled ideal inrush changes markedly, final late currents/state do not |

The optical/supervisor controls show that coil state follows the declared electrical chain rather than a hidden direct duty assignment. The unsafe bridge and drain-short controls remain unsafe as intended. Coil current can continue after the gate falls; the model includes stored energy and capacitive switching transients, not an instantaneous mechanical close.

Both optical-pole assumptions were inspected across1/2/4/10/40µs commands. The1µs command passes under the0.2µs pole and is lost under the2µs pole. A single pulse/tau pair cannot establish a physical minimum pulse. The1µs half-step changes peak current by about4.31e-5 relative within this model. The longer assumed supervisor assertion produces about99.94µs of gate-above2V with rail below4.5V, compared with9.95µs for the shorter assumption. These are sensitivity consequences, not datasheet maxima or regulator/brownout acceptance.

All11 retained short-pulse windows match the preceding full traces' peak current and gate width at the original export precision. Increasing export precision changes only decimal rounding. The final data retain every ngspice row in the declared windows, with finite13-column vectors and exact end times. Short-pulse tails after2.2ms are not retained and no complete pulse-energy ledger is claimed.

## Remaining physical and review limits

This review does not reaccept native ERC/DRC/parity or the copper/assembly review. Literal component/interface checks and source hashes prevent stale nominal values; they do not establish device dynamics from CAD. No real regulator stability/overshoot, loaded GPIO/RUN level, NPN storage range, exact procured PDIP guarantee, parasitic loop behavior, isolation capacitance, component temperature, minimum physical pulse, valve current limit or mechanical position is validated.

There is no firmware/engine/Speeduino coupling in these new electrical experiments. The earlier executed-PWM engine comparisons remain separate evidence. Physical idle stays inhibited; no target was flashed. Exact valve/protected power/disconnect, eFuse routing, mounting/live tabs, finished holes, underside fit, RF/enclosure and powered fault tests remain open. A normal-current stuck-on switch still requires an independent branch disconnect; a fuse alone is insufficient.

## Reproduction and immutable evidence

`probe.py`, `results.json` and their initial snapshot bind the eight independent electrical controls and earlier full-window comparison. `final_audit.py`, `final-audit.json`, the final snapshot and `reviewed-data-sha256.json` bind the final precision export and two spot reruns. `probe-initial.log` retains the first strict-time audit rejection before print precision was increased; it is not a remaining circuit failure.

These cache scripts use their original paths and refuse to replace existing probe directories. Restore snapshots or choose fresh review outputs when reproducing them. The report and manifests preserve source history instead of relabeling old runs as current. No vendor models or proprietary primary-source PDFs are redistributed in this circuit review.
