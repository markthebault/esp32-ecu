# Engine development and simulation

This development branch moves toward Speeduino feature coverage. The project remains an inhibited bench monitor. No tune, MSQ, API or button enables physical engine outputs. A3 manufacturing records and the A4 N16R8 fit draft are unchanged.

The shared C++ core computes four-cylinder, four-stroke batch/wasted or [cam-synchronized sequential fuel and spark](engine-sequential.md). The ESP32 now has a [MCPWM/GPTimer timing executor](engine-target-timing.md), with virtual outputs in the selected N16R8 build. Its shared dispatcher also runs on the external research plant through a native ABI. Physical target timing remains unmeasured. The old constant-speed revolution planner is a diagnostic helper.

[Feature coverage](engine-feature-coverage.md) distinguishes implemented software from missing features and hardware. This is not full ECU parity.

## Build and run

The pinned PlatformIO ESP-IDF framework supplies cJSON for native builds. A C/C++ compiler and Python 3 are required.

```sh
pio run -d firmware -e compact_n16r8_web
CXX=g++ sh scripts/test_firmware.sh
python3 tools/test_web_config.py
python3 tools/test_radio.py
python3 tools/test_engine.py
python3 tools/test_engine_http.py
python3 tools/run_engine_scenarios.py
python3 tools/web_server.py --port 8765 --tuner-port 29000 --tuner-pty .cache/engine/shared-tuner-serial
```

Use free ports and a new PTY path. Optional local tuning endpoints share the web simulator's in-process engine store. A standalone tuning server has its own store. Two processes must not write the same state file. These host transports do not attach to physical serial ports or GPIO. The selected web firmware also has a separate [native USB tuning service](engine-usb-tuning.md); online TunerStudio still rejects our own controller identity.

Open `http://127.0.0.1:8765` and select **Engine development**. Settings, coolant/battery curves, all three16×16 maps and sequential [individual cylinder trims](engine-cylinder-trims.md) are editable. Host and ESP32 use the same C++ tune validator. Engine storage/revision is separate from sensor profiles. Conflicting writers must reload. Malformed documents returned by storage block application writes. Host files are retained on validation failure; the application never asks NVS to erase a partition. NVS recovery may discard physically damaged entries, so raw corrupt flash preservation is not guaranteed.

Engine tunes use bounded 24 KiB blobs in a dedicated 64 KiB NVS partition at 0x210000. This fixes ESP-IDF's 4000-byte string ceiling without moving existing sensor/pairing NVS, PHY or factory-app offsets. Valid legacy engine strings are copied read-only and retained. Persistence errors block further engine saves until restart/inspection; volatile tune state changes only after success. Upload the matching partition table with firmware. API-model tests exercise caller behavior, not physical flash wear or power-loss recovery.

The host runs warm/cold starts, throttle/load changes, trigger dropout, MAP short, overrev and stall/restart scenarios. Its normal sensor dashboard is independently labelled synthetic. SIL results are completed historical runs, not live hardware measurements.

## Implementation and limits

The core implements speed-density mass/flow fuelling, bilinear/clamped maps, cranking timing/enrichment, warmup, afterstart, decaying TPS acceleration enrichment, battery dead-time/dwell curves, rev retard/cut hysteresis, delayed overrun cut, bounded lambda PI, virtual idle PI, fan hysteresis and pump prime proposals.

MAP/TPS/CLT/IAT require confirmed physical conversions in kPa, %, C or °C. Relabelling raw voltage is rejected. Lambda feedback needs a confirmed lambda conversion and external wideband controller. Fast raw samples feed the core; display smoothing cannot hide an electrical fault.

The shared scheduler updates deadlines per decoded tooth and latches advance at dwell start. Injector close deadlines remain fixed. An unachievable late advance change retains the committed full-dwell firing for that cycle. Reports separately measure angle error to the latched event and newest demand. Selective cuts suppress new starts and retain active closing edges. Fault/stale cuts emit explicit global-low trace events. Injector high time is capped at 15 ms and coil high time at 3.5 ms.

A protected stall can recover in SIL only after at least 150 ms without raw crank or cam edges, fresh valid decoder-derived stopped samples, acknowledged virtual outputs low, and a further continuous 20 ms interval. Invalid/stale samples, activity and control gaps restart the interval. Stop reasons/counters survive recovery. This is absence-of-signal logic, not proof that a physical rotor is stationary; target restart policy needs HIL review.

Defaults describe an illustrative 2 L, four-cylinder, 300 cc/min model. They are not a physical engine base tune. This profile is naturally aspirated, limited to 8000 RPM. Batch/wasted is the default; sequential operation requires the explicit cam/timing configuration and retains all pulse limits.

## Simulator assessment

