# Independent Speeduino runtime review

The reviewer inspected the pinned external production source and the native build/HAL/IPC adapters. No production or upstream file was edited by the reviewer. The review confirmed actual non-`UNIT_TEST` `setup`, `loop`, decoder and scheduler execution, rather than a formula clone.

Findings and resolution:

- Physical cylinder order differed between the two controllers. The explicit native-to-project map `(0,2,3,1,4,6,7,5)` was independently checked against the full 720° firing order and wasted-spark pairs.
- Archive extraction could leave an unlisted cached `.cpp` that was still compiled. The builder now enumerates pinned archive members, rejects extra generated source files, and hashes headers, dependency archives, compiler and flags. A negative extra-source test rejects the reproduced condition.
- Upstream instrumented dependency archives wrote `.gcda` files into the external checkout. The adapter now redirects coverage into its own executable cache. A fresh quit-only test changed zero external coverage files and wrote 16 private files.
- Direct production injector/ignition IO uses PORT registers rather than `digitalWrite`. Actual register transitions are observed after timer ticks and controller calls.
- Main-loop cadence changes timing. At 1000 RPM with 10° demand, the independent constant-speed test measured 9.816° with 100 µs loops and 10.728° with 250 µs loops. This is a native scheduling result, not measured AVR or ESP32 timing.
- Native timers use 32-bit counters. At 100 RPM and trigger loss, a pending GPIO fall occurred 640.88 ms after the last trigger, after reported RPM/sync had already cleared. AVR's 16-bit timer horizon differs, so this cannot be called an AVR defect. The limitation is retained in the benchmark documentation and provenance.
- Trigger delivery invokes the actual decoder callback directly. Native fake interrupt dispatch/edge selection is not validated.

Independent constant-speed runs acquired correct RPM/sync, produced 2800 µs dwell and 5444 µs electrical injector highs for the 5445 µs integer request, and repeated deterministically. The bounded wrapper test completed 10 seconds of virtual operation. Startup sensor polling/default values and ADC quantization remain part of production behavior and are declared in the profile.

Raw reviewer evidence is retained at `.cache/engine/speeduino-independent-runtime-review.json`, `.cache/engine/speeduino-independent-dropout-review.json` and the corresponding bounded reproduction scripts. The parent subsequently added locked/atomic native builds, configuration readback, clock bounds, explicit production halt, and enabled fixed rev protection. Those final changes are covered by [four actual-runtime integration tests](speeduino-runtime-tests.txt), [build guard evidence](reference-build-guards.json) and the [final controller matrix](full-controller-comparison.json), rather than a claim of a second independent target qualification.
