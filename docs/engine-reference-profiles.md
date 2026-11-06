# Expanded production-reference engine comparisons

The new reference fixture runs pinned, non-`UNIT_TEST` Speeduino with sixteen distinct native GPIO outputs. Both controllers drive separate instances of the generalized MVEM air path and empirical combustion/free-shaft plant. The physical cylinder count, firing order, displacement, tooth wheel and cam position are explicit and shared between the two runs. Their sensor traces and resulting shaft speeds are independent.

This extends the previous setup-only geometry probe. It does not add PCB channels or qualify a physical engine. Normal ESP32 builds still inhibit engine outputs; the fitted carrier remains four injector and four coil commands. The wider feature goal, expanded turbo comparisons, online tuning integration and target/physical qualification remain unfinished.

## Reference fixture

`scripts/build_speeduino_profiles.py` verifies upstream commit `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`, unchanged tracked production sources, copied headers and dependency identities. The original 109 objects must relink to the exact historical binary SHA256 `046389d754c996c34cb7e7171b1e42088f5ae6c0615133a3c5e74743f9f6d52c`. The new executable reuses108 objects and substitutes only its native fixture entry point. The original four-cylinder executable, manifest and external checkout stay unchanged.

The real production `setup()` loads the selected configuration through its storage API. Before clock advancement, trigger input or output recording, the fixture stops schedulers, closes the original outputs, binds eight injector and eight coil pins, and invokes the actual public ignition/fuel initializers. Those initializers validate configuration, bind production IO/callbacks, reset schedules and calculate their angles. Schedulers then restart. This explicit native board setup is distinct from the original v0.4 board mapping.

| Native output | Pins |
| --- | --- |
| INJ1..8 | 22,23,25,26,27,28,29,30 |
| COIL1..8 | 31,32,33,34,35,36,37,38 |

All sixteen `(port,mask)` combinations must be distinct, below FakeMega's70-pin table bound and separate from every resolved input/auxiliary binding. The fixture observes each actual port transition. It never creates a partner-cylinder edge in Python. The record at every edge carries sync status, ignition/injection spans, effective injection layout and active schedule counts.

The fixed benchmark has500cc per cylinder,300cc/min injectors,10.7ms full-cycle required fuel, neutral corrections, a60-2 crank wheel, physical tooth1 at90° before C1 compression TDC and one cam edge at540° of shaft rotation. Native tables/sensors retain their production quantization and polling behavior. Timer ticks are4µs with32-bit native counters; input callbacks and normal loop opportunities cost zero simulated CPU time. This is neither AVR/ESP32 emulation nor measured target timing.

For one cylinder, `divider=0` deliberately selects the production default of two non-sequential squirts per720°. A prior fixture selected one squirt while the production fuel calculation still halved the dose; its stalled run is retained as a failed fixture experiment. The correction changes configuration only. Readback now verifies the divider and two-squirt result. Sequential mode selects one full-dose injection through the existing production behavior.

## Effective modes and physical wiring

Requested sequential is retained for1..8 cylinders. On4/6/8-cylinder engines, production callbacks temporarily use wasted-COP and semi-sequential injection while cam sync is partial, then switch to sequential. Both setup and actual event-time states are retained.

Requested wasted-COP is valid for4/6/8. Requests for1/2/3/5/7 fall back to WASTED; injection layouts may also fall back. Odd3/5-cylinder WASTED ignition has schedules spaced360/N, whereas physical compression TDCs follow720/N. For zero-based native index `i`, the declared static coil wiring therefore uses firing-order position `(i*(N+1)/2) mod N`. It maps observed native pins to physical cylinders; it does not change an edge timestamp or replicate a pulse. Injector wiring and actual bank callbacks remain separate. In five-cylinder semi mode, native injector pins3+5 share a production callback and phase.

Two reference fallbacks cannot represent the chosen even-fire COP geometry:

- Two-cylinder WASTED schedules have0/180° offsets; equal-fire four-stroke compression TDCs coincide modulo360°.
- Seven-cylinder fallback has three ignition schedules and three primary injection schedules for seven physical cylinders.

The ordinary coupled API rejects these cases. An explicit diagnostic opt-in retains their actual behavior and marks the mismatch in the reference profile. These observations do not establish that every two-cylinder engine topology or upstream board is unsupported.

Seven-cylinder sequential ignition uses integer102° schedule increments rather than720/7°. The static1000RPM fixture measures up to5.871° spark error, including the native predictor/timer behavior; other representable static profiles measure up to0.728°. The project retains fractional angles. Its two-cylinder sequential counterpart also differs from the reference's180° second injector offset. Actual injection-closing errors remain in the raw prescribed-shaft results.

Free-shaft timing is recorded independently from the static shaft test. Rapid single-cylinder speed variation can increase reference prediction error: the four-second baseline measures1.831° for batch and1.918° for sequential after3s. An initial comparison test incorrectly imposed a1.5° common bound; its failed report is retained. The project keeps its timing gate, while upstream timing remains measured comparison data. A last sampled reference demand is not an event-latched demand, and a watchdog-induced coil falling edge is not proof of a correctly timed combustion. No static or coupled result establishes physical timing accuracy.

## Tests and reproduction

The acceptance script exercises all24 requested count/mode combinations, actual output identities, phase, readback, global-low shutdown, invalid commands/clocks and hard-limit cuts. Three original four-cylinder modes must retain exactly the same mapped edge tuples and core status fields as the preserved original executable.

The coupled comparison script exercises all24 project profiles and all24 reference requests. Four incompatible reference fallbacks are diagnostic controls; they are not successful matched profiles. It also tests extended-channel faults, fixed physical geometry with wrong project firing order/reference wiring, and250/125/100µs coupling refinements. Fuel, chemical, shaft and air ledgers must close. Reference measurements remain comparison data rather than being forced to meet the project's scheduler contract.

The [reviewed comparison packet](../reports/engine/expanded-reference/README.md) records68 coupled runs:44 normal profiles,4 unsupported reference-geometry diagnostics,6 fault cases,2 fixed-geometry causal controls and12 refinements. All24 project profiles and20 representable reference profiles power the declared engine after starter removal. Twelve complete original four-cylinder coupling results remain exactly equal before/after this change. The independent review checks source/IO/modes, its own coupled cases and analytical variable-speed shafts; the parent separately validates the full68-run matrix. Neither scope completes the wider ECU goal.

In the existing pinned Linux workspace, with the original native build and profile FMU prerequisites from the [research benchmark guide](engine-research-benchmark.md):

```sh
python3 scripts/build_speeduino_profiles.py --output NEW-BUILD-DIRECTORY
python3 tools/test_speeduino_profiles.py --executable NEW-BUILD-DIRECTORY/speeduino-profiles --output NEW-GPIO-RESULTS
uv run --with fmpy==0.3.26 python tools/test_engine_profile_comparison.py --executable NEW-BUILD-DIRECTORY/speeduino-profiles --output NEW-COUPLED-RESULTS
```

Output directories must be new. Build manifests bind sources, objects, libraries, compiler flags and executable identities. A fresh machine must reconstruct the attested prerequisites; changing an expected hash is not a substitute for that reconstruction.

Primary production code remains unchanged: [ignition setup/callbacks](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/scheduler_ignition_controller.cpp), [fuel setup/callbacks](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/scheduler_fuel_controller.cpp), [required-fuel calculation](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/fuel_calcs.cpp).
