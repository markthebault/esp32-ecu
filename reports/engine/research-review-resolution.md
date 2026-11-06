# Research adapter review follow-through

[Independent scientific review](independent-research-plant-review.json) tested the actual FMU, controller coupling, conservation, cylinder charge, lambda freshness, output traces and production halt. The reviewer did not edit production or upstream files. Its remaining hard-limit rerun is completed in the final matrix below.

The final bench profile explicitly enables Speeduino `PROTECT_CUT_BOTH` and `HARD_REV_FIXED`, then reads the loaded configuration back after production setup. The overrev case uses a declared 70 Nm external motoring interval from 6.0 to 6.25 seconds. All three implementations actually cross 6500 RPM and report fuel/ignition cut:

| Controller | Peak free RPM | 1 ms samples observing hard cut |
| --- | ---: | ---: |
| Project core | 6705.2 | 350 |
| Speeduino native | 6676.5 | 209 |
| Speeduino native, per tooth | 6698.5 | 217 |

The motoring dynamometer supplies work even while the controller cuts combustion, so these peaks are not a failure to hold shaft speed against an external motor. Its work is booked explicitly. Soft-limit and hysteresis policies differ and are documented.

The [final matrix](full-controller-comparison.json) passes 21 controller/scenario cases and six coupling-step comparisons. Largest checked change on halving the step is approximately 0.0311%. Maximum residuals across the controller cases are about 4.91e-8 mg fuel, 7.77e-9 J shaft work, 5.90e-9 J released chemical energy, 1.29e-11 kg intake mass and 0.0105 J intake energy. These are model accounting/convergence checks, not engine calibration.

The reviewer independently reconstructed all 18 baseline scenario edge traces and verified monotonic timestamps, rise/fall alternation, pulse widths and explicit final halt. The final matrix adds MAP-short tests and the enabled hard-limit profile. Parent integration tests also exercise native halt with actually high injector and coil outputs. Pre-termination highs and natural trigger-loss output latencies remain separate from explicit stop records.

The first sweep's three failed expectations are retained under `.cache/engine/comparison-baseline-unprotected`. A long trigger gap stopped each rotor, so signal restoration alone could not restore idle. The corrected expectation checks coast-to-stop separately from a starter-assisted restart. The original profile also failed to enable the native protection modes and never crossed its written hard-limit value. Those were test-profile omissions, not established upstream ECU bugs.

Transient native spark error references last observed demand; the project uses event-latched demand. Neither aggregate error is a physical target timing measurement. Stock research-engine combustion, physical engine calibration, target interrupt timing, vehicle/environment behavior and full feature parity remain unqualified.
