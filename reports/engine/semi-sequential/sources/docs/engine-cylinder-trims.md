# Individual cylinder fuel and spark

The four-cylinder sequential core now has four independent 6×6 fuel trim maps and four signed spark offsets. Browser tuning, persistent JSON, own 003 MSQ exchange, channel proposals and engine logs carry the same physical cylinder identities. Physical engine outputs remain inhibited in the selected N16R8 build.

## Configure and identify channels

Select **Engine development → sequential mode → Physical cylinder adjustments**. Enable individual trims explicitly. A disabled tune may retain nonneutral values, but control ignores them. Enabling trims in batch/wasted mode is rejected.

| Physical cylinder | Injector command | Smart-coil logic command |
| --- | --- | --- |
| 1 | INJ1, J9 pin 1 | IGN1, J10 pin 1 |
| 2 | INJ2, J9 pin 2 | IGN2, J10 pin 2 |
| 3 | INJ3, J9 pin 3 | IGN3, J10 pin 3 |
| 4 | INJ4, J9 pin 4 | IGN4, J10 pin 4 |

Array order is always physical 1/2/3/4. Firing order assigns their 720° phases and does not reorder the calibration arrays. Verify compression TDC, the wiring harness and output polarity independently. The existing [connector contract](../hardware/a3-compact/connector-pinout.csv) already has these four channels. This increment changes no PCB, BOM, case or manufacturing artifact. Electrical load, flyback, coil, module-fit and environmental qualification remain undone.

Fuel maps use ascending RPM and MAP axes. Bilinear interpolation clamps to the nearest edge outside the axes. 100% is neutral; allowed cells are 50–150%. Signed spark offsets are −10..+10°; positive advances spark. Defaults disable trims and contain neutral values.

For each cylinder, `PW = effective_fuel_time × trim_percent/100 + deadtime`. Deadtime is added once and is not scaled. Check the applied pulse against the configured injection limit and fresh-RPM duty interval; one cylinder exceeding capacity inhibits all channels. The existing 15 ms injection and 3.5 ms coil limits remain. Valid negative trims can make the actual pulses fit even when the untrimmed scalar demand exceeds 15 ms.

Nominal spark plus its offset is clamped to −5..40° while running, or −5..15° while cranking. Mandatory soft-limit retard follows that clamp, with a −5° floor. Separate capacity, nominal-clamp and retard-floor masks identify affected cylinders. These are bounded software proposals, not cylinder pressure, knock protection or measured output timing.

An open injector retains its closing edge. Each coil latches its own advance at dwell start. During acceleration, a target tooth can arrive just before an already committed discharge. The scheduler retains that unchanged discharge only when it is pending, charged, at most 25 µs away, within a combined 0.2° lateness budget and within maximum dwell. A future goal that rounds to the current microsecond is covered. Larger errors or an expired edge fault. Phase, freshness, dispatch-lateness and independent high-time supervision still apply.

## Storage, tuning and debug

Engine JSON schema 3 adds `cylinder_trims: {enabled, spark_deg[4], fuel_maps[4]}`. Exact schema 1/2 documents migrate to disabled neutral trims with their original revision. Existing files and NVS records stay unchanged until Save. The previous defaults remain in [defaults-v2.json](../config/engine/defaults-v2.json). Engine documents now have a 24 KiB bound within the existing 64 KiB engine NVS partition. Sensor configuration keeps its 16 KiB bound. Near-limit legacy migration and allocation-failure cases are tested; physical flash wear and power-loss behavior remain unmeasured.

Use [esp32-ecu-cylinder.ini](../tuning/esp32-ecu-cylinder.ini), identity `ESP32ECU SIL 003 INHIBITED`. The first four pages remain; page 5 is 800 bytes. It holds four 192-byte maps, four float spark offsets at 768, a U32 enable at 784 and zero reserved bytes 788..799. The 184-byte output block preserves the old 100-byte prefix, then adds four sets of PW/advance/fuel-percent/duty and five validity/enable/mask fields. Exact 001/002 MSQs import with neutral disabled trims, even when the current editor has active adjustments. Historical INIs/MSQs remain available.

