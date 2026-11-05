# Boost control development

Boost pressure protection is now connected to the main engine, schema10 tune, browser controls, own011 binary/MSQ exchange, coherent diagnostics and a separate virtual target PWM channel. The default retains the110kPa NA guard. All physical engine outputs remain inhibited and no boost GPIO is allocated. A coupled turbo/wastegate comparison and the protected physical driver remain unfinished, so this is partial development integration, not a completed boost feature.

## Control contract

Pressure protection can run with solenoid control Off. Enabled valve modes require that protection. All pressures are absolute kPa; TPS is percent and duty is energized percent. The controller assumes increasing duty raises boost and that deenergized plumbing preserves mechanical wastegate spring control. Neither assumption is established for a purchased valve/harness.

Open loop has an8×8 RPM/TPS duty table. Closed loop has separate8×8 RPM/TPS absolute-pressure targets and RPM/absolute-target feedforward duties. Tables have explicit independent meanings. The PID uses proportional gain in %/kPa, integral gain in %/(kPa·s), derivative gain in %·s/kPa, derivative on measured MAP, a bounded integral, conditional tracking against output/rate limits, and an active-control output slew limit. Target-only changes do not create derivative kick. Numeric gains are not interchangeable with Speeduino's integer PID gains.

The pressure monitor latches a fresh qualified MAP above its cut threshold, including a known high reading beyond the declared measurement envelope. Release needs valid observations below the hysteresis threshold over the configured recovery interval. Stale/invalid/regressing clocks cannot release it. Pressure protection remains active when the valve mode is Off. Configuration, MAP, stale and clock failures request engine inhibition; normal stop/crank/overrun/throttle gates deenergize the valve. Closed loop additionally requires a qualified fixed/live barometric input. The target must exceed ambient pressure. The inactive/spool proposal defaults to zero and is an explicit setting; stop/fault paths always command zero. The whole-tune owner resets the core on configuration changes.

An opt-in nonzero inactive/spool proposal applies directly up to `max_pct`; active-control slew/minimum and active limit flags do not apply to that path. The browser labels it as direct duty below activation and explains that fault/stop paths still demand zero.

The default object is disabled. Its example maps/limits are development fixtures, not an engine tune. Enabling pressure protection makes qualified MAP required and selects an explicit110..400kPa measurement ceiling. Review sensor calibration and every fuel/spark/lambda/trim axis. Existing table cells and axes are preserved; extending the ceiling does not calibrate an engine.

## PWM and hardware architecture

The existing idle executor now has a compile-time period envelope. Its idle alias retains exactly2500..50000µs. The boost alias uses20000..100000µs for10..50Hz. Each instance owns its own sequence floor, phase, pending/applied duty, immutable20ms input/command deadline,25µs lateness bound and supervised-zero recovery. A long PWM period needs fresh commands while active. Expired commands cannot be rescued by an arriving refresh, and normal duty requests cannot clear a latched timing fault.

The [GPIO45 candidate](../hardware/boost-control/architecture.json) binds unused A6 U3.37 and preserves UART, native USB, idle GPIO3 and flex GPIO38. It proposes a permanent carrier pulldown, keyed logic header and separate buffered isolated THT solenoid accessory. It is not a schematic, routed board, connection instruction or manufacturing release. RUN loading, actuation, inductive energy, fit and hardware acceptance remain open.

Espressif identifies GPIO45 as a strapping pin affecting flash voltage unless an applicable eFuse fixes it. It becomes a normal GPIO after reset. Actual board identity and read-only strap/eFuse inspection must precede any allocation; no eFuse is burned by this work. GPIO35..37 remain unavailable with the selected octal PSRAM arrangement. [Official GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/gpio.html), [boot control](https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf) and [schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html).

## Integrated software evidence

