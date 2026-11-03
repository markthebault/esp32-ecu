# Feature coverage toward Speeduino

Reference: [published features](https://speeduino.com/home/about/features), [tuning interface](https://speeduino.com/home/about/interface) and official source pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. Speeduino capability depends on board/configuration. This ledger does not claim equivalence.

**Shadow** means ESP32 calculations with physical outputs inhibited. **SIL** means host virtual events. Neither means physical engine testing.

| Capability | Firmware / simulation | Configuration, UI and debugging | PCB / remaining work |
| --- | --- | --- | --- |
| VE, spark, lambda maps | Shared 16×16 interpolation/validation; target timer source/native dispatcher | Axes/cells editable, JSON/own MSQ | Target pulse/jitter measurements pending |
| Speed-density fuel | Shared core; fuel-kernel and external-plant controller comparisons | Engine/injector settings and correction readouts | Four high-Z saturated drivers, electrical behavior unmeasured |
| Batch/wasted four-cylinder | Shared native and ESP32 MCPWM/GPTimer executor | Explicit fixed strategy, inhibited-output labels, timing trace | Four injector/four smart-coil commands; selected N16R8 physical policy inhibited |
| Other cylinder counts | Missing; Speeduino publishes 1–8 support | Validator rejects other counts | Channel/strategy review required |
| Sequential/semi-sequential | Missing 720-degree cam phase/scheduler | No enable option | Cam capture exists but does not establish phase |
| Missing-tooth triggers | Existing generic decoder; SIL exercises 60-2 | Wheel geometry, sync/fault diagnostics | Protected Hall input, thresholds/noise unmeasured |
| Other OEM trigger patterns | Missing decoder collection | No misleading selections | Pattern-specific HIL required |
| VR crank/cam | Raw VR conditioning missing | Hall-specific guides | External conditioned module or reviewed new front end |
| Cranking fuel/spark | Shared shadow/SIL | Threshold/timing/coolant curve | Cranking voltage/noise and timing-light tests pending |
| Warmup/afterstart | Shared shadow/SIL | Curves, magnitude/duration, correction logs | Physical cold calibration pending |
| Acceleration enrichment | Basic decaying TPS-rate model | Threshold/gain/decay and logs | Wall-film/MAP-rate/per-engine tuning remain |
| Dead-time compensation | Battery curve and pulse bounds | Curve and pulse diagnostics | Injector flow/dead-time/flyback characterization missing |
| Dwell compensation/protection | Battery curve, bounded high time, late-demand handling | Dwell/angle diagnostics, event traces | Smart coils only, no dumb-coil power driver |
| Rev limiting | Retard band, cut and hysteresis | Editable thresholds and fault logs | Target response and physical cut behavior pending |
| Overrun fuel cut | Continuous entry delay/hysteresis | Enable/limits/state logs | Active pulses finish bounded closing edges |
| Closed-loop lambda | Basic bounded PI | Gains/limits and correction logs | External wideband controller, no raw sensor heater/control |
| Idle | Virtual PI only | Target/gains labelled virtual | No qualified PWM idle driver or stepper H-bridge |
| Fuel pump / fan | Prime/hysteresis shadow proposals | Settings and status | Existing command stages, engine execution disabled |
| Boost / overboost | Missing, current profile NA only | Boost tune rejected | Solenoid driver/connector allocation needed |
| VVT | Missing | No controls | Phase sensing, driver, flyback and connector work |
| Flex fuel | Missing | No ethanol blending/capture settings | Protected frequency input/pin allocation needed |
| Secondary maps / blending | Missing | One map set | Switch input or authenticated strategy needed |
| Per-cylinder trims | Missing | No trim controls | Phase/channel semantics and tests needed |
| Staged injection | Missing | No staging controls | Extra drivers and duty/flow qualification |
| Launch / flat shift / nitrous | Missing | No enable options | Protected switch/speed/pressure inputs and output allocations |
| Knock | Missing | No misleading protection indicator | Analog front end and processing required |
| Sensor calibration | Persistent linear/table/NTC with loading compensation | Guides, units, confirmation and raw diagnostics | Six analog inputs plus battery/5V; physical verification pending |
| Engine sensor binding | Confirmed physical units; raw-voltage relabelling rejected | Binding/fault status | Fast raw samples, display filter cannot hide faults |
| Supervision/recovery | Target independent command/producer/tooth/high-time deadlines, transactional scheduling and configuration holds | Reasons/counters/bounded traces/revisions/storage | Target timing/watchdog/restart policy needs physical HIL |
| TunerStudio offline | Own definition/MSQ exchange | Settings/curve/map editors, strict identity/revision import | Files only, no physical binary transport |
| TunerStudio online | Local MS-envelope prototype | Wire read/write/burn tests; app rejects own identity | Vendor integration and dedicated transport required |
| MegaLogViewer HD | MSL export, actual application opens/plots | Labelled simulation log download | Real target logging not implemented |
| Tooth/composite/ignition logging | Native full traces; target 128-record edge/cut ring | Timing JSON export, faults/overwrite counts; no TS high-speed logger | Dispatcher timestamps implemented; raw composite/per-pin measurements remain |
| Autotune / VE Analyze Live | Missing | No button implies working autotune | Integration, calibrated data and suitable license |
| ESP-NOW screens | Existing authenticated read-only sensor telemetry | Button/UI pair, approve/unpair, LED | Sealed buttons/LED fit remains provisional |
| New engine telemetry to screens | New engine-specific schema missing | Current protocol is sensor-monitor telemetry | Versioned receiver compatibility work |
| Hand assembly / enclosure | A3 sources and A4 fit draft retained | Existing build/manual/guides | Module geometry, antenna RF and sealed fit checks pending |
| External engine benchmark | Verified MVEM air path, pulse-driven empirical combustion/free shaft; production Speeduino loop compared | Declared neutral profiles, edge/ledger/fault logs, step convergence | Uncalibrated research plant; native HAL is not target/HIL qualification |
| Vehicle electrical/environment | Not established | Software never implies qualification | Surge/EMI/current/thermal/splash/fit tests undone |

## Hardware sequence

1. Preserve A3/A4 manufacturing records. Define a future carrier against an explicit engine/channel/trigger contract before routing.
2. Prove Hall, ADC, injector and smart-coil paths on dummy loads, with captured supply/watchdog/interlock/reset behavior. Measure the actual N16R8 socket and antenna geometry.
3. Add agreed protected inputs/drivers together with firmware, configuration, UI guides and fault tests. Idle stepper, VR, boost and VVT need real hardware work.
4. Preserve the 120×120 mm limit, ordinary iron assembly, leaded parts, pluggable ESP32 and direct-solder DIP preferences. Use reviewed modules where necessary.
5. Release new Gerbers/case/BOM only with matching electrical contracts and fresh native CAD checks. This increment does not update or qualify those artifacts.

DBW/OEM integration remain outside the current bench scope.

[External benchmark scope, configuration and reproduction](engine-research-benchmark.md) keeps simulator coverage separate from missing physical and control features.

[Target timing implementation and evidence](engine-target-timing.md) describes the selected build's inhibited policy, native dispatcher comparison and outstanding physical tests.
