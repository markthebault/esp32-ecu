# Independent secondary-table integration contract review

Baseline: project `f3b049eb695dadbadc7ff382547e572ecf03e695`, production reference Speeduino `9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20`. This is an independent review of the proposed schema8/own009 contracts against frozen baseline sources. It is not acceptance of the parent's evolving implementation. No root source, service, external checkout, board or flash was modified. All probes and records are in this cache directory.

## Assessment

The proposed8192-byte page and640-byte runtime layout are internally consistent and practical for the selected N16R8 build, subject to the gates below. Two required capacity changes are supported by actual data/source evidence: use a shared48KiB tune-document bound, and expand only engine_nvs from64KiB to128KiB at the existing0x210000 offset. A global limit increase alone is insufficient: memory failure, storage failure, all importers, historical identities and source-labelled diagnostics must agree.

## Independent measurements

Three proposed schema8 fixtures retain default Off/absolute Rules. I validate their old schema7 prefix through the frozen production project parser, then load their two secondary maps into the actual C++ Tune and run its complete validator. This proves that the map/scalar data satisfy current core ranges; it does not prove a future schema8 parser or actual engine behavior. ASan/UBSan reports no failure or leak in these probes.

| Fixture | Input bytes | cJSON canonical bytes | Native cJSON parse/print peak |
| --- | ---: | ---: | ---: |
| Default |8146|8146|139735|
| Dense F32 |33160|33460|190465|
| Dense subnormal F32 |37676|38094|229261|

Both dense legal core profiles exceed24KiB and fit48KiB. The cJSON live DOM is123178bytes in all three cases. Peaks exclude the input body, C++ Tune, allocator headers, active document, concurrent services and fragmentation. The full JSON has1889nodes. A cross-compiled ESP32-S3 symbol probe measures cJSON nodes40bytes versus64 on this host; subtracting that node-size difference gives a77842-byte target DOM estimate, not a target allocator measurement.

The independent natural-layout prototype gives the following sizes; the ESP32-S3 compiler confirms every planned entry below. This prototype is explicitly separate from the future implementation and must be replaced by actual candidate sizeof/build checks.

| Object | Baseline native | Planned native | Planned ESP32-S3 |
| --- | ---: | ---: | ---: |
| Secondary observation |44|64|64|
| RuntimeSample |400|528|528|
| Log row |416|544|544|
| Recorder256rows |106584|139352|139352|
| Tuning Session |5456|8272|8272|
| Tuning Reply |432|656|648|

The recorder grows32768bytes. It is a static global in engine_log_service.cpp, so the increase consumes static internal DRAM unless deliberately relocated. A16-row page grows from6744 to8792bytes; keep its checked heap allocation and row-at-a-time target JSON/MSL streaming. Do not construct a full paged JSON DOM on target merely because a host sanitizer fixture can do it.

The selected actual sdkconfig enables octal PSRAM through malloc, with16384-byte internal allocation preference and32768-byte internal reserve. That makes native-versus-target heap comparisons nontrivial. Generic A3 defaults do not enable those selected PSRAM settings. Fresh linked image/static budgets and actual minimum heap/largest block/task-stack/runtime-load tests remain necessary; a successful compile or the estimated DOM size is not runtime acceptance.

## Binary page and framing

The page ranges are contiguous and nonoverlapping: old prefix0..5375; fuel Rule5376..5411; spark Rule5412..5447; reserved5448..5503; fuel map5504..6655; spark map6656..7807; zero tail7808..8191. Each Rule is five U32 enums, two F32 scalars and U32 channel/polarity. Each map is16 RPM,16 load and256 cell F32s. Retain the old reserved5176..5375 bytes as zero too. Decode full U32s before narrowing; a channel257 must not become1 and polarity2 must not become true.

Runtime keeps the416-byte prefix, adds80-byte fuel/spark observations at416/496 and reserves576..639. Each observation has nine F32 values at0..35, flags at36, six U32 codes at40..63, U64 observed_us at64..71 and zero72..79. A full640-byte read is647 framed bytes including status and CRC. Maximum256-byte writes remain269 framed bytes, below the existing1024-byte USB rings. Stack temporaries and actual sustained USB throughput are separate unverified concerns.

