# Four-cylinder sequential control

The shared firmware/native core supports batch injection with wasted COP, or sequential fuel and spark for a four-stroke, even-fire, four-cylinder engine. The selected N16R8 build still compiles physical output writes out. No UI, tune or protocol command enables them.

The existing carrier already has four injector commands, four smart-coil commands and a protected Hall cam input at J18. Crank is J17. This software increment does not change the PCB, BOM, module footprint, case or manufacturing records. Their electrical, mechanical and environmental qualification remains undone.

## Configuration

Engine JSON schema2 adds `timing` and permits `strategy: sequential_4cyl`. Batch/wasted remains the default. The UI exposes strategy, firing order, injection end angle and cam reference/window, together with phase status, reason, rejection count and loss count.

| Setting | Meaning | Illustrative default |
| --- | --- | --- |
| `firing_order` | Cylinder identities in firing order, cylinder1 first; each appears once | `[1,3,4,2]` |
| `tooth1_btdc_deg` | First present crank tooth after the missing gap, degrees before cylinder1 TDC | 90 |
| `injection_end_deg` | Injector electrical closing target, degrees after that cylinder's compression TDC, modulo720 | 540 |
| `cam_sync_deg` | One rising cam edge per720 crank degrees, after cylinder1 compression TDC | 450 |
| `cam_window_deg` | Acceptance half-window in crank degrees | ±20 |

The fixed simulator engine has compression TDC at shaft90/630/270/450° for physical cylinders1/2/3/4 and a cam pulse at shaft540°, corresponding to450° after cylinder1 compression TDC. Changing the tune does not change those independent mechanical references. Other cylinder counts, uneven firing and OEM cam patterns are rejected or unimplemented.

Two consecutive cam observations720° apart establish phase. A repeatable reference wrong by360° is indistinguishable from correct calibration to this single-pulse decoder. Establish compression TDC mechanically. The simulator's deliberately wrong360° case produces wrong-stroke sparks and fails to sustain combustion; its720° oracle exposes an error a360° metric would hide.

Sequential pulse width delivers the full four-stroke fuel mass in one opening, with dead time once. Batch supplies half that mass per opening, twice per cycle. Duty uses the corresponding720°/360° interval. An initial sequential pulse is skipped if its full duration no longer fits before its closing target. Once open, its low deadline stays fixed, preserving fuel quantity during acceleration. Spark advance latches at dwell start; late advance changes retain a previously committed full-dwell event when necessary.

The15ms injector and3.5ms coil limits remain. At0°C/100kPa/200RPM, the illustrative cold enrichment can demand approximately20ms sequential injection and correctly Capacity-inhibits. Do not silently clip fuel or increase these bounds. The defaults are not a physical engine base tune; injector capacity and cold enrichment require an appropriate independently qualified engine profile.

## Phase loss and target supervision

Crank synchronization is separate from720° phase. Sequential outputs wait while acquiring phase. After acquisition, missing, extra, duplicate, out-of-window, late or unmappable cam observations inhibit and latch. There is no moving fallback to batch or wasted spark.

Crank processing is immediate. A64-entry history and one bounded pending cam handle cross-channel callback ordering through the1ms capture-processing bound. Floating-point angle calculations run in the worker, never the capture ISR. Scheduling uses a matching crank timestamp and720° tooth index, never a cam timestamp paired with a newer crank position.

The next expected cam center retains its angular-cycle identity. Each crank tooth projects that window's closing deadline from current decoded speed, with a1ms processing allowance. GPTimer enforces it independently, including while normal output proposals are cut. Expiry wins before a fresh command or deadline extension. Producer, command, tooth, maximum-high-time and late-dispatch checks remain independent.

This projection is conservative under rapid speed changes or a cam in a long missing-tooth gap. The processing allowance is not a bound on arbitrary shaft acceleration. Native ramp/ripple tests cover declared fixtures; the supported physical acceleration/noise envelope and false-inhibit rate remain unmeasured.

Configuration holds invalidate captures, phase and pending output plans. Phase evidence carries tune revision, sensor revision and execution epoch. Stale evidence waits for reacquisition. Worker publications recheck the epoch under the target lock; stale candidates cannot restore an old plan. After a fault, recovery needs both raw crank and cam quiet for150ms, fresh valid stopped samples, acknowledged all-low outputs and a further continuous20ms interval. Invalid capture callbacks also restart quiet supervision. This detects absence of input signals, not a physically stationary rotor.

