# Boost control development

The portable development core is in `firmware/include/ecu/boost_control.hpp`; its dedicated supervised PWM type is in `boost_pwm.hpp`. They are not yet connected to the engine tune, target, browser UI, USB tuning, logs or screens. Existing NA pressure rejection remains110kPa and all physical engine outputs remain inhibited. This is groundwork toward the full boost feature, not a usable boost controller.

## Control contract

Pressure protection can run with solenoid control Off. Enabled valve modes require that protection. All pressures are absolute kPa; TPS is percent and duty is energized percent. The controller assumes increasing duty raises boost and that deenergized plumbing preserves mechanical wastegate spring control. Neither assumption is established for a purchased valve/harness.

Open loop has an8×8 RPM/TPS duty table. Closed loop has separate8×8 RPM/TPS absolute-pressure targets and RPM/absolute-target feedforward duties. Tables have explicit independent meanings. The PID uses proportional gain in %/kPa, integral gain in %/(kPa·s), derivative gain in %·s/kPa, derivative on measured MAP, a bounded integral, conditional tracking against output/rate limits, and an active-control output slew limit. Target-only changes do not create derivative kick. Numeric gains are not interchangeable with Speeduino's integer PID gains.

The pressure monitor latches a fresh qualified MAP above its cut threshold, including a known high reading beyond the declared measurement envelope. Release needs valid observations below the hysteresis threshold over the configured recovery interval. Stale/invalid/regressing clocks cannot release it. Pressure protection remains active when the valve mode is Off. Configuration, MAP, stale and clock failures request engine inhibition; normal stop/crank/overrun/throttle gates deenergize the valve. Closed loop additionally requires a qualified fixed/live barometric input. The target must exceed ambient pressure. The inactive/spool proposal defaults to zero and is an explicit setting; stop/fault paths always command zero. A whole-tune owner must reset the core on configuration changes.

An opt-in nonzero inactive/spool proposal applies directly up to `max_pct`; active-control slew/minimum and active limit flags do not apply to that path. This needs an explicit explanation beside its future UI setting. No current product UI exposes it.

The default object is disabled. Its example maps/limits are development fixtures, not an engine tune. The current engine cannot accept boosted MAP merely by constructing this object. Integration must introduce an explicit forced-induction pressure envelope and corresponding calibration review, rather than remove the existing NA guard globally.

## PWM and hardware architecture

The existing idle executor now has a compile-time period envelope. Its idle alias retains exactly2500..50000µs. The boost alias uses20000..100000µs for10..50Hz. Each instance owns its own sequence floor, phase, pending/applied duty, immutable20ms input/command deadline,25µs lateness bound and supervised-zero recovery. A long PWM period needs fresh commands while active. Expired commands cannot be rescued by an arriving refresh, and normal duty requests cannot clear a latched timing fault.

The [GPIO45 candidate](../hardware/boost-control/architecture.json) binds unused A6 U3.37 and preserves UART, native USB, idle GPIO3 and flex GPIO38. It proposes a permanent carrier pulldown, keyed logic header and separate buffered isolated THT solenoid accessory. It is not a schematic, routed board, connection instruction or manufacturing release. RUN loading, actuation, inductive energy, fit and hardware acceptance remain open.

Espressif identifies GPIO45 as a strapping pin affecting flash voltage unless an applicable eFuse fixes it. It becomes a normal GPIO after reset. Actual board identity and read-only strap/eFuse inspection must precede any allocation; no eFuse is burned by this work. GPIO35..37 remain unavailable with the selected octal PSRAM arrangement. [Official GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/gpio.html), [boot control](https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf) and [schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html).

## Production reference