The current tune is schema10. Own011 uses one12288-byte page and1152-byte live block, preserving every own010 field offset and keeping the old8192-byte codec/INI/layout separately. Three8×8 boost tables occupy new space. Old JSON/MSQs migrate with boost disabled. Invalid or stale whole-tune writes cannot partially activate the controller. The earlier TunerStudio online identity rejection remains unresolved; browser/native own011 file exchange is tested, but actual application acceptance of this new identity is unverified.

The target and native target dispatcher execute a separate10..50Hz virtual boost channel. The worker requires its current measured synchronization before enabling it, so a healthy command queued before sync loss cannot restart the valve. Global stops, configuration holds and timing faults deenergize it. No GPIO45 allocation or physical valve command exists. The browser shows controller proposals separately from cycle-latched dispatcher observations.

Coherent data schema2 adds a64-byte boost record with full64-bit counters. MSL008 exports245 engine-log columns and202 direct-SIL columns. Raw PID demand may exceed duty limits and remains visible; applied duty remains bounded. Legacy schema1 samples and MSL007 audit fixtures remain readable. The actual native circuit/control bridge passes six replay combinations with independent245-column auditing and96 corrupted boost-column negative controls. This does not repeat or extend the physical/circuit qualification claims of the previous supply study.

Engine JSON remains bounded at48KiB in the unchanged128KiB NVS partition at0x210000. The conservative schema9 migration bound is47994bytes. Native Session size is12368bytes under a13KiB resident budget; native RuntimeSample is728bytes and the128-row Recorder95320bytes under100KiB. These are native sizes and static target budgets, not measured target heap/stack peaks.

Independent storage review reproduced one lost blob in360 flash-error trials against the installed NVS source. The [project-local correction](../firmware/components/nvs_flash/README.ecu.md) distinguishes chunk identities during active-page duplicate recovery. Its exact49-file provenance and single modified source line are checked. The corrected source retains complete old/new values through all360 trials,800 ordinary saves at four sizes and120 nonblob/legacy-format trials. The original cut9 failure remains a negative control. Failed writes have an uncertain durable outcome; runtime retention does not promise the old flash value after reboot. This is a memory-backed source model, not physical power-cut or flash-wear qualification.

The independent core review covers4422 assertions and48000 unchanged legacy engine observations. Actual target-source tests cover shared alarms, recovery and sync-loss fencing. The first firmware attempt was rejected because an initializer-list minimum escaped into flash from the ISR path; nested binary minima fix it. Accepted firmware must pass the explicit boost-state IRAM/DRAM audit, output-inhibition and USB-ownership checks. Stopped pressure faults also request the red problem indicator, with problem priority over pairing.

Current verification and exact source snapshots are retained in [the integration packet](../reports/engine/boost-integration/). Earlier isolated-kernel/reference evidence below remains a historical groundwork result, not a coupled main-engine boost comparison.

## Production reference

