# Independent scheduling and SIL recheck

Review date: 2026-11-03. Scope: current uncommitted portable engine core, per-tooth scheduler, native bridge, physical-input binding, reduced-order SIL, and associated portable regressions. No GPIO outputs were enabled and no production source was changed by the reviewer.

Three additional correctness/evidence issues were reproduced and corrected by the implementing agent during this review:

1. **Selective cut lost an active falling edge.** At 1000 RPM and 10 ms injection width, setting `fuel_cut` at 46 ms after a 45 ms leading edge cleared scheduler state and discarded the closing event. Four virtual injectors remained high at 90 ms. The corrected scheduler retains bounded closing deadlines while suppressing future starts. The same reproduction now shows closing edges at 55 ms and final mask zero. A fuel/spark cut and resume regression is included.
2. **Edge traces silently truncated at 4096 events.** A default 12 s overrev scenario stopped its saved trace at 5.576368 s and reconstructed a high-channel mask of 147 while the summary claimed shutdown. The cap has been removed for the already bounded 1–30 s run duration. The latest 12 s run contains 15076 edges, includes explicit simulation-end lows at 12 s, and reconstructs zero. The regression now exceeds 4096 events.
3. **Legal pre-dwell advance updates latched timing failure.** A 5 to 15 degree change at 500 RPM failed for 180 of 360 supported trigger offsets; a -5 to 40 degree change at 1000 RPM failed at several tooth phases. The corrected scheduler retains a previously committed full-dwell event when the new demand is no longer achievable, then applies the new demand on the next firing. Both reproductions now report no failure. A sweep covers all 360 offsets and 60 update phases at both RPM/advance pairs, checking edge order and high-time bounds.

A build-cache defect was also corrected: Python native-library dependencies omitted `engine_scheduler.hpp`, allowing scheduler-only edits to reuse a stale shared library. The dependency set now covers the ECU headers and cJSON headers/source.

Validation performed on the corrected state:

- `c++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Wall -Wextra -Werror -Ifirmware/include firmware/tests/engine_test.cpp -o .cache/engine/recheck-engine-tests && .cache/engine/recheck-engine-tests`: passed, including the new offset/update-phase sweep.
- `PYTHONPATH=tools python3 tools/test_engine.py`: all 13 tests passed.
- Independently compiled `.cache/engine/recheck-dfco.cpp`: final injector states `0000` after selective cut.
- Independently compiled `.cache/engine/recheck-crank-advance.cpp`: `offsets failing: 0/360`.
- Independently compiled `.cache/engine/recheck-advance.cpp`: no sticky timing failures at any tested update phase.
- Independently reconstructed 12 s default overrev saved edge trace: 15076 events, no duplicate state transitions, final mask zero, max injector high 7990 us, max coil high 2838 us, no rejected plans. Timing error to latched event demand 0.0617 degree max; error to latest control demand 0.392 degree max in this particular synthetic run.

No further blocking defect was found within this bounded portable review after these fixes. This is not a claim that the project can run a physical engine. Remaining objections to any such claim: the event executor is native SIL only, target compare-ISR integration/jitter is unqualified, the reduced-order plant and generic coil-energy proxy are uncalibrated, the controller only implements four-cylinder batch fuel/wasted ignition, and full Speeduino closed-loop comparative validation plus real electrical/physical fault testing is still outstanding. Keeping a previous committed advance for one firing creates a deliberate transient lag from newest demand; timing reports must preserve the separate latched-event and latest-demand metrics.
