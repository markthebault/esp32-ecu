# Idle air control and comparison

The shared core implements on/off, PWM open-loop and closed-loop idle with feedforward, coolant target addition, crank/run taper, throttle/RPM entry hysteresis, dashpot, filtered derivative, duty slew and bounded anti-windup. The default master enable is off. The selected ESP32 remains an inhibited monitor; this increment establishes software and an explicitly unrouted hardware draft, not full Speeduino or physical-engine qualification.

## Configuration and diagnostics

Use **Engine development → Idle air control**. The base target and normalized P/I gains live in the existing settings. `idle_control` adds mode, 50–250 Hz PWM, 10–250 ms PID period, limits/gates and six-point coolant curves for running duty, cranking duty and target RPM addition. Duty is energized percentage. P uses percentage points/RPM; I uses percentage points/(RPM·s); D acts on measured RPM in percentage points·s/RPM. These are not Speeduino's raw gains. The on/off mode uses 0/100% and requires a 100% maximum. The C++ validator checks inactive configurations as well.

Only fresh, valid sensor data and a valid running/cranking context permit idle demand. TPS must first be observed at or below the closed threshold before its exit hysteresis applies. Stop, open throttle, overrun cut and faults close the command immediately. Normal running slew cannot delay a safety cut or a reduced hard maximum. Partial anti-windup admits reachable integral progress instead of freezing the integrator when one update exceeds slew/headroom. A save resets controller state and execution context; it is not seamless hot tuning.

The UI distinguishes target/feedforward/P/I/D and proposed duty from the cycle-latched PWM command, pending identity, high time, fault and lateness. Completed host observations label valve current/opening synthetic. The target's timing API exposes idle dispatcher counters separately from the eight-bit injector/coil masks. Its existing edge ring contains engine channels; native simulation records idle as channel 8. No status field proves a GPIO voltage or physical valve position.

The common GPTimer owner executes integer PWM under the existing safety lock. Commands expire at 20 ms before a new heartbeat can rescue them; excessive interrupt lateness, time reversal or output failure cuts the output. Partial duty latches at cycle boundaries; 0% closes immediately and 100% stays high only under supervision. Recovery needs fresh explicit stopped zeros for 20 ms, with crank/cam quiet for over 150 ms. Repeated already-low stop commands preserve that continuity. Only the executor's accepted, effective command can enable idle, including phase-context checks. A native no-edge timer notification advances a constant output without inventing a GPIO transition.

The battery check uses the board's existing battery observation as a proxy, not a measurement of the separately switched valve branch. There is no actuator feedback. A disconnected or stuck valve therefore changes simulated airflow/RPM without magically creating an ECU fault.

## Storage, tuning and logs

Engine JSON schema 4 adds `idle_control`. Exact schema 1/2/3 documents migrate with fixed idle defaults and the former virtual-idle enable cleared, preserving their stored bytes/revision until Save. Supported cylinder trims remain intact. [Schema 3 defaults](../config/engine/defaults-v3.json) and historical INIs/MSQs remain records.

Use [esp32-ecu-idle.ini](../tuning/esp32-ecu-idle.ini), signature `ESP32ECU DEV 005 INHIBITED`. One 4992-byte page preserves offsets 0..4767, appends algorithm at 4768, 18 floats at 4772..4843 and four 6-float arrays at 4844..4939, with 52 reserved zero bytes. The field order is explicit and independent of JSON insertion order. All seven map editors reference page 1. The 256-byte runtime block preserves the 216-byte prefix and adds six idle floats and four status words. `iacFlags` bit 8 and `iacAvailable` indicate availability; source and age are separate logged channels. Serial discovery remains 002.

Own005 offline files retain the same stable-origin/CAS semantics as own004. Legacy own001..004 imports disable the new idle path and cannot inherit enabled/custom idle parameters from the editor. Current files can omit the application's read-only origin; the browser retains its loaded CAS revision. Native validation/persistence remain whole-tune and atomic.

Actual TunerStudio MS Lite 3.3.01 read the definition, displayed the idle curves and spark map, and saved frequency 80→90 Hz, mode closed-loop→open-loop and running duty at 70°C from 17→17.01%. The [application-authored fixture](../tuning/examples/tunerstudio-idle-roundtrip.msq) imports through native and Chrome paths. TunerStudio online acceptance remains blocked by the previously observed own-identity gate; no vendor message was sent.

