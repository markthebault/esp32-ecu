# Verified bench checkpoint

Feature expansion is stopped here at the user's request. Runtime firmware, web UI and existing engine/simulator code remain at commit `22b2df6`; this checkpoint corrects stale guides and adds a pairing-screen acceptance test. The [verification record](../reports/engine/bench-checkpoint/README.md) contains checks, hashes and independent review.

This is a software/bench development checkpoint. **All normal physical engine outputs remain inhibited.** It is not a complete Speeduino replacement or a hardware fabrication/vehicle release.

## Supported paths checked

- Measurement-profile validation, sensor conversions and supply compensation, persistent save/restart, corrupt-storage handling, stale-revision rejection and API authorization.
- Shared engine calculations, missing-tooth/cam phase handling, scheduler deadlines/cuts, tune storage, native transport and bounded diagnostics, through the existing sanitizer and host suites.
- Actual Chrome editing of eight-cylinder calibration, legacy migration, native-coherent export and offline own012 MSQ/CAS workflows. These virtual profiles do not add drivers beyond the fitted4+4 commands.
- UI pairing, cancellation, candidate approval, persisted unpair and requested LED states on an owned synthetic host. Native service tests cover authenticated telemetry and shared-bus LED fault/readback behavior; RF and optical output were not measured.
- Fresh `compact_n16r8_web`, `compact_n16r8_flex_dev` and historical `compact_a3_web` builds, each with the current UI verified inside the linked image. No device was flashed. Original build caches and source inputs were preserved.

Use **`compact_n16r8_web`** as the selected-module bench build. The flex development image requires its matching development wiring. The A3 build/package/manual are historical hardware records; A6/A7 and accessory layouts remain development drafts. Do not mix their wiring assumptions.

## Important boundaries

The current API/browser and native tests pass within those scopes. Target timing/electrical behavior, actual radio peers/range, module/socket/enclosure fit and environmental qualification remain unverified. A compiling image and native test do not establish physical engine operation.

The retained [engine comparison](engine-shaft-integration.md) still fails the reference's finite-step convergence checks. Supported online TunerStudio integration is unresolved; own012 is verified offline, and MegaLogViewer file compatibility has its documented limits. Missing decoder/control features remain listed in [feature coverage](engine-feature-coverage.md), with no implication that they were implemented for this checkpoint.

## Resume or reproduce

```sh
python3 scripts/build_firmware_preserved.py --output .cache/engine/NEW-CHECKPOINT-BUILD --environment compact_n16r8_web
CXX=g++ CC=gcc ECU_TEST_BUILD_ROOT=.cache/engine/NEW-CHECKPOINT-NATIVE sh scripts/test_firmware.sh
PYTHONPATH=tools CXX=g++ CC=gcc python3 -m unittest tools.test_web_config tools.test_radio tools.test_engine tools.test_engine_http -v
uv run --with playwright python tools/test_pairing_ui.py --output .cache/engine/NEW-PAIRING-UI
```

Use new output/state directories and free ports. The browser test requires installed Chrome and closes its own browser/server. The [configuration guide](web-configuration.md) and [tuning guide](../tuning/README.md) distinguish the current workflows from historical files. Further feature development requires an explicit resume; physical tests remain separate work.