Keep own008 INI/layout/codec metadata and defaults-v7 as immutable records. Q must identify own009; do not expose expanded pages under own008. Prefix preservation means stable field locations/semantics and byte-exact behavior for corresponding legacy configurations, not that a newly active secondary result must have identical proposal bytes. New whole-page CRC length is intentionally different; origin stays read-only at268 and CAS/storage activation remains atomic.

## Migration and operator traps

1. Separate LOAD_SIGNATURE/has_load from current own009/has_secondary. The baseline importer uses not-current as the test for old20..120 VE bounds. Renaming SIGNATURE alone would wrongly reject valid own008 coefficients0..255 and can drop its configured load/AFR fields. Own001..007 retain their earlier F32-qualified bounds; own008 and009 use the supported wider coefficients. Both browser and Python importers need the same capability ladder.
2. Schema1..7 migrate in a private tree to neutral Off secondary data, retaining earlier table/source settings, revisions and old stored bytes until an explicit successful save. Spark's default input channel is1, not Rule{}'s channel0; construct the full Config default. Allocation failures during any migration addition must discard the private candidate and preserve runtime/storage.
3. Preserve independent mode/source/axis/cell-meaning metadata. A source or mode selector cannot silently change axes or reinterpret degrees, percent multipliers or additive percentage points. Keep cells while presenting explicit review/acknowledgement or clearly named neutral replacements. Validate inactive stored tables too. TunerStudio should expose both selectors/bases; incomplete combinations fail one whole-page burn, not partially activate.
4. Update every bound: engine_limits/storage maximum, native host load/save/callback buffers, HTTP body/error messages, embedded defaults, migrations, generated Document header, MSQ/current definitions and fixtures. Browser import/MSQ64KiB limits should be retained only after actual worst-case own009/application roundtrips fit them. Shared parser depth8 is sufficient for the proposed nesting, but malformed/duplicate/unknown/nonnumeric cases and allocation failures still require tests.
5. Target has no protected switch or ethanol producer yet. Do not fabricate defaults as healthy inputs. Host synthetic switch fixtures must force Synthetic source; configuration data cannot authorize TargetProtected. UI must visibly disclose unavailable target input modes and failure reasons until acquisition hardware/driver is implemented.

## Diagnostic contract

Capture all Rule metadata with the completed control observation rather than reading the current editor/active tune later. A stopped/faulted step can have available selection metadata but no evaluated composition. Off/evaluated results may have a known primary/combined value but no secondary lookup, coordinate, condition or switch. Unknown numerics stay null/NaN; raw and debounced booleans require explicit source/validity/qualification/known state. An absent producer must not display a fabricated released switch.

Raw sample valid=true can coexist with consumer input_qualified=false because of debounce, stale/future/reversed timestamps or a configuration reset. Pending level can be known before the initial stable level is qualified. Preserve observed_us exactly as a JSON decimal string and two U32 wire parts; generic application plotting precision for large integers remains a separate limitation.

Do not force observed_us<=control_us in an observation-fixture validator: a future raw switch timestamp is itself diagnostic evidence of the recorded input-time fault. Similarly, do not reconstruct active from logged F32 condition_value>threshold. The core compares F64 physical input; a just-above input can round to equality in F32 telemetry while a true active flag remains legitimate. Validators may enforce domains and structural availability without inventing hidden filter history.

Append/version MSL fields consistently across native target, browser collector and direct SIL exporters. Preserve the current prefix/order where promised, record primary/corrected/secondary/combined values and units, source, condition, raw/debounced state, age, active/pending/evaluated and reasons. New data must survive strict native/browser fixture roundtrips and real MegaLogViewer file opening; absent legacy secondary observations stay unknown, not fabricated Off measurements.

## Radio

