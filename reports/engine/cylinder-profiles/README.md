# Public cylinder integration development packet

Tune schema11 / own012, coherent data3, screen schema7 and MSL009 add1..8 logical cylinders to configuration, virtual execution, UI, tuning and debugging. The existing PCB has4 injector and4 coil commands. All normal images inhibit engine outputs; physical qualification and the full Speeduino goal remain unfinished.

- `sources.zip`: current source overlay on commit5c132ee, with per-file identities in the manifest. Apply only to a separate checkout; preserve existing work.
- `validation.zip`: sanitized firmware/regression results, shared-codec/CAS/legacy probes, independent radio checks, actual sender API-model bytes/replay, linked static audits and memory/formatter checks.
- `plants.zip`:53 raw cases,9 coupled/geometry/log tests and independent plant evidence. The48 normal cases cover1..8 cylinders in all3 modes on two uncalibrated plants. Wrong-order/reference and fault controls retain fixed physical geometry. No expanded Speeduino engine-run or turbo result is claimed.
- `applications.zip`: actual own012 TunerStudio C8 edits/page-byte validation, MegaLogViewer009 field plots, current Chrome checks and reviewer closure receipts. Proprietary executables, user profiles, registration and copied vendor projects are excluded.

Reproduce in the pinned Linux workspace with `CXX=g++ CC=gcc sh scripts/test_firmware.sh`, `python3 tools/test_engine_profile_boundaries.py`, `python3 tools/test_cylinder_radio.py`, and `uv run --with fmpy==0.3.26 python tools/test_engine_profile_plants.py --output NEW-DIRECTORY`. Build the separate profile FMU first with `python3 scripts/build_engine_airpath.py --profiles`; prerequisites/pins are documented in the repository's research-benchmark guide. Chrome scripts require Playwright and the installed Chrome. Vendor applications require their separate unmodified installations and fresh owned profiles.

The4-part sender replay is a deterministic SDK API model, not RF or RTOS measurement. Target audits prove linked source/layout/policy properties, not runtime heap/stack, timer latency or physical behavior. Own012 offline editing is verified; supported online onboarding remains unresolved. Known derived-AFR/unknown-lambda viewer caveats remain. No device was connected or flashed, and no vendor message was sent.

Remaining: distinct16-output genuine Speeduino fixture and generalized coupled comparison; matching turbo geometry; additional protected PCB drivers/connectors/enclosure; target/HIL, electrical/environment/fit tests; online vendor integration and the broader control/trigger/configuration/debug feature gaps.
