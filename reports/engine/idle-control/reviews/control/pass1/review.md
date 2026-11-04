# Idle controller/PWM implementation review, pass 1

Read-only review of the first uncommitted idle_control.hpp/idle_pwm.hpp increment. Exact reviewed headers are snapshotted in `include/ecu/`; their hashes and compiler/test outputs are in `manifest.json` and `results.json`. Root is implementing the target owner, native actuation, wire and UI separately; those integrations are not accepted by this pass. Physical GPIO remains outside these tests.

## Findings, in priority order

1. **High: antiwindup can prevent any progress toward an achievable duty.** `include/ecu/idle_control.hpp:114-123` clamps a candidate integral, compares its trial output with the hard/slew-achievable output, and discards the entire candidate when it overshoots. It then recomputes desired from the old integral. When an integral step exceeds available headroom, this sequence can repeat forever while the command never approaches the limit.

   Reproduction A: run/crank duty20%, KP0, KI0.02, target900, RPM800, period100ms, slew1%/s, entry/taper/dashpot0. Begin cranking to establish20%, then run for5s. Every0.2% integral increment exceeds the0.1% allowed slew over a period, is discarded, and duty remains20% with I0 indefinitely despite persistent error. Reproduction B: KI0.2, period250ms, integral limit100, slew1000, target2500, RPM600. Each95% increment would exceed maximum100%, so the integral remains0 and duty remains20%, rather than progressing toward100%. Both configurations pass valid(). `probe.cpp` prints both cases as `antiwindup_no_progress`.

   Fix with conditional integration/back-calculation that permits progress to the achievable bound, or a separately held saturated output demand consistent with the integral. Do not only widen the integral limit or tune around these cases. Add both directions of slew saturation, both hard limits, and recovery under changing error. The randomized finite/bounds properties pass while this functional bug remains, so those properties alone are insufficient.

2. **Medium: entry TPS hysteresis has no established closed-throttle state after reset.** `idle_control.hpp:51,75-77,94` initializes throttle_ false, only changing it when TPS exceeds closed+hysteresis. A fresh controller at2.25% with a2% entry threshold and0.5% hysteresis enters ClosedLoop without ever observing TPS<=2%. The same can occur after stopped/fault clears. Require proving the entry threshold after reset/clear; hysteresis may retain eligibility after a real closed-throttle observation. `fresh_throttle_band` reproduces ClosedLoop/duty20 at2.25%.

3. **Medium: recovery accepts a nonzero PWM command as an explicit zero.** `idle_pwm.hpp:72-80` allows the quiet recovery branch when either enabled is false or high_us is zero. With enabled=false, high_us5000 and supervised_stop=true on fresh samples for20ms, an EngineFault clears and recoveries increments. This conflicts with the stated requirement of continuous explicit zero commands. It does not directly energize during the disabled samples; it weakens the latch-clear contract. Require high_us==0 for supervised recovery, while ordinary disabled commands may still cut immediately. Reproduce using `nonzero_disabled_recovery`.

4. **Medium, integration contract: the PWM observation mixes pending and applied identities.** `idle_pwm.hpp:71` copies sequence and revisions into stats immediately; `boundary():38` copies period/high only when the next cycle starts. Submitting seq2/high2500 while seq1/high5000 is active yields stats sequence2/high5000 until the boundary. These fields cannot collectively describe one applied waveform. Expose pending/accepted identity separately from latched waveform identity, or explicitly label the existing identity as pending and add applied sequence/revisions. Root's owner should not publish them as one applied command. Reproduce using `mixed_applied_observation`.

5. **Medium, diagnostics: a late boundary is timestamped as if it executed on time.** `idle_pwm.hpp:63` calls boundary(cycle_,io), and level() stamps stats.observed_us with that scheduled phase. With a due boundary10000 and allowed dispatch at10020, the actual sink goes high at10020 but stats.observed_us is10000. Keep scheduled phase to avoid accumulating drift, but stamp execution/observation using actual now. Reproduce using `late_boundary`; max_lateness correctly reports20.

6. **Medium unless prevented by the owner: a new hard maximum can be exceeded while slewing down.** `idle_control.hpp:127-130` hard-clamps desired first, then clamps that value into the old duty's slew range. A valid open-loop change from80% to max25% (all curves adjusted to25%) yields79% at the next5ms sample. The kernel accepts Config/Base afresh each call and has no revision/reset contract. Either hard-clamp the final output, or guarantee/document/reset before every tune/mode/limit change in every owner. The latter must be verified in target, host and native integration; it is not established yet. `changed_limit` reproduces this case. This finding concerns changes to configuration while the object remains active, not a fixed-config bounds failure.

## Verification completed

- ASan/UBSan builds of both isolated review executables completed without sanitizer diagnostics.
- 900,000 deterministic randomized controller samples across OnOff/OpenLoop/ClosedLoop retained finite outputs in0..100%, bounded integral, monotonically increasing update counts, and immediate off behavior for disabled, stopped, overrun and engine-fault states. Config was fixed within each run; this does not test owner configuration fences.
- 135 NaN/positive-infinity/negative-infinity mutations across every Config scalar, every curve cell and Base target/KP/KI were rejected by valid(). Twelve nonfinite input cases produced Fault/zero duty. Supply8.999/9/12/16/16.001V plus nonfinite cases behaved correctly. Freshness at20,000us,20,001us and a future sample was checked.
- Integral scaling with explicit cranking-to-running entry matched the same4% integral change after2s for10/100/250ms periods, with unrestricted slew and no saturation. This confirms elapsed-time units in the unsaturated case, not antiwindup correctness.
- Twenty-five PWM cases covered periods2500/4000/10000/20000/50000us, each at high0/1/half/period-1/full. With1ms heartbeats and exact dispatch, integrated high time over1s matched the commanded fraction exactly. Zero/full duty, future event deadlines and ordinary stop were coherent.
- Failed rise/fall writes both latched OutputFault, drove the sink low, disabled execution and removed alarms. Twelve malformed/future/replay/expired/range-boundary commands cut and latched as intended.
- Existing production tests cover initial configuration, crank/run taper, ordinary entry, basic response and faults; additional functional regressions are needed for the concrete findings above. Diagnostic `probe` deliberately prints the faulty behavior and exits successfully, so its exit status is not a claim that the implementation satisfies the desired contract. `properties` contains actual pass/fail assertions.

## Reproduce

From the repository root:

```
c++ -std=c++17 -Wall -Wextra -pedantic -fsanitize=address,undefined -g -O1 \
  -I.cache/engine/idle-control-review/pass1/include \
  .cache/engine/idle-control-review/pass1/probe.cpp \
  -o .cache/engine/idle-control-review/pass1/probe
.cache/engine/idle-control-review/pass1/probe

c++ -std=c++17 -Wall -Wextra -pedantic -fsanitize=address,undefined -g -O1 \
  -I.cache/engine/idle-control-review/pass1/include \
  .cache/engine/idle-control-review/pass1/properties.cpp \
  -o .cache/engine/idle-control-review/pass1/properties
.cache/engine/idle-control-review/pass1/properties
```

These use the immutable reviewed header snapshot, so later production fixes do not erase the original reproductions. Rebuild against current headers for regression acceptance. A subsequent pass should verify fixes and owner freshness/recovery authority, actual PWM/plant coupling, schema migration/wire layout, target stack/IRAM/radio behavior and real UI/application reads. No physical engine, electrical driver, thermal or vehicle qualification follows from this review.