Current schema3 is already250bytes with218-byte HMAC body. Only bytes90..91 are reserved. Do not put new status into schema3 without version negotiation or silently publish a combined result as an entirely primary-table model. Gate schemas1..3 whenever either secondary mode is non-Off, including a currently inactive conditional; explicitly disclose existing sensor-stream fallback.

One viable compact schema4 option uses byte90 for two3-bit modes plus two active bits; byte91 for two2-bit secondary sources plus two availability and two evaluated bits. This fits without moving old load fields or the HMAC. It cannot carry full secondary values, input health/age or fault reasons; those remain web/log diagnostics and the screen contract must say so. Negotiate4, preserve old transcripts/byte layouts, reject reserved mode/source codes/inconsistent flags and test authenticated changed-byte, stale-counter, replay, lost-ACK and fallback behavior. This is a proposed contract, not an implemented receiver or RF result.

## Storage capacity

The actual installed framework package is3.50500.0 (ESP-IDF5.5.0). Its writeItem writes a new blob version completely before invalidating the prior version. PageManager reserves a free page for compaction. Page entries are32bytes,126 per4096-byte page, and blob chunk payload is at most4000bytes. Two changed48KiB documents require at least26chunk pages before index/namespace/compaction headroom. The existing64KiB partition has16pages and cannot provide that capacity. A128KiB partition has32pages and is a reasonable capacity design with margin. This is source/capacity inference, not proof of every fragmentation/power-loss case. The project stores blob document bytes without a NUL terminator; adding one would not change this chunk count.

Keeping start0x210000 and growing size to0x20000 ends at0x230000, within both8MiB and16MiB flash and without moving sensor/pairing NVS, PHY or the2MiB factory app. Do not erase flash or move offsets as a side effect. Existing64KiB content plus added flash-range state, repeated near-limit rewrites, failures/reboots and real power loss need acceptance. The current API-model fake alone cannot prove production NVS durability. Espressif's [NVS documentation](https://docs.espressif.com/projects/esp-idf/en/v5.4.1/esp32s3/api-reference/storage/nvs_flash.html) describes append-before-invalidate storage and the need for free space; frozen installed source is authoritative for this review's exact algorithm.

## Required acceptance before claiming this integration ready

- Actual candidate schema8/own009 native roundtrip for all modes/sources/meanings, full-scale/dense/subnormal data, wrong shapes/types/duplicates/enums/reserved bytes, and every legacy JSON/MSQ identity. Exact old prefix/default control/wire replay, old stored bytes/revisions retained, stable-origin CAS conflicts, full-tune invalid-combination rejection and checked OOM/storage failure/retry behavior.
- Source-bound native/browser observation and MSL parity for available/unavailable/evaluated/fault/startup/Off samples, just-above F32-rounding thresholds, input known/unknown states and future/reversed timestamps. Unknowns and source domains must survive export/import without false healthy values.
- Real browser edits, mode/source acknowledgement, save/reload, stale-editor conflict and JSON/MSQ import/export; actual offline TunerStudio complete-page roundtrip and MegaLogViewer new fields. Online TunerStudio acceptance remains separately unresolved.
- Selected and generic web target image/IRAM/static budgets, runtime block647-byte framing and bounded buffers, fresh memory object sizes; retain explicit runtime heap/stack/USB/timing/HIL holds. Update recorder static budget deliberately rather than dropping fields/rows merely to pass an old assertion.
- Authenticated radio negotiation/gating or schema4, old schemas byte-exact and disclosed fallback. No RF/device qualification inferred.
- A protected two-input accessory, bounded acquisition/config readback and actual producer health/source behavior remain necessary for input-mode hardware. Secondary-enabled independent-plant/reference-loop switching, actual pulse/ledger audits and selected half-step runs remain necessary for the complete feature. This contract review does not close those gates or broader Speeduino parity.

Reproduction: run_review.py compiles the independent native/ESP32-S3 layout prototypes and three sanitized legal-core/JSON sizing cases from frozen sources/fixtures. It creates a fresh replay directory and never rewrites root sources. The returned execution.json records exact compiler commands, versions and results. Existing probe outputs and source/fixture hashes are retained. No engine, HIL or physical acceptance is claimed.