`scripts/build_speeduino_boost.py` compiles only a separate input/output fixture against the attested pinned production objects. The original decoder, loop, boost/PID/protection objects, native HAL and cached numerical executable remain unchanged. The source pin is `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. Linked reference executables stay in the cache.

The fixture drives raw ADC counts and actual primary-trigger callbacks. It advances the declared native timer/loop model, exports observed PWM transitions and source-labelled status, and never assigns RPM, sync or MAP status. Its sensor map covers0..400kPa through the production calibration path. Native TPS is exported both as its raw half-percent representation and physical percent. The production boost lookup's own TPS coordinate is exported separately so unit differences cannot disappear in comparison.

The production table also has a Y-axis conversion factor of2. The pre-conversion lookup argument alone is not a physical TPS coordinate. The fixture exports that factor and the stored-axis coordinate; the four TPS-ramp probes agree in physical percent within the declared ADC/table quantization. They do not establish a doubled-TPS defect.

The generic32-bit native timer initializes its compare register to `UINT32_MAX`, so partial boost duty can report a nonzero request without an edge during the60s benchmark. The fixture explicitly initializes that channel's virtual compare register to zero. `--default-unarmed-compare` retains the original value as a negative execution control. This is an authored native timer initial condition, not proof of AVR/ESP32 startup behavior or a production Speeduino bug. Requested duty alone is never accepted as executed PWM evidence.

The pinned source uses an8×8 duty/target table, optional target feedforward, pressure activation and production engine-protection policy. Our recovery, physical units, input validity and rate-limit semantics are explicit and can differ. [Official boost manual](https://wiki.speeduino.com/en/configuration/Boost_Control) and [pinned production controller](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/src/controllers/boost/boostController.cpp).

## Groundwork evidence

The14 paired probes cover disabled/zero/partial/full duty, closed-loop feedforward and below-activation behavior, trigger stall, overboost, the unarmed native compare negative and four TPS ramps. The own side executes the new portable kernel/PWM with authored RPM/running observations; it does not execute the main engine controller. The reference side uses raw ADC and actual decoder/loop/PWM/protection source. Actual edges, timing, duty and absence of unintended high edges are checked separately from requested duty.

Under the declared fast native loop, the pinned controller's outer33ms and inner100ms mask gates first coincide at3300ms. Both long closed-loop probes retain this delayed target update; their full runs extend past it before checking PWM or activation. The independent reviewer reproduced the first nonzero target at exactly3300000µs with1ms observations. This is a scoped native-cadence result, not a hardware timing measurement or a general claim about other Speeduino revisions/boards.

The overboost witness also retains a policy difference: the configured reference cuts both scheduling masks while its boost-duty request remains60%; the portable core requests engine inhibition and deenergizes the valve. A future engine integration must carry that cut through its actual owner and executor. A kernel boolean alone does not establish execution.

The core passes162 ASan/UBSan assertions, and the isolated interface candidate has three contract tests, including rejection of the already allocated RGB J23 reference. The corrected candidate is J24. Independent review compares old/current idle behavior over759600 full observations, adds500281 kernel/PWM assertions, and checks actual fake-target service behavior. Fresh compact A3, N16R8 and flex-development web builds retain physical-output inhibition. Static IRAM/DRAM placement is evidence about the built image, not measured interrupt latency.

```sh
python3 -B scripts/build_speeduino_boost.py --output .cache/NEW_BOOST_REFERENCE
python3 -B tools/run_boost_groundwork.py --reference .cache/NEW_BOOST_REFERENCE/speeduino-boost-sim --output .cache/NEW_BOOST_PROBES
python3 -B tools/test_boost_architecture.py
```

The reference builder requires the existing attested pinned numerical reference described in [engine development](engine-development.md). Every output directory must be new. Earlier failed probes remain separate and are not relabelled as acceptance evidence.

## Remaining integration

The complete feature needs pressure-envelope validation, control-owner/target-PWM integration, whole-tune migration/storage/CAS, dedicated table/gain/limit controls in the browser and own TunerStudio definition, source/age/fault/applied-PWM logging and screen telemetry, guarded hardware drafts and a pulse-driven turbo/wastegate plant compared with actual production Speeduino output edges. Existing NA behavior and historical exports must remain reproducible. None of that is satisfied by the isolated kernel tests alone. The current8192-byte tune page ends at byte7968, leaving224 bytes; the three new tables alone exceed that space. Integration therefore needs an explicit new tune layout and memory/storage review, with old file/wire identities retained.

Crank/cam acquisition, CPU/timer/ISR/flash/RF load, actuator current/energy/thermal behavior, regulated supply, plumbing, printed fit, splash resistance and vehicle/engine operation remain physically unqualified.
