Independent review: first engine-development increment
2026-11-03 | No production source edited by reviewer; physical outputs inhibited.

Four reproducible defects were identified and the parent's corrections rechecked. No unresolved defect remains in the reviewed source paths; the qualification limits below still apply.

1. Protected stall could never restart (P2, corrected).
   Baseline load_step/12s/seed17 rejected a corrected coil end at4,744,078us: start4,741,489us, old end4,744,309us, proposed end4,745,327us. The proposed3,838us dwell exceeded the unchanged3,500us limit, so immediate all-low protection was justified. The defect was the permanent failed_ latch: even after stopping and receiving a fresh1,000RPM crank signal, it produced116 further rejects and zero edges. Corrected adapter retains the fault until external all-low acknowledgment,150ms without raw teeth and20ms of fresh valid stopped/unsynced samples. Malformed samples, >20ms control gaps and raw teeth restart the gate; cumulative reason/stop/recovery history survives reset. Independent checks withheld low acknowledgment (mask144), injected malformed input, and delivered continuous unsynced teeth: each correctly prevented recovery. Actual load_stall_restart now records one dwell-limit stop and one recovery, then runs at1,058.53RPM with final faults0.

2. Clean tuning clients could overwrite another writer (P2, corrected).
   Session.refresh() advanced calibration base on writes and even live polls. A client holding rev1/cell85 could overwrite HTTP's rev2/cell88 with its cached page, silently producing rev3/cell85. Connections now retain one calibration snapshot; another writer requires reconnect. Both the cached full-page repro and live-poll variant now burn0x85, preserving HTTP rev2/cell88. Common Session logic serves TCP and PTY; real loopback TCP verifies shared HTTP burns/reconnect behavior, and real PTY verifies fragmented envelopes and CRC rejection.

3. Fractional SIL time conflicted with integer timer/trigger ordering (P2, corrected).
   Overrev/seed17 failed the active-coil !reachable branch at4,765,781us: the pending fall was at exactly that integer timestamp, while the next target was only0.009936deg ahead and rounded to now. The fractional integration endpoint had left that due fall unpopped before a rounded trigger. SIL now drains edges through round(end*1e6) before delivering the quantized trigger. Recheck: zero rejects, final running6,404.66RPM, latched-demand error0.06196deg max. This was an executor ordering defect, not an expected dwell protection.

4. Revision representation broke MSQ exchange and new protocol sessions (P2/P3, corrected).
   '.9g' rounded revision1,000,000,001 to1,000,000,000 and made UINT32_MAX unimportable. Also valid JSON revision1.0 saved as Python2.0, then struct.pack(U32) crashed new sessions, including after restart. Validated load/save now canonicalizes revisions to int; MSQ baseRevision performs explicit range/integrality validation and lossless integer formatting. Integer and float representations of1,000,000,001 and4,294,967,295 now roundtrip; JSON1.0 saves/restarts and creates sessions successfully.

Validation commands and retained evidence

- PYTHONPATH=tools python3 -m unittest tools.test_engine tools.test_engine_http -v
  23 tests passed in7.381s. Log: final-python-tests.log.
- c++ -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined -fno-omit-frame-pointer -I firmware/include firmware/tests/engine_test.cpp -o .cache/engine/independent-review/engine-test-asan
  Then .cache/engine/independent-review/engine-test-asan: passed, no sanitizer diagnostics. Log: final-native-tests.log.
- PYTHONPATH=tools python3 .cache/engine/independent-review/reproduce_interop.py interop-final.json
  Both stale-client cases conflict; high integer revisions roundtrip. Float revision evidence: integral-float-revision-final.json.
- PYTHONPATH=tools python3 .cache/engine/independent-review/reproduce_recovery_guard.py recovery-guard-final.json
  Withheld acknowledgment, malformed input and continuous unsynced teeth preserve the fault.
- Independent final Simulation(defaults, scenario,12,17) runs: load_step, load_stall_restart, overrev and stall_restart. Reconstructed every saved edge, checked monotonic order, duplicate transitions, final mask0, injector<=15,000us and coil<=3,500us. Both load cases report one classified dwell protection; the other cases reject zero. Details and source hashes: final-scenarios.json.
- Independently reconstructed all108,388 saved edges from the final27-case sweep (nine scenarios, seeds1/3/17). Every case has ordered nonduplicate transitions, final mask0 and unchanged15ms/3.5ms bounds; there are zero unexpected scheduler failures. Only seed17 load_step/load_stall_restart record expected low-RPM dwell protection. Evidence: final-27-edge-audit.json.
- Current manifest, wire field order, page sizes, revision offset268, live block76bytes and UI/INI signatures agree: layout-coherence.json.

Baseline commands/evidence remain in findings-baseline.txt, stall-evidence.json, stall-rejection.log, interop-evidence.json, integral-float-revision.json and overrev-rejection.log. Reproduction scripts use current repository source; retained baseline evidence records the original failures.

Harness correction also verified: top-level passed and nonzero exit now reject unexpected scheduler failures. Synthetic CLI negative cases rejected an unreachable deadline, dwell protection in overrev, and a load-case dwell stop above the crank/run threshold; only the intended low-RPM load-stall dwell case passed. These tests wrote only to a private cache tree. Evidence: negative-runner-evidence.json.

Limits: This review does not establish calibrated plant validity, real engine operation, target ISR/GPIO timing, or full Speeduino parity. Actual TunerStudio currently rejects the own live identity, so online compatibility remains unverified. Parent is testing the offline application workflow separately; this reviewer inspected browser helpers but did not independently exercise browser MSQ import/export. Keep the own-signature restriction. Latest-demand error differs from latched-event error: stall_restart/seed17 retains one committed firing across a10deg demand change while the actual event error stays below0.018deg; this does not establish real timing accuracy. A future regression should freeze ordered wire fields or assert generated layout/INI coherence, since field order currently inherits defaults JSON key order.