`scripts/build_speeduino_boost.py` compiles only a separate input/output fixture against the attested pinned production objects. The original decoder, loop, boost/PID/protection objects, native HAL and cached numerical executable remain unchanged. The source pin is `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. Linked reference executables stay in the cache.

The fixture drives raw ADC counts and actual primary-trigger callbacks. It advances the declared native timer/loop model, exports observed PWM transitions and source-labelled status, and never assigns RPM, sync or MAP status. Its sensor map covers0..400kPa through the production calibration path. Native TPS is exported both as its raw half-percent representation and physical percent. The production boost lookup's own TPS coordinate is exported separately so unit differences cannot disappear in comparison.

The production table also has a Y-axis conversion factor of2. The pre-conversion lookup argument alone is not a physical TPS coordinate. The fixture exports that factor and the stored-axis coordinate; the four TPS-ramp probes agree in physical percent within the declared ADC/table quantization. They do not establish a doubled-TPS defect.

The generic32-bit native timer initializes its compare register to `UINT32_MAX`, so partial boost duty can report a nonzero request without an edge during the60s benchmark. The fixture explicitly initializes that channel's virtual compare register to zero. `--default-unarmed-compare` retains the original value as a negative execution control. This is an authored native timer initial condition, not proof of AVR/ESP32 startup behavior or a production Speeduino bug. Requested duty alone is never accepted as executed PWM evidence.

The pinned source uses an8×8 duty/target table, optional target feedforward, pressure activation and production engine-protection policy. Our recovery, physical units, input validity and rate-limit semantics are explicit and can differ. [Official boost manual](https://wiki.speeduino.com/en/configuration/Boost_Control) and [pinned production controller](https://github.com/speeduino/speeduino/blob/9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20/speeduino/src/controllers/boost/boostController.cpp).

## Groundwork evidence

The14 paired probes cover disabled/zero/partial/full duty, closed-loop feedforward and below-activation behavior, trigger stall, overboost, the unarmed native compare negative and four TPS ramps. The own side executes the new portable kernel/PWM with authored RPM/running observations; it does not execute the main engine controller. The reference side uses raw ADC and actual decoder/loop/PWM/protection source. Actual edges, timing, duty and absence of unintended high edges are checked separately from requested duty.

Under the declared fast native loop, the pinned controller's outer33ms and inner100ms mask gates first coincide at3300ms. Both long closed-loop probes retain this delayed target update; their full runs extend past it before checking PWM or activation. The independent reviewer reproduced the first nonzero target at exactly3300000µs with1ms observations. This is a scoped native-cadence result, not a hardware timing measurement or a general claim about other Speeduino revisions/boards.

The overboost witness also retains a policy difference: the configured reference cuts both scheduling masks while its boost-duty request remains60%; the portable core requests engine inhibition and deenergizes the valve. The current integration separately verifies main-engine cuts and virtual target ownership. These earlier paired probes still execute only the isolated own kernel; they do not establish a coupled-engine comparison.

The core passes162 ASan/UBSan assertions, and the isolated interface candidate has three contract tests, including rejection of the already allocated RGB J23 reference. The corrected candidate is J24. Independent review compares old/current idle behavior over759600 full observations, adds500281 kernel/PWM assertions, and checks actual fake-target service behavior. Fresh compact A3, N16R8 and flex-development web builds retain physical-output inhibition. Static IRAM/DRAM placement is evidence about the built image, not measured interrupt latency.

```sh
python3 -B scripts/build_speeduino_boost.py --output .cache/NEW_BOOST_REFERENCE
python3 -B tools/run_boost_groundwork.py --reference .cache/NEW_BOOST_REFERENCE/speeduino-boost-sim --output .cache/NEW_BOOST_PROBES
python3 -B tools/test_boost_architecture.py
```

The reference builder requires the existing attested pinned numerical reference described in [engine development](engine-development.md). Every output directory must be new. Earlier failed probes remain separate and are not relabelled as acceptance evidence.

## Remaining boost work

[Screen schema6](espnow-engine.md#boost-pressure-and-valve-proposal-schema6) carries the original boost decision alongside engine and flex data in three authenticated datagrams. Both extensions bind the full BASE MAC; only the complete set can publish or ACK. Bounded reassembly, original ages, repeated-source immutability and explicit stale/source decision statuses are included. Schemas1..5 withhold new boost pressure profiles with an upgrade reason; fresh sensor fallback remains separate. Previously prepared observations retain their original context and expiry. This supplies the ECU sender/reference receiver contract, with no actual screen application or RF qualification.

A pulse-driven turbo/wastegate plant must consume actual main-controller PWM edges and engine outputs, then be compared with unchanged production Speeduino under pressure faults, actuator failures and time-step refinement. The current host regression plant has no turbo/wastegate model. A passing NA scenario is not boost validation. The older14 probes above remain isolated-kernel groundwork.

The guarded GPIO45/J24 interface is still only an unrouted candidate. Protected driver design, carrier/enclosure integration and physical qualification remain open. Own011 live TunerStudio acceptance and the new MSL008 application workflow also need actual application checks.

Crank/cam acquisition, CPU/timer/ISR/flash/RF load, actuator current/energy/thermal behavior, regulated supply, plumbing, printed fit, splash resistance and vehicle/engine operation remain physically unqualified.
