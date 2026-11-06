# Verified software/bench checkpoint

Feature expansion is frozen at the user's requested early stop. Runtime firmware, UI and engine/simulator code remain at22b2df6. The current changes correct entry-point guides and add an actual pairing-control browser check. **Normal physical engine outputs remain inhibited.**

Acceptance: full native sanitizer suite,99 host/API/config/protocol checks, sensor NVS fault tests, four Chrome workflows, and three fresh inhibited firmware builds. Current UI bytes are present in each linked image; source inputs/default caches are unchanged. The independent reviewer found0 supported-path regressions and0 open findings. All owned review/test services are terminal; no device was flashed.

`validation.zip` contains logs, source/build identities, UI evidence and the independent review. Build binaries remain in the recorded local cache paths; reproduce using the source guide. A review-tool ELF-container rewrite was restored exactly from original verified archives and independently rehashed; firmware binaries and sources were unchanged. The first pairing harness wait expression was corrected for the existing CSP, without changing product policy.

This accepts the declared bench/software paths. Physical hardware/RF/fit and engine operation are unqualified; supported online TunerStudio, failed reference convergence and missing ECU features remain open. Historical A3 manufacturing/manual files and A6/A7 development drafts keep their original scope.

See [the checkpoint guide](../../../docs/bench-checkpoint.md) and [feature coverage](../../../docs/engine-feature-coverage.md). The broader feature goal is unfinished and is being paused at this checkpoint.