## Tuning and diagnostics

Schema1 JSON loads into canonical schema2 RAM with fixed batch/default timing and its original revision. Existing files/NVS bytes remain until an explicit save. Invalid, oversized or failed migrations preserve the record and block saves. Saving increments the revision once.

The new own identity is `ESP32ECU SIL 002 INHIBITED`. Page1 keeps revision at268 and the old272-byte prefix. Added fields occupy272..291; the four pages retain their sizes. The historical76-byte output prefix is retained, with24 bytes of phase/mode diagnostics appended. [Protocol layout](../tuning/protocol-layout.json) documents it.

Use [the002 TunerStudio definition](../tuning/esp32-ecu-sequential.ini). The001 definition and genuine earlier MSQ remain historical. Exact001 MSQ import explicitly migrates to batch defaults, even from a sequential editor; foreign and future identities are rejected. Actual TunerStudio MS Lite3.3.01 loaded the002 cycle editor, changed injection end540→530.5°, saved [this MSQ](../tuning/examples/tunerstudio-sequential-roundtrip.msq), and the native validator read it back correctly. [Editor evidence](../reports/engine/sequential/tunerstudio-sequential.png) is offline. Live TunerStudio integration remains unresolved; no other ECU identity is used.

MSL logs add crank/phase status, phase requirement/loss count, cam rejection count and angular error. Host raw-trigger replay includes generated rising cam edges for sequential runs and never invents falling edges. Target raw recording and the continuous phase decoder use separate capture channels. The archived printed A3 manual is retained; these current software instructions supplement it.

## Comparison and evidence

[The comparison](../reports/engine/sequential/comparison.json) covers33 cases: the shared ESP32 dispatcher, actual pinned Speeduino with native32-bit timers, and a separate Mega-like16-bit/4us/equality timer model. Each runs11 start/load/fault/cam scenarios on independent copies of the verified MVEM air path plus local empirical combustion/free shaft. Six125/250us coupling checks stayed below0.24% relative difference in final speed, delivered fuel and combustion work, against a3% bound. The legacy batch regression also passed14 cases and4 step checks.

Warm final speeds were approximately919RPM here and917RPM in both reference timer models. Throttle-step speeds were approximately2870RPM and2869RPM. These are uncalibrated model outcomes, not performance or physical accuracy measurements.

Our strict cam-loss policy coasts to rest. Pinned Speeduino retains acquired phase when the cam disappears, and can use Partial-sync wasted operation before Full sync. That is a declared behavior difference. Each reference output event records actual sync status and effective360°/720° range. Intentional Partial wasted operation, Full720 errors and unsynchronized pending discharges are counted separately, without a fixed-time startup heuristic.

The16-bit model checks timer wrapping, equality matching, zero-tick delay and disabled/re-enabled counting. It is not AVR CPU, vector, interrupt-latency or register emulation. Long delayed native32 coast events depend on its larger timer range. An independent prescribed crank-dropout/cam-continuation probe reproduced a Full720 wrong-phase discharge in both timer widths; this is native source-model evidence, not a physical Speeduino hardware claim.

[Recorded execution archive](../reports/engine/sequential/recorded-execution.tar.xz) preserves all39 raw runs and their execution-source hashes. A strict event-mode analysis subsequently refines fallback counts from those recorded events; it does not rerun or change controller timelines. Execution and analysis hashes remain separate. [Plots](../reports/engine/sequential/sequential-comparison.png), independent review reports, native tests, browser checks and build/ISR evidence are alongside it.

All three target builds pass. Independent static ELF review checks ISR code/literals/data and observes bounded stack frames; it does not measure interrupt jitter, runtime stack watermarks or GPIO timing. No board was flashed. Physical Hall conditioning, injector/coil behavior, watchdog shutdown, module fit, supply transients, EMI, thermal, splash and engine/vehicle operation remain unqualified.

```sh
python3 scripts/build_speeduino_sim.py
python3 scripts/build_speeduino_sim.py --timer-bits 16
python3 tools/test_speeduino_timer_model.py
uv run --with fmpy==0.3.26 python tools/run_sequential_scenarios.py
python3 tools/review_sequential_results.py .cache/engine/sequential-final .cache/engine/sequential-reviewed
CXX=g++ sh scripts/test_firmware.sh
PYTHONPATH=tools python3 -m unittest tools.test_engine_sequential
uv run --with playwright python tools/test_sequential_ui.py
```
