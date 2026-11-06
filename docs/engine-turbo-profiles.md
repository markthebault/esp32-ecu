# Generalized turbo research geometry

The turbo composition now binds explicit1..8-cylinder `EngineGeometry` to the actual TCSI engine-pumping graph and empirical per-cylinder combustion plant. The native project dispatcher can drive all declared engine channels plus boost, including sequential cam events. This is a simulation foundation toward the wider ECU goal. It does not establish a matched turbo for every engine size or an expanded genuine Speeduino turbo comparison.

The existing PCB remains four injector and four coil commands. Normal firmware outputs remain inhibited. No physical engine, target timing, electrical, RF, thermal, splash or printed-fit qualification follows from this work.

## Physical binding

The source engine-flow graph consumes **total** displacement. It computes total four-stroke airflow; count partitions that flow among cylinders. The composition therefore binds total displacement once and freezes each cylinder's trapped air from `total_flow × 4π / omega / count` at its intake-close event. Firing order, compression TDCs, injector/coil arrays and sparse logical IDs use the same declared physical geometry.

Geometry overrides are applied to private copies of model parameters and provenance before graph creation. Previously constructed graphs and a caller's shared model retain their original parameters/caches. Readback records actual graph displacement, count, per-cylinder displacement and authored overrides. The underlying source files stay unchanged. Bore, stroke and detailed valve/piston mechanics are not modeled by this mean-value/empirical composition.

The six source gas volumes describe fixed hardware and are retained independently of cylinder count/displacement:

| Volume | Litres |
| --- | ---: |
| Filter | 10 |
| Compressor charge | 5 |
| Cooler | 5 |
| Intake manifold | 1.8 |
| Exhaust manifold | 2.5 |
| Tail | 20 |

The implicit historical turbo graph really pumps1.8L. Its geometry label now records4 cylinders/1800cc/1-3-4-2; its numerical behavior stays unchanged in the checked fixtures. Explicit geometry deliberately changes pumping volume. The source turbo/maps, inertia, restrictions and gas volumes do not automatically become suitable for a different engine.

## Cuts, boundaries and evidence

Global command-low processes every declared injector and coil, including logical10..17, plus auxiliary commands. A charged smart-coil command can discharge and spark when removed; it is not an ideal power quench. Result files retain separate before/after-halt states, discharge records, per-cylinder totals and pending heat/fuel/work inventories. Model solenoid current may decay after its command goes low.

Typed/finite edge and integration checks reject invalid requests before physical state changes. Within the declared floating-point clock tolerance, accepted edges use the same physical boundary. Independent review found that a slightly future accepted rise could otherwise interrupt a later global cut halfway; the corrected path is independently retested. Candidate RK failures retain the previous plant and exchange inventories.

Coupled provenance binds the actual loaded sparse-channel layout to `config/engine-profile.json`, snapshots it and records its hash. A stale loaded layout/channel constant is rejected. Earlier runs missing that dependency or post-halt diagnostics remain historical records, not post-cut proof.

The [development packet](../reports/engine/turbo-profiles/README.md) includes eight geometry/atomicity test groups, existing regression checks,200 exact parent numerical-state replays, independent analytical/model and controller-coupling reviews, and native1/7/8-cylinder run records. The reviewer preserved1,002 historical numerical values exactly and checked48 analytical flow cases. These finite checks do not prove general convergence or physical accuracy.

The sequential8-cylinder charged-stop run cuts actual logicalCOIL17 after1745µs, records436.832J additional modeled chemical energy and180.514J newly pending exhaust heat, and closes the post-cut coupled energy ledger within2.3×10⁻⁸J. The independently run7-cylinder semi-sequential stop releasesCOIL16 after1637µs; its wasted-stroke discharge correctly adds no combustion heat. Both record the coil's energy at discharge; no separate ideal coil-power quench is modeled.

## Observed limit and remaining work

The8-second,20%-throttle4L open-loop experiment records234 actual boost PWM edges. Its intake manifold remains under ambient pressure; this is actuator/coupling evidence, not target-pressure tracking.

A separate4L/80%-throttle/35Nm run fails at4.730343s when the source turbo exceeds its declared0..24000rad/s map domain. The last trace at4.72s records23861.4rad/s,146.766kPa charge pressure and102.084kPa manifold pressure. The failed experiment is preserved and excluded from passing evidence. A matched turbo/map/hardware hypothesis is required before wider high-load comparisons. This does not identify a physical engine or controller defect.

The current genuine turbo reference remains the historical4-cylinder/1800cc batch fixture. Requests for expanded reference geometry/strategies fail before creating an output directory. The separate16-output naturally aspirated fixture is not silently substituted for boost execution. Next work is explicit matched turbo parameters, a16-output production boost fixture, paired normal/fault/refinement comparisons and wider configuration/control/PCB integration. Dynamic cam-dropout and expanded closed-loop boost behavior are not established by this packet.

## Reproduce

In the existing pinned Linux workspace:

```sh
python3 tools/test_turbo_geometry.py --output NEW-TEST-DIRECTORY
python3 tools/run_boost_engine.py --output NEW-RUN-DIRECTORY --cylinders 8 --strategy sequential --mode off --duration 3.9572 --load-nm 5
python3 tools/verify_turbo_geometry_run.py NEW-RUN-DIRECTORY --charged-cylinder 8 --output NEW-AUDIT.json
```

The example is a fixed research fixture, not an engine tune. CLI cylinder profiles use500cc per cylinder and the printed reverse-order-after-C1 fixture unless an explicit displacement is supplied. The Python API accepts a complete physical `EngineGeometry`. Output paths must be new. Model and toolchain prerequisites remain in the [turbo benchmark guide](engine-turbo-benchmark.md).
