# Internal cylinder-core checkpoint

The shared internal capacity-eight core executes1..8 even-fire four-stroke profiles. Public tune/browser/USB/radio/target interfaces and the PCB remain four-cylinder. This packet does not complete that feature or the wider ECU goal.

- 1296 motored timing cases pass across counts, strategies, orders, wheels, speed and closing angle. Maximum observed spark phase error0.07°; injector phase error2.115°, within the declared integer-capture/locked-closing-edge bounds. No sub-degree injector or physical timing claim.
- 7776 exact F64 four-cylinder controller observations match commit cdbd534. This is the stated legacy path, not every possible tune.
- 24 actual production Speeduino setup profiles disclose effective modes and schedule geometry. No shaft, sixteen-output GPIO or engine-plant execution is claimed for this new reference probe.
- Full sanitized firmware suite,3 public-boundary tests and13 tuning tests pass. Three fresh inhibited firmware builds pass ISR placement, linked policy and USB ownership checks. No target was connected or flashed.
- Independent review reproduces the original removed-cylinder ghost-edge fault and accepts the corrected configuration fence and core scope. Original failure evidence is preserved. Expanded public/UI/telemetry/target/hardware and generalized engine plants remain open.

[Design, limits and remaining integration](../../../docs/engine-cylinder-profiles.md) · [Summary](summary.json)

Archives contain sources, before/after raw observations, motored measurements, production setup readbacks, immutable reviewer-selected evidence and target build/static receipts. Target ELF/bin and upstream application/library binaries are excluded. Actual local target images are bound by SHA256 in the receipts.

```sh
python3 reports/engine/cylinder-core/verify.py --verify-only --output reports/engine/cylinder-core
```

Add `--repo .` only while live source bytes match this checkpoint. Integrity verification does not rerun the tests or establish physical/engine acceptance. Reproduction uses scripts/test_firmware.sh, scripts/build_speeduino_cylinder_geometry.py and tools/run_engine_profiles.py with the pinned native dependencies described in the design guide.
