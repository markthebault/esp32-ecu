# External engine research benchmark

The project engine core, decoder and scheduler now drive an external research plant. The pinned Speeduino production `setup()`, `loop()`, decoder and schedulers drive independent copies of the same plant. RPM comes from fuel, actual spark events, starter, inertia and load. Each controller receives its own resulting sensor history.

This extends the earlier fuel-kernel comparison. It is an uncalibrated software benchmark. The ESP32 remains a shadow bench monitor with physical engine outputs inhibited. This work changes neither PCB manufacturing records nor the enclosure.

## Run

Use the existing Docker daemon and the pinned external Speeduino checkout. The original checkout is retained. Generated sources, executables, FMU and full edge traces stay under `.cache/engine`.

```sh
python3 scripts/probe_engine_modelica.py
python3 scripts/build_engine_airpath.py
python3 scripts/build_speeduino_sim.py
python3 tools/test_speeduino_runtime.py
uv run --with 'fmpy==0.3.26' python tools/test_research_plant.py
uv run --with 'fmpy==0.3.26' python tools/validate_engine_comparison.py
```

The Speeduino build uses dependency archives from the upstream native tests. Run those first if absent, as described in [engine development](engine-development.md). No command starts or restarts a host service. The Modelica export uses a temporary Docker container with no network or published ports after prerequisites are cached. FMPy loads the local FMI 2.0 co-simulation artifact with CVODE, following the [OpenModelica FMI export documentation](https://openmodelica.org/doc/OpenModelicaUsersGuide/1.25/fmitlm.html).

For one bounded case:

```sh
uv run --with 'fmpy==0.3.26' python tools/compare_engine_controllers.py \
  --controller speeduino_per_tooth --scenario stall_restart --duration 12 \
  --output .cache/engine/comparison/individual-restart.json
```

Controllers are `ours`, `speeduino`, and `speeduino_per_tooth`. Cases cover warm start, throttle, resisting load, trigger dropout, MAP rail short, starter-assisted restart and rev limiting. `--step-us 125` halves the default 250 µs coupling interval. This command-line research suite is separate from the web UI's earlier reduced-order SIL plant; it does not replace or silently relabel that simulator.

## Plant and actuation

[Modelica-MVEM](https://github.com/modelica-3rdparty/Modelica-MVEM) supplies unchanged compressible throttle, intake-volume thermodynamics, gas properties and speed-density pumping components. A new composition sets one explicit 2 L geometry and a naturally aspirated pressure domain. The stock engine model cannot start at zero speed, commands its own fuel, and has no usable spark interface. Its burner also assumes combustion, so it is unsuitable for fuel-only or ignition-cut tests.

The local closure supplies pulse-derived injector delivery, wall/port fuel storage, intake-closing charge capture, combustion and a free shaft. Cylinder air is frozen at intake closing. An actual coil falling edge, its delivered dwell/energy and its angle relative to physical cylinder phase determine combustion. Requested pulse width or advance never substitutes for delivered actuation.

Fuel and spark alone cannot produce combustion work. Missed-cycle fuel leaves through an unburned ledger. Lambda validity expires without recent combustion, shaft rotation or pumping. The shaft accounts for starter, resisting load and friction work. Separate ledgers expose delivered/burned/stored/unburned fuel; released chemical energy, heat, pending and delivered shaft work; kinetic energy; and intake mass/energy balance.

The torque, timing-efficiency, combustion limits, coil, injector, wall-film, starter and friction parameters are local empirical assumptions. Conserving their bookkeeping does not calibrate them. Exhaust pressure is fixed; this model does not predict exhaust filling, knock, emissions, real cold starting or a vehicle's safe mixture/timing. It needs independent measured engine/actuator data before engineering calibration conclusions.

## Matched configuration and clock

The comparison uses a declared neutral bench profile: four cylinders, 2 L, 300 cc/min injectors, gasoline AFR 14.7, flat VE 85%, spark 10° running/5° cranking, lambda 1, 0.9 ms dead time and 2.8 ms dwell. WUE/cranking corrections are 100%; ASE, EGO and DFCO are off. These settings isolate controller execution; they are not either project's physical engine base tune. The existing default-profile regressions remain separate.

Both use 60-2 teeth with tooth 1 at 90° BTDC. Speeduino channels are explicitly mapped to the project's physical 1-3-4-2 order. Its full storage API saves and reloads the bench tune before normal production initialization. The wrapper reads back required fuel, limits, protection type, hard-limit mode and per-tooth mode, rejecting a mismatch.

The project uses per-tooth deadlines, a 1 ms control sample and its existing ramped soft limit/hard-cut hysteresis. Native Speeduino runs its production loop at coupling boundaries and after trigger callbacks; the standard and per-tooth configurations are both exercised. Speeduino uses its production sensor polling, quantization and stopped-state defaults, relative 10° soft retard at 6200 RPM, and explicitly enabled fixed 6500 RPM cut of fuel and ignition. Its limit semantics differ from the project's ramp/hysteresis.

The rev case applies 100% throttle from 3 s. A simulated motoring dynamometer supplies 70 Nm from 6.0 to 6.25 s so the shaft actually crosses the hard limit even if soft retard would otherwise hold it below that limit. This external work is included as negative resisting-load work. Cut status and actual threshold crossing are asserted; the scenario name alone is not evidence.

Time is integer microseconds. Virtual timers fire before a coincident trigger, then the main loop runs. Output edges split plant integration, and actual shaft angle generates teeth. The adaptive coupling reports its angular quantization and is checked by step halving. Project spark errors reference latched dwell-start demand; native errors reference the last sampled production demand. Use measured actual angles or constant-demand intervals when comparing timing.

## Evidence and remaining boundaries

[Comparison results](../reports/engine/full-controller-comparison.json) retain the matrix, convergence results, source hashes, build provenance, explicit profile and qualification limits. Full traces stay in `.cache/engine/comparison`. [Plots](../reports/engine/research-benchmark-charts.html) show the saved trajectories. Independent runtime and scientific reviews are recorded alongside the results.

Source verification reconstructs pinned Git trees and checks 71 MVEM files and 1438 Modelica/ModelicaServices/Complex files. The native builder rejects unlisted cached sources and fingerprints dependencies, headers, compiler and flags. Coverage artifacts go to this repository's cache. The original source checkout is not changed. Upstream GPL source and linked binaries are not redistributed; the MVEM repository's conflicting root/header license notices remain recorded in the source assessment.

The native Speeduino HAL uses 32-bit timer counters at 4 µs and zero CPU execution cost. It is not AVR emulation. Its long pending events at very low speed can differ from AVR's 16-bit timers. Trigger injection calls the actual decoder callback directly, so it does not validate interrupt wiring or edge selection. The project portable scheduler likewise has no target ISR/GPIO timing evidence here.

A long trigger gap can stop the rotor. Restoring signal availability does not turn a stopped shaft; the separate restart case applies a starter. Natural fault-gap edge timing is reported separately from explicit end-of-test halt. Ending with virtual outputs low does not prove natural shutdown behavior.

Target ISR integration, other trigger/cylinder/phase strategies, tuning transport integration, PCB additions, calibrated physics and electrical/HIL validation remain part of the [feature gap](engine-feature-coverage.md).