The regression plant models throttle/manifold flow, independent VE/injector/rotor parameters, pulse-derived fuel, cold/warm wall film, generic coil charge energy, combustion work and shaft dynamics. RPM is an outcome rather than a prerecorded trace. Seeded variations expose fragile defaults. Coefficients are uncalibrated. Use it for software regressions, not power, knock, mixture-safety or emissions predictions.

Ange Yaghi's [Engine Simulator](https://github.com/ange-yaghi/engine-sim) targets audio/response and explicitly disclaims engineering/tuning accuracy. Its stock fuel/ignition interfaces also need adaptation.

The external [Modelica-MVEM research library](https://github.com/modelica-3rdparty/Modelica-MVEM) now runs in pinned OpenModelica on this mini:

```sh
docker pull openmodelica/openmodelica@sha256:ac9a0223e69b8055d444b42f58ccb9680342b56848c68b81385bf83d7c0ba824
python3 scripts/probe_engine_modelica.py
```

The script uses the existing Docker service, task cache mounts and no published ports. [Feasibility results](../reports/engine/modelica-feasibility.json) retain initialization, unit and species-mass warnings. Stock examples force speed and calculate fuel internally; one turbo example also develops pressure far outside our NA range. They do not demonstrate either ECU controlling that stock engine.

A separate [external research benchmark](engine-research-benchmark.md) now reuses verified, unchanged air-path components through FMI/CVODE and adds explicit local pulse-driven fuel/combustion/free-shaft states. It runs both controller implementations against independent copies of the same constrained NA plant. Its combustion and actuator assumptions remain empirical and uncalibrated; calibration is still required.

The peer-reviewed [TCSI testbed](https://github.com/nkymark/TCSISimTestbed), a 1.8 L turbo SI model, is another candidate: Ng et al., IEEE Control Systems Magazine 40(2), 2020, [DOI 10.1109/MCS.2019.2961793](https://doi.org/10.1109/MCS.2019.2961793). It requires MATLAB/Simulink and adaptation of stock speed/AFR inputs. MATLAB/Simulink is not installed here. No commercial simulator/tuning license has been purchased.

## Speeduino comparison

Official [Speeduino source](https://github.com/speeduino/speeduino), adjacent `../speeduino`, is pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`.

```sh
cd ../speeduino
pio test -e native_code_coverage -f test_fuel -f test_tables
cd ../esp32-ecu
python3 scripts/build_speeduino_reference.py
python3 tools/compare_speeduino.py
```

The adapter links actual production Speeduino objects. Its upstream native fuel/table tests pass 236 cases. The [75-case comparison](../reports/engine/speeduino-fuel-comparison.json) covers steady-state batch fuel under explicitly mapped required-fuel, MAP, dead-time and correction settings, including documented integer quantization.

That original 75-case comparison covers the fuel kernel only. The new [full controller-source comparison](engine-research-benchmark.md) executes Speeduino's production loop/decoder/schedulers and our shared portable core/decoder/scheduler with virtual edges, startup, transients and faults. Native execution does not validate either target's physical ISR timing. No formula clone is presented as Speeduino. External GPL source stays in its own checkout; linked executables are not distributed here.

## Evidence, tuning and reviews

[Validation summary](../reports/engine/validation-summary.json) records commands/counts, source hashes, firmware build and qualification limits. [Plots](../reports/engine/first-increment-charts.html) show a SIL restart and the limited fuel-kernel comparison. [Storage review](../reports/engine/independent-storage-review.md) covers the new partition/blob path.

[Tuning interoperability](../tuning/README.md) covers own-signature MSQ exchange, MSL logs, desktop checks and the current live-connection limitation. Speeduino/MegaSquirt tunes are incompatible and rejected.

Independent reviews found and drove fixes for synchronization/bench arming, whole-revolution timing drift, phase-wrap skipped firings, stale command events, lost closing edges, trace truncation, late advance updates, physical-unit binding, enrichment state, asynchronous UI navigation, build-cache dependencies, stopped-state recovery and stale-client tune overwrites. The [scheduler recheck](../reports/engine/independent-scheduler-review.md) and [stall/interoperability review](../reports/engine/independent-stall-interop-review.md) record reproductions.

Before engine actuation, required work includes physical target timer/ISR measurements under Wi-Fi/ESP-NOW/flash load, HIL fault/restart validation, calibrated plant and remaining feature comparisons, crank/cam/ADC HIL, electrically measured dummy loads, driver energy/thermal tests, module/carrier fit and physical power/wiring/EMI/surge/environment testing. CAD, SIL and compilation do not qualify a car, printed fit or enclosure splash resistance.

The [semi-sequential increment](engine-semi-sequential.md) adds the current schema5/own006 strategy and negotiated engine-radio schema2. Earlier identities/evidence described here remain historical records; byte offsets, CAS, bounded logging and selected physical-output inhibition are retained.
