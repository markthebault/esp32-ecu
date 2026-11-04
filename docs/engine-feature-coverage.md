# Feature coverage toward Speeduino

Reference: [published features](https://speeduino.com/home/about/features), [tuning interface](https://speeduino.com/home/about/interface) and official source pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. Speeduino capability depends on board/configuration. This ledger does not claim equivalence.

**Shadow** means ESP32 calculations with physical outputs inhibited. **SIL** means host virtual events. Neither means physical engine testing.

| Capability | Firmware / simulation | Configuration, UI and debugging | PCB / remaining work |
| --- | --- | --- | --- |
| VE, spark, lambda maps | Shared 16×16 interpolation/validation; target timer source/native dispatcher | Axes/cells editable, JSON/own MSQ | Target pulse/jitter measurements pending |
| Speed-density fuel | Shared core; fuel-kernel and external-plant controller comparisons | Engine/injector settings and correction readouts | Four high-Z saturated drivers, electrical behavior unmeasured |
| Batch/wasted four-cylinder | Shared native and ESP32 MCPWM/GPTimer executor | Explicit strategy, inhibited-output labels, timing trace | Four injector/four smart-coil commands; selected N16R8 physical policy inhibited |
| Other cylinder counts | Missing; Speeduino publishes 1–8 support | Validator rejects other counts | Channel/strategy review required |
| Full sequential four-cylinder | Shared720° phase/scheduler; strict cam-loss cut,33 external-plant cases plus6 step checks | Strategy/order/injection/cam settings, phase reasons/logs, schema migration and own003 MSQ | Existing protected Hall cam/four injector/four smart-coil commands; N16R8 physical policy inhibited |
| Selectable semi-sequential | Missing as a separate selectable strategy | No misleading option | Strategy-specific timing/HIL remains |
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
| Idle | On/off, open-loop and closed-loop PWM with executed-edge NC valve model; 33 coupled runs/38 reference checks | Coolant/duty curves, normalized gains, gates, applied/pending PWM diagnostics, own005 files/logs and isolated wiring/debug guide | Routed A5 permanent-bias/PH4 interface and isolated THT IAC-DRAFT2; native checks, independent copper review and25 conditional circuit runs; physical output disabled; actual module/driver/pulse/brownout/valve/fit holds; stepper/H-bridge missing |
| Fuel pump / fan | Prime/hysteresis shadow proposals | Settings and status | Existing command stages, engine execution disabled |
| Boost / overboost | Missing, current profile NA only | Boost tune rejected | Solenoid driver/connector allocation needed |
| VVT | Missing | No controls | Phase sensing, driver, flyback and connector work |
| Flex fuel | Missing | No ethanol blending/capture settings | Protected frequency input/pin allocation needed |
| Secondary maps / blending | Missing | One map set | Switch input or authenticated strategy needed |
| Per-cylinder trims | Four6×6 fuel maps and signed spark offsets; physical-channel capacity/duty, latched coil advance;18 new plant runs | Sequential enable, browser/own005 MSQ, strict legacy migration, per-channel JSON/91-field MSL and masks | Existing J9/J10 channels1–4; actual flow/deadtime/phase and electrical qualification pending |
| Staged injection | Missing | No staging controls | Extra drivers and duty/flow qualification |
| Launch / flat shift / nitrous | Missing | No enable options | Protected switch/speed/pressure inputs and output allocations |
| Knock | Missing | No misleading protection indicator | Analog front end and processing required |
| Sensor calibration | Persistent linear/table/NTC with loading compensation | Guides, units, confirmation and raw diagnostics | Six analog inputs plus battery/5V; physical verification pending |
| Engine sensor binding | Confirmed physical units; raw-voltage relabelling rejected | Binding/fault status | Fast raw samples, display filter cannot hide faults |
| Supervision/recovery | Target independent command/producer/tooth/cam/high-time deadlines, transactional scheduling and configuration holds | Reasons/counters/bounded traces/revisions/storage | Target timing/watchdog/restart policy needs physical HIL |
| TunerStudio offline | Own definition/MSQ exchange | Own005 complete-page settings/curve/map editing, origin metadata and stale-editor CAS | Actual offline application roundtrip; target USB hardware unmeasured |
| TunerStudio online | Shared C++ whole-tune transport and dedicated inhibited USB service | Authenticated tuning diagnostics; bounded framing/CAS/storage tests; app rejects own identity | Vendor integration unresolved; physical USB/load/cache/timing tests pending |
| MegaLogViewer HD | SIL, raw-trigger and bounded target engine MSL; actual application opens/plots browser engine/trigger exports | Source/loss/age/validity labels, collected versus retained downloads; derived missing-lambda display caveat | Physical target capture/logging behavior unmeasured |
| Tooth/composite/ignition logging | Target finite512-edge crank/cam recorder, raw intervals and128-record output/cut ring | Trigger charts/zoom, JSON/MSL export, bounded paging and fault counts; no TS high-speed logger | Independent capture channels implemented; capture integrity/per-pin timing need HIL |
| Autotune / VE Analyze Live | Missing | No button implies working autotune | Integration, calibrated data and suitable license |
| ESP-NOW screens | Existing authenticated read-only sensor telemetry | Button/UI pair, approve/unpair, LED | Sealed buttons/LED fit remains provisional |
| New engine telemetry to screens | Opt-in232-byte authenticated schema, coherent inputs/proposals/phase/worker observations, timed nonce recovery and64-bit sequences | Negotiated schema/source-age diagnostics; Python receiver and clock/replay/queue tests; legacy stream retained | Actual two-device/RF/load testing and screen implementation pending |
| Target engine data logging | Bounded256-row fixed RAM ring, absolute sampling and final loss accounting | Period/duration controls, paged browser collection, gap disclosures, JSON/MSL and retained-window export | Runtime load, minimum heap, stack high-water and physical data integrity tests pending |
| Hand assembly / enclosure | A3 sources, A4 fit and A5 idle drafts retained | Existing manual plus new back-assembly/insulation/harness guide | Module geometry, antenna RF, new header/accessory clearance and sealed fit checks pending |
| External engine benchmark | Verified MVEM air path, pulse-driven empirical combustion/free shaft; production Speeduino loop compared | Declared neutral profiles, edge/ledger/fault logs, step convergence | Uncalibrated research plant; native HAL is not target/HIL qualification |
| Vehicle electrical/environment | Not established | Software never implies qualification | Surge/EMI/current/thermal/splash/fit tests undone |

## Hardware sequence

1. Preserve A3/A4 manufacturing records. A5 defines a separate idle interface; it has no fabrication release. Define each later carrier increment against an explicit engine/channel/trigger contract before routing.
2. Prove Hall, ADC, injector and smart-coil paths on dummy loads, with captured supply/watchdog/interlock/reset behavior. Measure the actual N16R8 socket and antenna geometry.
3. Add agreed protected inputs/drivers together with firmware, configuration, UI guides and fault tests. Idle stepper, VR, boost and VVT need real hardware work.
4. Preserve the 120×120 mm limit, ordinary iron assembly, leaded parts, pluggable ESP32 and direct-solder DIP preferences. Use reviewed modules where necessary.
5. Release new Gerbers/case/BOM only with matching electrical contracts and fresh native CAD checks. This increment does not update or qualify those artifacts.

DBW/OEM integration remain outside the current bench scope.

[External benchmark scope, configuration and reproduction](engine-research-benchmark.md) keeps simulator coverage separate from missing physical and control features.

[Target timing implementation and evidence](engine-target-timing.md) describes the selected build's inhibited policy, native dispatcher comparison and outstanding physical tests.

[Trigger debugging](engine-trigger-debug.md) covers raw capture, the Speeduino logger comparison and the source-labelled MegaLogViewer workflow.

[Sequential configuration, supervision and comparison](engine-sequential.md) records the latest software increment and its physical limits.

[Engine observability](engine-observability.md) covers coherent samples, target RAM logging, browser collection and the [opt-in screen protocol](espnow-engine.md), with independent review findings and declared clock assumptions.

[Individual cylinder tuning and comparison](engine-cylinder-trims.md) describes physical mapping, trim/deadtime semantics, migration and the current evidence.

[USB tuning](engine-usb-tuning.md) covers the shared own005 codec, dedicated target transport, offline file workflow, diagnostics and unresolved online application gate.

[Idle evidence](engine-idle-control.md) extends the software/control comparison and exposes remaining hardware release blockers. It does not close other control, OEM trigger, cylinder-count, online-vendor or physical-qualification gaps.

[Isolated idle hardware](engine-idle-isolation.md) records the routed carrier/accessory, independent review corrections and conditional return/brownout/pulse circuit experiments.
