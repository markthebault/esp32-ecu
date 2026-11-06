# ESP32 timing executor

The ESP32 now has a target capture/compare implementation for the existing four-cylinder batch fuel and wasted smart-coil strategy. The selected N16R8 firmware executes virtual outputs with physical engine commands inhibited at compile time. No configuration, API, pairing button or tune enables them. This is source, native simulation and build evidence. No board was flashed or electrically tested for this increment.

The A3 manufacturing records, A4 fit draft, BOM and enclosure are unchanged. The selected supplier module still requires pin, header spacing, antenna and RGB-pin verification before a physical output build can be considered.

## Capture and scheduling

`engine_target.cpp` creates a dedicated core 1, priority 20 task and allocates both priority 3 interrupts from it. MCPWM captures the hardware counter on each rising Hall edge. GPTimer supplies the common microsecond time domain and one-shot compare alarms. Both use the APB clock. Sensor/control updates remain in the application task at approximately 5 ms; the timing task wakes on capture or a 1 ms timeout.

At boot, with capture channels and outputs disabled, a software synchronization event resets the capture counter. Two GPTimer reads bracket that event. Initialization rejects a bracket wider than 10 µs and reports its uncertainty. The pinned S3 driver supplies an 80 MHz, 32-bit capture clock; GPTimer uses 1 MHz. Each channel independently resolves its counter against the current GPTimer count, including counter wrap and reversed callback order. Resolution assumes callback delay below 5 ms. Capture processing older than 1 ms inhibits execution. These are checked software bounds, not measured target latency or oscillator accuracy.

The ISR places captures into a 64-item internal-memory queue. The task runs the missing-tooth decoder, takes a bounded scheduler snapshot under a target lock, and calculates angles outside that lock. Commit requires the same generation, configuration epoch and command sequence. An interrupt, cut or configuration change invalidates an older calculation. Four failed retries inhibit execution. A newer command can supersede an older queued capture for scheduling while that capture still feeds the decoder.

GPTimer dispatch reads the current schedule and current counter. A callback left pending by an older alarm cannot replay that alarm's event. Dispatch uses fixed storage, integer helpers and a maximum of 16 events per invocation. Tied falling edges precede rising edges. Overdue short pulses are rejected before their rises are emitted.

Independent deadlines cover:

- Producer progress: 5 ms, checked before a late heartbeat can extend it.
- Command and earliest sensor sample: 20 ms, checked before replacement.
- Missing-tooth decoder stall timeout, independently of new control commands.
- Each active injector/coil high interval, bounded by its configured maximum and the 15 ms / 3.5 ms carrier ceilings.
- Dispatch lateness: 25 µs. A larger observed delay cuts all virtual outputs and latches a reason.

`actual_us` is one dispatcher observation timestamp used for successive writes in that invocation. It is not a measured timestamp of each GPIO transition. Dispatch lateness and high-time counters cannot establish per-pin jitter, pulse width or electrical response. Interrupt and lock execution times remain unmeasured.

## Configuration and faults

Engine and sensor configuration saves cut execution before persistence begins. A configuration hold spans NVS writing and active-state publication. During the hold, submissions are rejected and captures are counted without scheduling. Release changes the epoch and enforces revision floors, preventing cached old-profile samples from reactivating execution. The decoder restarts on an accepted epoch change. Failed engine storage blocks actuation proposals and further saves.

Faults retain their first reason and counters. Recovery requires outputs low, fresh valid stopped commands, more than 150 ms without raw crank activity and a further continuous 20 ms interval. Activity or stale/control gaps restart the interval. This establishes software absence of signal, not a stationary physical rotor. A failed capture timebase cannot recover through the ordinary stopped-state path.

The legacy single-pulse bench path and engine timing path cannot own outputs together.

## Build policies

```sh
pio run -d firmware -e compact_n16r8_web
pio run -d firmware -e compact_a3_timing_bench
```

The first is the selected module's normal web/radio firmware with physical engine outputs inhibited. The second is an explicit **generic A3 dummy-load build**, based on the older generic module contract. It omits web/radio service and compiles a GPIO sink for injector/smart-coil commands only. Pump/fan remain low. Its first arming requires J3 closed at boot, fresh healthy synchronized commands and good SAFE_N/interlock signals. A gate/supervision failure after arming latches until MCU reset. Watchdog feed remains in the supervised application loop. This build is preparation for HIL and dummy-load measurements, not authorization to connect an engine.

