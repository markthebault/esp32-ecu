# Flex-fuel raw-edge groundwork

Portable acquisition and correction helpers are implemented and tested against genuine production source execution. **Own engine Tune, target capture, browser/TunerStudio configuration, logs/radio, PCB and coupled-plant integration remain pending.** The shipped controller stays schema 8/own009 and output-inhibited. This packet does not establish complete flex-fuel capability or full Speeduino parity.

The 25 declared cases drive synthetic flex transitions and a 60-2 crank waveform through real installed Speeduino callbacks, periodic timer service and production loop. No ethanol, RPM or sync status is injected. The same changed flex transitions feed our standalone portable core. Reference code is pinned at `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20` without UNIT_TEST. The builder proves an exact relink of the 109 original numerical objects, then reuses 108 original objects and compiles a separate entry. All 565 original input hashes remain stable.

The evidence records a conditional native startup/cache defect, non-100-Hz span behavior and an artificial 356-Hz counter-wrap alias. It also distinguishes intentional fault/stale/range policies and integer/filter differences. These are source/native observations, not physical engine findings. [The contract and findings](../../../docs/engine-flex-fuel.md) describe those limits and the required integration work.

`matrix/` preserves exact gzip input/stdout/stderr, source-bound results and the reference build manifest. `checks.json` replays all cases and verifies neutral/causal, loop-refinement and phase controls plus 11 deliberately corrupted records. `sources/` contains the frozen project files used by the runs, tests and postprocessor; `upstream/` holds inspected source and its license. Executables, objects and application binaries are not redistributed.

`reviews/` retains independent source, sanitizer, quantization-boundary, raw-data and actual owned-ELF replay evidence. Earlier freezes and review findings remain records. The final review binds the current implementation and documents its precise acceptance scope. `validation/` retains the full passing native firmware harness with `CXX=g++`; the unavailable default Clang attempt is retained separately. The native harness includes 509 flex checks.

The initial independent cache probe updated 16 generated upstream `.gcda` counters before coverage output was isolated. The exact paths and limitation are recorded in `reviews/coverage-side-effect.json`; prior counter contents could not be reconstructed and were left intact. Tracked upstream code and the existing numerical binaries/manifests are unchanged. Generated counters are explicitly excluded from unchanged-cache claims. Subsequent production runs isolate coverage before startup and through the fixture's executable-directory safeguard.

Verify from the repository root:

```sh
python3 tools/verify_flex_core_evidence.py --replay
```

This validates the complete artifact/source set and review bindings, replays the saved 25-case audits/controls and compiles the frozen 509 parent, 2,101 independent and 21,382 boundary assertions under ASan/UBSan. It does not reexecute the production ECU or a physical target. Add `--check-live-sources` only when current files still match the packet. Replay uses temporary compilation paths and suppresses bytecode writes inside the archive.

For a fresh production raw-edge experiment, use the guide's separate builder/runner commands and new output paths. The fixture is native execution with a deterministic 32-bit timer HAL and zero modeled CPU cost; it has a 60 s virtual bound. Sensor hardware/power/noise, ESP32 scheduling, actual boot timing, fuel chemistry, real-engine operation, physical qualification and full parity remain open.