Actual TunerStudio MS Lite 3.3.01 loaded the 003 editors, saved C2 spark −3→−2.5° and the C2 map cell at 1600 RPM/50 kPa 120→117.25%. The [application-authored MSQ](../tuning/examples/tunerstudio-cylinder-roundtrip.msq) imports through the native validator with the correct physical cylinder and cell orientation. This is offline file interoperability. Live TunerStudio acceptance of our controller identity and a physical tuning transport remain unresolved.

The live browser table and JSON expose each applied channel proposal plus clamp/capacity masks. Scalar PW/advance/duty remain untrimmed base demands. Engine MSL 002 preserves the previous 58-field prefix and adds 21 fields, for 79 total. A sample without cylinder data marks those channels unavailable. The 256-row recorder now occupies 73,816 static bytes, with a 4,696-byte copied page. Runtime heap, stack high-water and timing under sustained load remain unmeasured.

The existing 232-byte ESP-NOW engine schema 1 retains its eight inputs, fourteen base proposals and flag layout. It does not carry these per-cylinder arrays. Use web/JSON/MSL for the added detail; a future negotiated radio extension must not silently change schema 1. Engine screens remain read-only.

## Comparison and limits

[Evidence](../reports/engine/cylinder-trims/) retains eighteen new external-plant runs, raw edge/combustion traces, coupling checks, desktop/browser checks and independent source/target reviews. Both controllers drive separate instances of the hash-verified external MVEM air path plus local empirical combustion/free-shaft model. CPU/IRQ execution cost is zero. This is an uncalibrated software benchmark, not physical qualification.

Four fixed injector flow factors `[1,.9,1.08,.95]` and optimum-spark offsets `[-3,2,5,-4]` belong to the plant independently of either controller. Disabled and enabled-neutral configurations produce identical edges and combustion records. Correct physical trims reduce cylinder mixture/work spread; intentionally swapping C2/C3 worsens it. Final absolute lambdas remain roughly 0.77–0.78. The experiment establishes balancing behavior, not a stoichiometric, optimal or safe engine tune.

Pinned production Speeduino applies integer `percentageApprox` to the whole PW, including deadtime. Its inverse-flow percentages therefore overcorrect short pulses relative to our fuel-before-deadtime rule. Both the identical-percent experiment and a separately labelled total-PW adjustment are retained. The latter derives percentages from known simulated flow/deadtime and one measured neutral idle PW; it is a single-point oracle calibration, not blind tuning or a complete load-dependent calibration. Reference 6×6 axes/cells and spark use their actual production quantization. Physical output order is mapped explicitly.

Additional runs cover throttle response, strict versus retained cam-phase policy, batch regression, native16/native32 reference timers and 125/250 µs coupling. The largest relative convergence difference in final speed, fuel and combustion work is below 0.9%, against a 3% bound. Our new transient cases keep latched spark error below 0.034°. Speeduino's comparison metadata uses the last sampled demand rather than event-latched advance, so those error numbers are not directly equivalent. The 16-bit model is a Mega-like timer HAL, not AVR/peripheral emulation.

```sh
CXX=g++ sh scripts/test_firmware.sh
uv run --with fmpy==0.3.26 --with playwright python -m unittest discover -s tools -p 'test_*.py'
uv run --with playwright python tools/test_cylinder_ui.py
uv run --with fmpy==0.3.26 python tools/run_cylinder_scenarios.py
uv run --with fmpy==0.3.26 python tools/run_cylinder_transients.py --baseline-dir .cache/engine/cylinder-scenarios
pio run -d firmware -e compact_n16r8_web -e compact_a3_web -e compact_a3_timing_bench
```

The independent reviews also reproduced and drove fixes for malformed commands retaining older pending edges, failed JSON ownership, near-limit tune migration and the 85% floating-point boundary. [Feature coverage](engine-feature-coverage.md) still lists substantial control, hardware and integration gaps. No board was flashed, and no physical engine, vehicle, EMI/surge, thermal, splash or printed-fit qualification is established.