Combining the selected N16R8 flag with dummy-load actuation is a compile error until the supplier module's hardware pin/fit issues are resolved. The negative-build check records that guard. No dummy-load hardware run has been performed.

## UI and debugging

**Engine development → Timing execution** reports mode, fault/last reason, virtual/physical masks, dispatch count, capture uncertainty/age, producer age, dispatch lateness and trace overwrites. **Export timing trace** downloads `GET /api/engine/timing`. The fixed ring retains at most 128 records with sequence, scheduled/observed times, channel, edge, reason and tune revision. Overwrites are counted. A snapshot reports records overwritten while it was being read instead of claiming a complete history.

Host web data remains labelled completed synthetic SIL. Its endpoint does not claim a real capture clock or target interrupt measurement. The separate external-plant regression uses the actual shared `timing::Executor` through a native ABI; it does not simulate FreeRTOS, MCPWM, cache outages, GPIO drivers or CPU execution cost.

## Reproduce and assess

```sh
CXX=g++ sh scripts/test_firmware.sh
PYTHONPATH=tools python3 -m unittest tools.test_web_config tools.test_radio tools.test_engine tools.test_engine_http -v
uv run --with playwright python tools/test_engine_ui.py --report-dir reports/engine/target-timing
python3 scripts/audit_target_isr.py firmware/.pio/build/compact_n16r8_web/firmware.elf .cache/engine/target-current-closure
python3 scripts/audit_target_isr.py firmware/.pio/build/compact_a3_timing_bench/firmware.elf .cache/engine/target-dummy-current-closure
uv run --with fmpy==0.3.26 python tools/run_target_scenarios.py
```

The external plant, pinned Speeduino source and neutral benchmark profile are described in [the research benchmark](engine-research-benchmark.md). The new matrix uses 5 ms control/sensor injection for both systems, plus the project's independent 1 ms producer heartbeat. Each controller drives its own plant from its emitted pulses. Complete edge streams are replayed to check ordering, alternation, all eight channels, closing edges and pulse maxima. Checks also cover conservation ledgers, idle/start/restart, load stall, trigger loss, sensor fault, throttle response and hard rev cut. Step-halving cases test coupling convergence. Assertions describe expected behavior of this declared uncalibrated plant, not every real engine.

[Evidence](../reports/engine/target-timing/validation-summary.json) records builds, tests, source/ELF hashes, matrix and independent review. Earlier milestone evidence is retained separately. The ELF audit assists source review: code/literal placement, registered callback indirections, internal ISR state and explicitly classified SDK error paths. It does not prove absence of all indirect data access or runtime allocation errors.

The audit retains 63 SDK flash-address references at 21 assertion call sites in each build. They load pointer values from IRAM and pass them directly as assertion metadata; no intervening dereference is accepted by the structural classifier. The pinned SDK checks cache state before reading these strings and substitutes internal text when cache is disabled. Fatal entry calls cache restoration before subsequent flash code, including cache-error handling and panic reporting. This is conditional error-path source evidence, not proof of uninterrupted timing or physical fail-low on an SDK assertion.

The [14-case comparison and four convergence checks](../reports/engine/target-timing/controller-comparison.json) pass. Warm-start final speeds are approximately 919 RPM for the target kernel and 917 RPM for native Speeduino. Both recover with declared starter assistance. Both stall under the declared large resisting load and exercise hard rev cuts. The MAP rail-fault case intentionally exposes differing policies: this project inhibits and coasts to rest; the chosen Speeduino configuration continues rotating. This does not establish a universal fault response for every Speeduino configuration. [Figures](../reports/engine/target-timing/comparison.html) retain those differences.

Before physical operation, measure ISR/lock duration, capture loss/overwrite, latency and per-pin edges under Wi-Fi/ESP-NOW and flash load; inject crank/cam/ADC faults; verify watchdog/interlock/reset/power-loss behavior; and characterize drivers, flyback, current and temperature. Full feature parity, calibrated engine behavior, online TunerStudio acceptance and physical vehicle/environment qualification remain open.

The subsequent [raw trigger recorder](engine-trigger-debug.md) uses separate diagnostic capture channels and leaves these decoder channels rising-only. Its evidence is recorded in a separate milestone directory.
