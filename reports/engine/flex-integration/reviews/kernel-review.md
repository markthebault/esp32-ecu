# Independent kernel development-integration review

Accepted only the frozen kernel/JSON/runtime contracts in kernel-freeze-005. No open findings remain in that scope. kernel-independent-review.json binds all eight requested sources and the evidence.

The review found and reproduced malformed raw samples that could alter demand despite invalid calibration/fault frequency or forged conversion fields. The controller now rechecks the F64 capture contract, including the50us high-gap floor, while preserving legitimate smoothing. A separate runtime parser finding allowed four impossible qualified flag/source tuples; all are rejected after the fix. Source3 value-only samples now also reject invented unfiltered waveform data. Earlier failed freezes and probes remain preserved.

Final strict-warning C++17 ASan/UBSan runs pass296 parent checks,14 context checks and93 schema/U64/record checks; four independent malformed runtime tuples reject. The enabled spark oracle passes2,164 checks across all secondary modes, clamps, trims and crank behavior. The final disabled kernel matches14,400 stateful baseline rows exactly, with the same12,271,007-byte stream and binary64 bit patterns (SHA2565825b992bb99148fc851c8656e164edde7a54b22cc98d8f8803258df4de6da92).

Schema1..8 migration into reused enabled Tunes resets flex to disabled neutral, preserves schema8 secondary maps and upgrades idempotently. Near-UINT64_MAX time/counter values survive record/JSON roundtrips exactly. Same-calibration context reset preserves fault/clock history and requires full reacquisition plus a consumed-invalid generation ACK.

The explicit retention tradeoff is256→128 rows,12.8s at100ms and2.56s at20ms. A300-row owned probe verifies128 retained,172 overwritten and explicit gap/page accounting. Native recorder size is87,128 bytes under the90KiB static budget. Collector metadata permits historical256/current128 and current help states the shorter window. These facts do not establish target heap/stack/load/timing behavior.

Target acquisition, protected hardware/PCB and full UI/config/storage/log/wire/plant integration have not been accepted here. No production Speeduino executable, hardware, eFuse, service or outside message was used in this integration review. All component executables were owned and received GCOV_PREFIX before startup. The earlier separate16-file generated coverage side effect remains preserved/disclosed and excluded from unchanged-cache statements.
