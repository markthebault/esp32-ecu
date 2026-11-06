# Feature coverage toward Speeduino

Reference: [published features](https://speeduino.com/home/about/features), [tuning interface](https://speeduino.com/home/about/interface) and official source pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. Speeduino capability depends on board/configuration. This ledger does not claim equivalence.

**Shadow** means ESP32 calculations with physical outputs inhibited. **SIL** means host virtual events. Neither means physical engine testing.

| Capability | Firmware / simulation | Configuration, UI and debugging | PCB / remaining work |
| --- | --- | --- | --- |
| VE, spark, lambda maps | Shared 16×16 interpolation/validation; target timer source/native dispatcher | Axes/cells editable, JSON/own MSQ | Target pulse/jitter measurements pending |
| Speed-density fuel | Shared core; fuel-kernel and external-plant controller comparisons | Engine/injector settings and correction readouts | Four high-Z saturated drivers, electrical behavior unmeasured |
| Primary load sources and pressure | Independent fuel/spark MAP, physical TPS or IMAP/EMAP coordinates; optional fixed-reference/MAP/baro normalization;56 cases plus8 step checks | Introduced in schema7/own008; retained in current schema9/own010 with explicit units, review and188/145-field MSL006 | Existing J16 may supply EMAP or live baro, with calibrated absolute-kPa input; simultaneous extra pressure path and separate baro curve missing |
| AFR incorporation | Off, target and readiness/delay-gated measured/target factor, separate from EGO PI; zero ordinary fuel suppresses deadtime-only openings | AFR state/factor, restart delay, unknown ratios and legacy migration in UI/JSON/tuning/logs | External wideband remains required; these compatibility calculations do not establish target-lambda tracking or engine calibration |
| Batch/wasted four-cylinder | Shared native and ESP32 MCPWM/GPTimer executor | Explicit strategy, inhibited-output labels, timing trace | Four injector/four smart-coil commands; selected N16R8 physical policy inhibited |
| Other cylinder counts | Missing; Speeduino publishes 1–8 support | Validator rejects other counts | Channel/strategy review required |
| Full sequential four-cylinder | Shared720° phase/scheduler; strict cam-loss cut,33 external-plant cases plus6 step checks | Strategy/order/injection/cam settings, phase reasons/logs, schema migration and own003 MSQ | Existing protected Hall cam/four injector/four smart-coil commands; N16R8 physical policy inhibited |
| Selectable semi-sequential | Crank-only timed pairs, half-effective fuel plus deadtime per opening;28 coupled cases and8 step checks against timed production Speeduino | Schema5/own006, derived pairs/modulo360 UI, strict trim rejection, schema2 screens, timing/log diagnostics and offline app fixture | Four separate existing J9 drivers; pair-current overlap, actual flow/deadtime/phase and physical timing remain unqualified |
| Missing-tooth triggers | Existing generic decoder; SIL exercises 60-2 | Wheel geometry, sync/fault diagnostics | Protected Hall input, thresholds/noise unmeasured |
| Other OEM trigger patterns | Missing decoder collection | No misleading selections | Pattern-specific HIL required |
| VR crank/cam | Raw VR conditioning missing | Hall-specific guides | External conditioned module or reviewed new front end |
| Cranking fuel/spark | Shared shadow/SIL | Threshold/timing/coolant curve | Cranking voltage/noise and timing-light tests pending |
| Warmup/afterstart | Shared shadow/SIL | Curves, magnitude/duration, correction logs | Physical cold calibration pending |
| Acceleration/deceleration enrichment | Legacy decay plus acquisition-window TPS/MAP tables, multiplier/reference-adder, latched RPM/coolant taper and zero-decel fuel cut;48 coupled cases plus8 refinement and8 neutral controls | Introduced in schema6/own007; curves/gates and source-rate/phase/dose diagnostics retained in current own010 and229/186-field MSL007 | Existing protected J11/J12; real sensor noise, injector behavior and engine/film calibration remain unqualified |
| Dead-time compensation | Battery curve and pulse bounds | Curve and pulse diagnostics | Injector flow/dead-time/flyback characterization missing |
| Dwell compensation/protection | Battery curve, bounded high time, late-demand handling | Dwell/angle diagnostics, event traces | Smart coils only, no dumb-coil power driver |
| Rev limiting | Retard band, cut and hysteresis | Editable thresholds and fault logs | Target response and physical cut behavior pending |
| Overrun fuel cut | Continuous entry delay/hysteresis | Enable/limits/state logs | Active pulses finish bounded closing edges |
| Closed-loop lambda | Basic bounded PI | Gains/limits and correction logs | External wideband controller, no raw sensor heater/control |
| Idle | On/off, open-loop and closed-loop PWM with executed-edge NC valve model; 33 coupled runs/38 reference checks | Coolant/duty curves, normalized gains, gates, applied/pending PWM diagnostics, own005 files/logs and isolated wiring/debug guide | Routed A5 permanent-bias/PH4 interface and isolated THT IAC-DRAFT2; native checks, independent copper review and25 conditional circuit runs; physical output disabled; actual module/driver/pulse/brownout/valve/fit holds; stepper/H-bridge missing |
| Fuel pump / fan | Prime/hysteresis shadow proposals | Settings and status | Existing command stages, engine execution disabled |
| Boost / overboost | Missing, current profile NA only | Boost tune rejected | Solenoid driver/connector allocation needed |
| VVT | Missing | No controls | Phase sensing, driver, flyback and connector work |
| Flex fuel | Standalone portable raw-edge/window/filter/fault-ACK and six-bin correction groundwork;25 declared genuine production callback/loop cases | Not yet connected to engine Tune, browser/TS settings, logs/radio or target binding; secondary ETH dependency still needs the producer | Protected frequency input, BOOT-safe pin allocation, PCB/connector and electrical/fit qualification pending |
| Secondary maps / blending | Independent multiply/add/strict conditional/input selection, correction ordering and qualified debounce; guarded J4 acquisition;128 declared coupled cases plus20 refinements, exact neutral controls and independent review | Introduced in schema8/own009; preserved in schema9/own010, browser/TS offline editors, complete-page CAS, source-tagged832-byte runtime,229/186-field MSL007 and switch wiring/bus diagnostics | Separate routed THT SW2-J4-DRAFT1, candidate BOM, independent reviews/native checks/conditional circuit cases; actual electrical/reset/power/timing/rail/fit tests pending; target ethanol and continuous blend missing |
| Per-cylinder trims | Four6×6 fuel maps and signed spark offsets; physical-channel capacity/duty, latched coil advance;18 new plant runs | Sequential enable, browser/own005 MSQ, strict legacy migration, per-channel JSON/current229-field engine MSL and masks | Existing J9/J10 channels1–4; actual flow/deadtime/phase and electrical qualification pending |
| Flex fuel / fuel temperature | Raw-edge acquisition and coherent control corrections, zero-factor/AE/cranking/secondary ordering, fault/revision fences; host integration tested | Schema9/own010 curves/calibration, source/age/fault diagnostics,229/186-field MSL007 and raw SIL stimulus | Protected target producer and PCB input missing; enabled target flex inhibits. Screen schemas1..4 suppress engine frames when flex is required. Ethanol chemistry/physical qualification pending |
| Staged injection | Missing | No staging controls | Extra drivers and duty/flow qualification |
| Launch / flat shift / nitrous | Missing | No enable options | Protected switch/speed/pressure inputs and output allocations |
| Knock | Missing | No misleading protection indicator | Analog front end and processing required |
| Sensor calibration | Persistent linear/table/NTC with loading compensation | Guides, units, confirmation and raw diagnostics | Six analog inputs plus battery/5V; physical verification pending |
| Engine sensor binding | Confirmed physical units; raw-voltage relabelling rejected | Binding/fault status | Fast raw samples, display filter cannot hide faults |
| Supervision/recovery | Target independent command/producer/tooth/cam/high-time deadlines, transactional scheduling and configuration holds | Reasons/counters/bounded traces/revisions/storage | Target timing/watchdog/restart policy needs physical HIL |
| TunerStudio offline | Own definition/MSQ exchange | Own0108192-byte complete-page settings/curve/map editing, origin metadata and stale-editor CAS | Actual offline application roundtrip; target USB hardware unmeasured |
| TunerStudio online | Shared C++ whole-tune transport and dedicated inhibited USB service | Fresh own009 rejection after valid discovery; genuine production-reference online read/edit/burn/MSQ positive control; stream-aware capture tools and independent review | Supported own-identity integration unresolved; physical USB/load/cache/timing tests pending |
| MegaLogViewer HD | SIL, raw-trigger and bounded target engine MSL; actual application opens/plots browser engine/trigger exports | Source/loss/age/validity labels, collected versus retained downloads; derived missing-lambda display caveat | Physical target capture/logging behavior unmeasured |
| Tooth/composite/ignition logging | Target finite512-edge crank/cam recorder, raw intervals and128-record output/cut ring | Trigger charts/zoom, JSON/MSL export, bounded paging and fault counts; no TS high-speed logger | Independent capture channels implemented; capture integrity/per-pin timing need HIL |
| Autotune / VE Analyze Live | Missing | No button implies working autotune | Integration, calibrated data and suitable license |
| ESP-NOW screens | Existing authenticated read-only sensor telemetry | Button/UI pair, approve/unpair, LED | Sealed buttons/LED fit remains provisional |
| New engine telemetry to screens | Opt-in authenticated232/250-byte negotiated schemas1..4; coherent inputs/proposals/phase/worker and compact load/secondary meanings; timed nonce recovery and64-bit sequences | Negotiated schema/source-age diagnostics; Python receiver and clock/replay/queue tests; legacy stream retained | Actual two-device/RF/load testing and screen implementation pending |
| Target engine data logging | Bounded128-row fixed RAM ring, absolute sampling and final loss accounting | Period/duration controls, paged browser collection, gap disclosures, JSON/MSL and retained-window export | Runtime load, minimum heap, stack high-water and physical data integrity tests pending |
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

[USB tuning](engine-usb-tuning.md) covers the current shared own010 codec, dedicated target transport, offline file workflow, diagnostics and unresolved online application gate.

[Idle evidence](engine-idle-control.md) extends the software/control comparison and exposes remaining hardware release blockers. It does not close other control, OEM trigger, cylinder-count, online-vendor or physical-qualification gaps.

[Isolated idle hardware](engine-idle-isolation.md) records the routed carrier/accessory, independent review corrections and conditional return/brownout/pulse circuit experiments.

[Selectable semi-sequential](engine-semi-sequential.md) introduced the schema5/own006 configuration and schema2 screen contract. Historical per-feature identities and evidence above remain records; that evidence used own006; current exports use own010. This increment does not establish broader Speeduino parity or physical engine operation.

[Transient fueling](engine-transient-enrichment.md) adds schema6/own007 while preserving legacy AE behavior and the first256 runtime bytes. This increment closes the basic TPS/MAP rate-table gap in software and UI; it does not establish wall-film calibration, online vendor acceptance or physical ECU equivalence.

[Load, pressure and AFR](engine-load-model.md) records the schema7/own008 increment. It includes independent source/unit choices, source-tagged logs and schema3 screens,64 declared primary/refinement runs,8 exact legacy replays, independent reviews and actual offline app checks. This does not close secondary tables, a separate baro correction curve or the wider engine/hardware qualification gaps.

[Secondary-table development integration](engine-secondary-tables.md) introduced schema8/own009 configuration, browser/TunerStudio offline editors, expanded logs/diagnostics and schema4 screens. Guarded target switch acquisition and a separate routed THT accessory draft have independent software/circuit reviews and native checks. [Enabled-table plant experiments](engine-secondary-plant.md) add actual controller-loop comparison, fault delivery, neutral/negative controls and independent simulator review. Physical acquisition/protection/fit, target ethanol and wider parity remain open.

[Flex development integration](engine-flex-fuel.md) now connects the raw-edge core to controller arithmetic, schema9/own010 configuration, browser calibration/import/debugging and MSL007. Independent kernel review includes14,400 bit-exact Off samples and enabled/fault probes;27 fixed-gasoline plant cases include exact neutral causal controls. The earlier25-case pinned production raw-edge comparison packet remains historical. Protected target capture, PCB, negotiated flex radio semantics, ethanol chemistry and physical qualification remain open.
