# Independent idle integration review

This review covers the uncommitted schema4 idle configuration, own0054992-byte page/256-byte live codec, JSON/MSQ migration, generated INI and browser helpers, and observation/MSL integration. It does not reaccept the PWM/control kernel, actual target owner, physical driver, simulator calibration, radio behavior, or TunerStudio online support. Root performed separate actual application QA. This reviewer used native shared C++ validators/transactions, real headless Chrome for browser semantics, and isolated ASan/UBSan allocation probes.

**No remaining concrete high/medium correctness finding was identified in this bounded integration review after the fixes below.** This is not a feature-parity or vehicle-readiness declaration. The initial files are preserved under `snapshot/`; reviewed final versions are under `final-snapshot/`, with immutable SHA256 manifests.

## Findings and fix verification

1. **Medium, fixed: current INI map editors pointed at nonexistent calibration pages.** The initial own005 INI declared nPages1 but Spark/Lambda/cylinder tables referenced2..7. The last TableEditor argument is the calibration page, confirmed by the bundled primary EFI Analytics definition comment and upstream Speeduino page mappings. All seven current editors now reference1. Historical definitions remain records. `layout-recheck.json` asserts the corrected current mapping. Actual application burn/read acceptance remains part of root's application QA.

2. **Medium, fixed: browser collector accepted malformed idle availability.** The initial new guard interpreted0/null/missing `idle.available` as false and committed the page when all six values were null, although the native observation parser rejected each payload. The guard now requires a boolean for a present idle object. Independent Chrome probes reject0/null/missing/"false" atomically and match the native parser, while valid observations still export correctly. An absent entire idle object remains compatible with historical observations.

3. **Medium, fixed: own005 offsets depended on current JSON key insertion order.** Initially SCALARS/ARRAYS were derived from defaults iteration with only counts checked. A semantically identical sorted JSON object moved frequency_hz4772→4812 and changed15 scalar offsets without changing the005 identity. The explicit ordered field tuples and exact default key/shape assertions now preserve scalar and array offsets when the JSON keys are reordered. Original mapping evidence is retained in `order-dependence.json`; `layout-recheck.json` verifies the fix. Future incompatible layouts still require a new signature.

4. **Medium observability gaps, fixed:** the direct SIL MSL action previously discarded every new idle/PWM/valve metric, and the own005 TunerStudio datalog omitted explicit availability/source/age. The SIL003 exporter now appends fields while retaining the19-field prefix; it separates controller observations, dispatcher state and synthetic valve estimates. A48-field fixture verifies full64-bit counters and NaN/availability distinctions for old rows without idle data. Current INI datalog explicitly includes iacAvailable, dataSource, snapshotAgeMs and supporting validity/session metadata.

5. **Low, fixed:** current own005 master idle target/KP/KI had generic−1000..10000 editor bounds and missing gain units. Current editor limits now match600..1500RPM and0..0.2, with %/RPM and %/(RPM*s). This changes current presentation, not wire offsets or the historical codec. Coupled curve/duty/target constraints still rely on the authoritative native whole-tune validator; the backend returns a generic invalid-tune result rather than a field-level explanation.

## Independent checks completed

- The frozen schema3 defaults are semantically equal to `cbfbe4a:config/engine/defaults.json`.
- For schema1/2/3 JSON, forced old idle_enabled=true migrated to false, retained the revision, supplied fixed new idle defaults with equal float32 values, and preserved original stored bytes until Save. Extra/missing/unknown schema fields and coupled target/curve violations were rejected even with idle disabled.
- Four historical MSQ signatures with forced old idle_enabled="On" migrated to disabled defaults. Real Chrome imports were also tested against an editor with enabled idle, frequency222 and nondefault curves: none of that new idle context leaked into the historical import. Supported legacy trim data remained handled by the shared import path.
- Current own005 MSQ browser export imported through the native Python/C++ path. Every idle scalar, every curve, algorithm and all master idle fields changed together survived20 native page chunks, whole-page burn, persisted reload and MSQ roundtrip with equal float32 payloads.
- Ninety-six nonfinite/out-of-range/reserved-byte binary variants were rejected. Exact4992-byte page and256-byte live read boundaries, the40-byte live extension, out-of-bounds reads, successful repeated burns, a stale concurrent writer and stable session-origin revision were checked. Invalid commands did not mutate the active tune.
- Browser/native observation exports agreed on all91 headers and units. IdlePidUpdates18446744073709551615 and SnapshotSequence9007199254740993 remained exact strings in MSL. The new metadata does not convert these counters through JavaScript Number.
- ASan/UBSan fault injection covered4000 cJSON allocation budgets on schema3→4 canonicalization:2485 clean failures,1515 complete migrations, zero tracked leaks. A forced on_off→closed_loop string-growth allocation failure affected only the private candidate document. These probes do not exhaust ESP32 heap fragmentation or arbitrary C++ allocator failures.
- Formatter stress cases fit the2048-byte output buffer:1804-byte MSL header and837-byte row. The row deliberately used extreme formatter inputs and is not a tune/sensor acceptance test.
- Current own005 offsets remained unchanged after isolated reordering of the defaults object. All seven table editor page references, availability/source/age datalog fields, and current idle master bounds/units were rechecked.

Legacy C++ migration may print a float32 default such as derivative_filter_s as0.10000000149011612 while a freshly loaded JSON default prints0.1. The actual float32 control value is equal; comparisons above intentionally compare wire float32 semantics rather than treating this decimal spelling difference as a control mismatch.

## Reproduction and evidence

From the repository root:

```
python3 .cache/engine/idle-integration-review/probe.py
uv run --offline --with playwright python .cache/engine/idle-integration-review/browser_probe.py
```

`alloc_probe.cpp` builds with the repository's ESP-IDF cJSON source and `-fsanitize=address,undefined`; the exact compile/run commands and output are in `results.json`. `python-probe.json`, `browser-probe.json`, `layout-recheck.json` and `sil-log-recheck.json` retain assertions/results. Initial and final source snapshots allow auditing fixes even if the working tree advances.

The tests establish configuration, codec, transaction, browser parsing and logging behavior in the reviewed paths. They do not establish physical timing, actual GPIO voltage, valve opening/current, thermal suitability, engine calibration, online vendor acceptance, or vehicle operation.