`ESP32ECU ENGINE LOG 003` preserves the 79-field prefix and appends 12 idle fields, including `IdleAvailable`, for 91 total. Unavailable numbers are null/NaN. The fixed 256-row recorder is 84,056 bytes, its copied 16-row page 5,336 bytes and each runtime sample 312 bytes on the native ABI; final target static budgets are recorded separately. The direct `ESP32ECU SIL 003` export preserves its 19-field prefix and appends controller, PWM and model data for 48 fields. Actual MegaLogViewer HD Lite 4.6.14 opens/plots both. Spot-sampled current can alias PWM; large numeric IDs may lose precision inside a viewer, while source files and JSON preserve integer text. The 232-byte ESP-NOW schema remains unchanged and carries the base idle proposal only.

## Independent plant and reference

[Evidence](../reports/engine/idle-control/) includes 33 coupled runs, 38 reference PWM checks, raw edges, application files, native/Chrome tests, three firmware builds and independent reviews. Both real controller cores drive separate copies of the same hash-verified external Modelica MVEM air path, local empirical combustion/free shaft and independently specified NC valve. The valve uses 8 Ω, 12 mH, 0.7 V flyback, a 60 ms mechanical pole and fixed current-squared opening thresholds. Executed GPIO edges drive it; direct proposed-duty shortcuts are rejected. Current and mechanical opening decay after a cut. The electrical ledger balances source, copper, diode and stored inductive energy; it does not validate electromechanical energy conservation or a real valve.

Pinned Speeduino production idle/PID/decoder/scheduler code is unchanged. Its native HAL now aligns PWM conversion with an explicit 4 µs auxiliary tick, or 16 µs in the 16-bit profile; engine timers remain 4 µs. A declared initialization profile seeds the first idle compare once at counter+1. Unseeded controls are retained. This models neither AVR startup registers nor CPU/interrupt execution cost. Normalized gains map to actual raw integer counts; production update cadence, rounding and gating differences remain visible.

Checks cover 0/1/50/99/100% at 50/100/250 Hz, both timer widths, seeded/unseeded start, cold/warm starts, load, throttle return, sensor/trigger loss, supervised restart, missing integral, open-loop control, disconnected/stuck valves, logical drive inversion and a 125 µs/250 µs sensitivity check. That refinement also changes the reference's main-loop cadence, so it is not an isolated solver-convergence claim. Logical inversion is not the same as swapping ordinary coil leads.

The comparison preserves an upstream discrepancy: `disableIdle()` omits PWM_OLCL, allowing timer activity after reported duty becomes zero. Both independent probes and a 50 ms post-halt timer-only window observe restarting PWM. The explicit external simulation cutoff is separate; we did not repair the reference or feed its reported duty directly to the valve.

The illustrative 900 RPM profile does not track perfectly. A disconnected/stuck-closed valve settles around 916–919 RPM at the baseline load, revealing limited downward airflow authority for that target. With an explicitly separate 1100 RPM profile and normalized P/I gains 0.06/0.06, final-second target MAE is approximately 0.7 RPM for ours and 3.7 RPM for Speeduino. These are model results, not physical base tunes or a claim that one ECU is generally better.

## Hardware and reproduction

The [THT accessory](../hardware/idle-accessory/README.md) supplies a reviewed pin/net contract and candidate BOM. It remains unrouted. Permanent carrier-side GPIO3 bias/eFuse verification, an alternate-return fault path, power/valve characterization, routing and physical fit remain release blockers. No shipped environment drives idle GPIO, and no board was flashed.

```sh
python3 scripts/generate_tuning_wire.py
python3 scripts/generate_tunerstudio_ini.py
python3 scripts/generate_idle_ui.py
python3 scripts/embed_web.py
CXX=g++ sh scripts/test_firmware.sh
uv run --with playwright --with fmpy==0.3.26 python -m unittest discover -s tools -p 'test_*.py'
uv run --with playwright python tools/test_idle_ui.py --report-dir NEW_UI_DIRECTORY
python3 scripts/build_speeduino_sim.py
python3 scripts/build_speeduino_sim.py --timer-bits 16
uv run --with fmpy==0.3.26 python tools/run_idle_scenarios.py --report-dir NEW_MATRIX_DIRECTORY
uv run --with fmpy==0.3.26 python tools/run_idle_followups.py --report-dir NEW_FOLLOWUP_DIRECTORY
pio run -d firmware -e compact_n16r8_web -e compact_a3_web -e compact_a3_timing_bench
```

Preserve published output directories. Remaining Speeduino gaps and physical qualification limits stay explicit in the [coverage ledger](engine-feature-coverage.md).
