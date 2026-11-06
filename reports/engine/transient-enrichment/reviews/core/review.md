# Independent transient-enrichment core review

Reviewed the initial uncommitted `transient_enrichment.hpp` and engine integration against the frozen architecture/reference assessment and `64c21ed` legacy fixture. Source bytes were copied before probes into `snapshot/`; the corrected version is preserved separately in `fixed-snapshot/`. This reviewer made no production edits. Commands, outputs, compiler version and immutable SHA256 hashes are in `results.json` and `manifest.json`.

**One medium functional bug was found and fixed by root. No remaining concrete high/medium blocker was identified in this bounded core review.** This is not target-executor, UI/protocol, simulator-calibration or physical-engine acceptance.

## Fixed finding

**Medium: coincident expiry discarded a newly qualified acquisition window.** Initial `transient_enrichment.hpp:101,121` cleared an expired event, computed the current source window, then returned unconditionally if the old phase had expired. A new stronger event could therefore be lost based solely on whether a task poll happened before its sample delivery.

Reproduction:20ms source window and20ms event duration. A100%/s event begins at20ms. The next acquired window ending40ms has200%/s. Delivery at40ms produced inactive/Expired; delivery of that same40ms acquisition at41ms, after an expiry-only poll at40ms, produced active acceleration with19ms remaining. The acquired endpoints and computed rate were identical. `probe.cpp` demonstrates this against the immutable initial snapshot.

Root removed the unconditional expiry return. The corrected snapshot starts the new200%/s event for both immediate and delayed delivery, and only the legitimate1ms remaining-lifetime difference persists. Expiry still clears a neutral phase. Root also added a scheduling-equivalence regression. This review's fixed-source reproduction and test outputs confirm the correction.

## Verified behavior

- The committed `legacy_golden.cpp` fixture compiled against the corrected header produced **byte-for-byte equal CSV scalar/pulse results** to the immutable64c21ed baseline. That covers step/exponential decay, threshold/cap, repeated acquisition stamp, negative movement, stale recovery, crank-to-run and EGO gating. It intentionally does not claim bit-identical cross-platform libm behavior.
- The two new repository core tests passed under ASan/UBSan against the reviewed headers. They cover rate windows, expiry/retrigger/reversal, latched tapers, clamp/history resets, multiplier/adder accounting, openings/deadtime/trims, decel0, EGO and fault/capacity recovery.
- Independent `properties.cpp` exercised486 dose scenarios across batch/sequential/semi, both application modes, MAP10/50/100, VE20/85/120, warmup80/100/200 andlambda0.75/1/1.2.448 cases matched independently derived mass/pulse equations;38 correctly failed final capacity limits and cut. Positive transient phases kept EGO at1.
- Eighteen decel0 cases covered all three strategies, both positive application modes and9/14/16V. All had fuel_cut, zero scalar/channel injector pulses and retained spark/dwell without an unexpected fault. A separate negative-trim case verified that a scalar reference-added pulse above the configured limit can remain safe when all actual trimmed channel demands are below it; capacity is judged on actual channel demand.
- Eighty-seven NaN/positive/negative-infinity mutations covered every scalar and curve cell and were rejected.400,000 deterministic randomized transient samples retained finite correction in0..750%, bounded remaining lifetime, coherent active flags, bounded qualified rates and immediate neutral/inactive behavior when ineligible.
- `clocks.cpp` checked duplicate/future/stale acquisition,20,000/20,001us freshness boundaries, acquisition gap/reversal, duplicate control time, near-UINT64_MAX deadline overflow and configuration reset. No sanitizer diagnostics occurred. Mode/application changes clear history before a new derivative can form.

The reference adder is applied to a full-cycle per-cylinder mass independent of current MAP/VE/WUE/EGO. The engine splits the total dose by actual openings, applies cylinder trim to the complete effective dose, and adds deadtime once. The tested algebra matches that contract. New decel0 suppresses the deadtime-only pulse and checks capacity against zero commanded fuel demand; independent target-edge tests are still needed to establish executor behavior.

## Intentional policy and limitations

- After the minimum-change gate, **any observed opposite rate cancels** an old phase; only a threshold-passing opposite rate begins a new phase. Thus a−30%/s window can cancel acceleration even with a40%/s trigger threshold. Root confirmed this as intentional and will document it. It is not classified as a remaining defect. It differs from both a threshold-qualified-only reversal policy and pinned Speeduino's absolute-peak hold behavior.
- Equal RPM/cold taper endpoints are accepted and disable that taper branch. This follows the conditional implementation and should be visible in configuration guidance; it is not an undefined divide.
- DFCO inhibits/clears the module on each cut frame. The first sample after a one-step reopening ends DFCO may only seed history and receive no AE. That follows the conservative reset contract, not an implementation mismatch. Exercise it in coupled quick-lift/reopen scenarios. A future design could retain valid source history while clearing only the held phase during DFCO; that would require an explicit policy/test change.
- Transient observation availability is distinct from qualified-rate validity. An available priming/inhibited/off observation can have NaN rates/window and clear RateValid. UI/JSON/MSL/native fixture guards must respect per-field validity rather than requiring all floats finite whenever available is true.
- Rejected capacity proposals deliberately retain useful transient demand diagnostics while clearing active state; those are rejected demands, not evidence of applied fuel.
- These probes do not test physical timing, GPIO, actual injector flow, target interrupt behavior, shared tuning/telemetry layout, actual online vendor acceptance, firmware heap/IRAM placement, or plant calibration. Root is separately running target-edge, simulator, UI/reference integration tests.

## Exact compiler commands

Compiler: `/usr/bin/c++`, Ubuntu GCC15.2.0-16ubuntu1. No clang dependency or CXX environment override was used by these probes. Example commands from the repository root:

```
/usr/bin/c++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  -fsanitize=address,undefined -g -O1 \
  -I.cache/engine/transient-core-review/fixed-snapshot \
  .cache/engine/transient-core-review/properties.cpp \
  -o .cache/engine/transient-core-review/properties_fixed
.cache/engine/transient-core-review/properties_fixed
```

The same flags build `probe.cpp`, `clocks.cpp`, `firmware/tests/transient_enrichment_test.cpp` and `firmware/tests/engine_transient_test.cpp`. The legacy comparison uses `-std=c++17 -O2` with the identical frozen/current compiler settings. `results.json` records every exact argument array and run result. Rebuilding `probe.cpp` against `snapshot/` reproduces the original finding; rebuilding against `fixed-snapshot/` demonstrates the fix without overwriting the evidence.
