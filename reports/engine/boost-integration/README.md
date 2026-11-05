# Partial boost integration

This checkpoint connects main-engine pressure protection, browser configuration, own011 tuning exchange, coherent diagnostics and virtual boost PWM. The broader Speeduino feature goal remains incomplete. Physical engine outputs stay inhibited; no boost GPIO is allocated.

The default remains NA with a110kPa guard. Schema10 adds explicit boosted-pressure configuration. Own011 has one12288-byte page and1152-byte live block. Coherent data schema2 and MSL008 add boost decisions and lossless counters. Old formats remain retained and migrate with boost disabled.

Verification includes173 Python regressions, the full ASan/UBSan native suite,512 author integration assertions, actual Chrome editor/logger flows, six actual native diagnostic replays and96 corrupt-column controls. Independent reviews cover4422 core assertions,48000 unchanged legacy observations, actual target owner/sync tests, indicator/radio policy and real pinned NVS recovery code. Counts describe separate scoped checks, not physical qualification.

The NVS negative control reproduces a lost blob at one of360 injected flash-error positions. The project correction preserves complete old/new values through all360 cases,800 normal writes at four sizes and120 nonblob/legacy-format cases. The original failure, complete ledgers, modified-file notice and exact source hashes are retained. This is a software flash-error model.

All three accepted Linux builds pass static ISR placement, internal boost-state placement, output-inhibition, USB-ownership and project-local NVS-selection checks. The first build attempt failed ISR placement and remains rejected evidence. Accepted firmware is a development record; runtime timing, heap/stack peaks and physical electrical behavior remain unmeasured.

| Archive | Contents |
| --- | --- |
| `sources.tar.gz` | Changed/new source files layered on the manifest's base Git commit |
| `independent-reviews.tar.gz` | Explicit reviewer whitelists, source snapshots, tests, findings and rechecks |
| `validation.tar.gz` | Final test logs, browser exports/screenshots, native replay ledgers and build/audit records |
| `inhibited-firmware.tar.gz` | Accepted inhibited images and exact compressed ELFs |

`manifest.json` binds all four archives and1556 payloads by SHA256. Verify without extracting:

```sh
python3 tools/package_boost_integration.py --output reports/engine/boost-integration --verify-only
```

Remaining work includes authenticated boost screen telemetry, a coupled turbo/wastegate comparison with production Speeduino, protected driver/carrier/enclosure design, actual own011/MSL008 desktop application checks and physical HIL. Existing screen formats cannot encode a new boost-profile observation; a previously prepared NA pair can finish within its original context and bounded lifetime. The current NA regression plant does not validate turbo behavior.

See [the integration contract](../../../docs/engine-boost-development.md) and [feature coverage](../../../docs/engine-feature-coverage.md).
