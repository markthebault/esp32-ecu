# Expanded production boost reference

A separate native fixture now combines sixteen actual engine-output GPIOs with production Speeduino boost PWM, raw ADC inputs and crank/cam callbacks. It uses the same pinned production code as the earlier four-cylinder turbo benchmark. The original executables, objects and upstream checkout are preserved. Generalized turbo runs select the new fixture by its explicit build-manifest scope; the older fixture remains limited to its declared4-cylinder/1800cc batch profile.

This extends research comparisons, not physical ECU qualification. The existing carrier still has four injector and four coil commands; normal project firmware keeps engine outputs inhibited. A suitable turbo/map/hardware combination remains a separate physical assumption.

## Construction and inputs

`scripts/build_speeduino_profiles_turbo.py` verifies the original109 objects relink exactly to SHA256 `046389d754c996c34cb7e7171b1e42088f5ae6c0615133a3c5e74743f9f6d52c`, then reuses108 unchanged production objects. The entry includes the accepted sixteen-pin project fixture through a generated bridge which changes only its `main` and observer symbol names. Production decoder, fuel, ignition, protection, PID and PWM algorithms are unchanged. The bridge bytes and exact substitutions are recorded and snapshotted.

Real `setup()` loads the declared tune through production storage. Before clock advancement or trigger inputs, the entry rebinds actual IO/schedules using the production initializers. Engine pins and `(port,mask)` identities retain the [sixteen-output contract](engine-reference-profiles.md); the boost port is separate. Boost observations come from actual port transitions, with a consistency check against the fake board's digital-write state. Python never synthesizes a missing cylinder edge or a requested PWM duty.

Full-cycle fuel is represented in the production0.1ms byte quantum. The fixture's declared300cc/min injector datum gives10.7ms per500cc/cylinder;450cc/cylinder rounds to9.6ms, preserving the historical1.8L fixture. Unrepresentable fuel quanta reject before launch. This is a benchmark translation, not physical injector calibration.

The profile includes0..400kPa MAP,24Hz requested boost, neutral primary maps and an explicit nine-bin integer IAT-density curve. Research temperatures/AFR can reach declared ADC rails; counts clamp to0..1023 before production `analogRead()`. Actual sensor polling/table quantization remains visible.

The native main loop follows an absolute calendar, normally1000µs. Plant integration calls and status queries do not create extra controller-loop opportunities. Timer ticks remain the earlier4µs/32-bit native model, with zero modeled CPU/IRQ cost. This is not AVR/ESP32 timing emulation. Native24Hz PWM has a41664µs period in the checked steady fixture because of timer quantization.

An explicit zero initial compare enables the native timer fixture. A separate default-unarmed negative control retains the original `UINT32_MAX` compare, producing requested40% duty with no actual boost edges in the checked interval. The selected initial condition is always recorded.

## Effective modes, halt and validation

Requested/effective engine modes accompany actual GPIO edges. Partial cam sync can change sequential4/6/8-cylinder operation to production wasted-COP/semi behavior. The existing odd3/5 wiring permutation and five-cylinder shared injector-bank caveat remain explicit. Two- and seven-cylinder non-sequential fallbacks cannot represent this even-fire COP fixture; ordinary coupled requests reject before creating an output directory. A diagnostic opt-in records those mismatches without treating them as matched profiles.

The explicit reference `halt` retains the historical engine-only fixture behavior: engine schedulers stop and their GPIOs close, while production boost demand/timer remain independent. The external simulation-ending cut also lowers the modeled valve command. Its post-halt record separately reports native reference boost state; a modeled command-low must not be mistaken for proof that the upstream boost controller disabled itself.

The wire parser validates complete bounded lines, exact argument counts and whole numeric tokens before clock, input or ADC mutation. Independent review found that numeric-prefix extraction could otherwise accept malformed suffixes after advancing time. Rejected launch arguments also isolate dependency coverage output before validation. Those failed candidates and corrected checks are retained as history.

## Evidence and audit scope

Native acceptance checks72 startup combinations,24 actual motion profiles, all sixteen engine ports, boost PWM, pressure cuts, ADC rails, fixed-calendar partition invariance, timer negative control, invalid public/raw inputs and exact historical four-cylinder behavior. The closed-loop native control includes nonzero PWM, rather than relying only on its startup interval. Independent review separately reconstructs the original relink and exercises its own probes.

The generalized coupled audit checks sparse output IDs, consumed-edge cursors, actual cam records, tune/plant/graph geometry, loaded layout, generated adapter snapshots and both before/after-halt inventories. Shared executing project source identities must match across comparisons. Extra reference fixture/build sources are separately declared and hashed rather than silently ignored. Reference-only fixture inputs cannot excuse a changed shared plant/controller module.

These are finite uncalibrated research runs. Low-throttle open-loop operation can remain below ambient manifold pressure, so executed PWM and engine operation do not establish pressure-target tracking. The [earlier4L high-throttle failure](engine-turbo-profiles.md) still marks the source turbo-map boundary. Matched turbo parameters, expanded closed-loop/fault coverage, other trigger/control features, PCB expansion, supported online tuning and target/physical tests remain part of the full goal.

The [development packet](../reports/engine/expanded-boost-reference/README.md) retains the finite-step failure. The project's500→250µs check stays below0.018% across the selected final-window metrics. The reference differs by12.72% meanRPM and19.72% turbo speed; its250→125µs check also fails, at20.21% and37.69%. The2% gate is unchanged. These reference runs are not accepted as a converged paired benchmark. A read-only combustion observer reproduces the exact ordinary output prefixes and locates different cylinder/mixture outcomes near partial-to-full sync; it does not isolate a production bug or justify fitting the plant.

The400kPa sensor-rail input becomes ADC1023 in the reference. Production MAP validation rejects that rail and retains47kPa in these runs, with `boost_cut=0`; setting the reference protection cap to0 gives the same result. Continued output therefore does not establish a correctly detected overpressure or an effect of the6500RPM cap. The project receives the declared physical-unit fault and cuts. Raw ADC, held MAP and native cut status stay separate in the evidence.

## Reproduce

Use new output directories in the pinned Linux workspace:

```sh
python3 scripts/build_speeduino_profiles_turbo.py --output NEW-BUILD
python3 tools/test_speeduino_profiles_turbo.py --executable NEW-BUILD/speeduino-profiles-turbo --output NEW-NATIVE-RESULTS
python3 tools/run_boost_engine.py --output NEW-RUN --controller speeduino --reference NEW-BUILD/speeduino-profiles-turbo --cylinders 8 --strategy sequential --mode open_loop --duration 4 --load-nm 5
python3 tools/verify_boost_engine.py NEW-RUN --current-inputs
```

Run the project controller separately with the same physical profile and stimulus. Neither controller receives the other's sensor trace or resulting RPM. Source/model/toolchain prerequisites and the empirical combustion/gas limits remain in the [turbo benchmark guide](engine-turbo-benchmark.md).
