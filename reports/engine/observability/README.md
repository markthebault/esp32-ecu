# Reviewed engine telemetry and logging increment

[Validation summary](validation-summary.json) records 100 Python tests, 10 native binaries (including 117 control scenarios), 36 Chrome checks, three firmware builds and three paired controller/plant comparisons. The wider Speeduino feature goal remains active. Physical engine outputs remain inhibited on the selected N16R8 build; no board was flashed or physically tested.

- [Usage, APIs and limits](../../../docs/engine-observability.md)
- [Engine screen protocol](../../../docs/espnow-engine.md) and [public deterministic wire fixture](wire-fixture.json)
- [Independent telemetry review](independent-telemetry-review.json), [logger/target review](independent-logger-review.json) and preserved [supplementary probes](independent-probes/)
- [External-plant and network validation](scenario-validation.json), including actual pinned Speeduino algorithms on independent copies of the same uncalibrated plant
- [Browser collection/export tests](ui-tests.json), [desktop UI](engine-log-desktop.png) and [mobile UI](engine-log-mobile.png)
- [Actual browser MSL](browser-collected.msl), [lossless source JSON](browser-collected.json), [gapped collection](browser-gapped.msl) and [retained window](device-retained.msl)
- [Unchanged MegaLogViewer desktop check](megalogviewer-check.json), [field plots](megalogviewer-engine-fields.png), [source header](megalogviewer-header.png) and [missing-lambda rendering caveat](megalogviewer-missing-lambda-caveat.png)

Native/HTTP/browser evidence checks logical behavior and source fidelity. The network queue is a software loss/delay/replay model. The research plant has verified MVEM air-path code and local empirical combustion/free-shaft behavior. Neither establishes physical RF, electrical, engine, vehicle, environmental or enclosure qualification. TunerStudio's actual live connection remains unresolved.

Supplementary reviewer probes are preserved verbatim and retain original workspace/cache paths. Public tests in `tools/test_engine_observability.py`, `tools/test_engine_observability_ui.py` and `scripts/test_firmware.sh` are the maintained reproduction entry points. Run probe copies in a temporary directory to preserve this evidence. [Source hashes](source-hashes.json) and [artifact hashes](artifact-hashes.json) identify the reviewed files.
