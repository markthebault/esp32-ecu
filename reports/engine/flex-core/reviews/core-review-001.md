# Independent flex groundwork review, freeze001

Scope: portable raw-edge acquisition and separate six-bin correction-factor core only. The source freeze is core-freeze-001/manifest.json. Header SHA256 12ad39ba8657667e37ddbae0492c9e89756d774db553ce410261a01b3a10ea26; parent tests7fb69ea5f3afba3366ed936dd4a3859dc1da45e67b492ee03f4d1bf1dade496d. No project/production source edits were made by this review.

## Findings

No new blocking defect found in this core freeze. The previously demonstrated invalid/Ready completed-sample-age defect is fixed: stale completed data is checked independently of last raw-edge age. Query-time reversal takes precedence over future-edge classification and produces a single fault for that query.

The pending-generation contract withstands an unobserved fault followed by full reacquisition, denies unobserved/superseded ACK tickets, and allows one ACK only after an invalid observation exposed that exact generation. ACK by itself cannot reconstruct a cleared series. Source/calibration changes discard old cycle sums and filter history; reconstructed frequency and low width use the same completed cycles. Repeated observations do not advance measurement time or filters.

## Executed verification

Both tests were built from the frozen include path with C++14, -Wall/-Wextra/-Werror/-pedantic, ASan and UBSan. Frozen parent505 checks passed. Independent2,101 checks passed, including an unequal-cycle rolling-window oracle at2/8/32 cycles; malformed/unavailable-source recovery; source changes and filter reset; configuration epoch/reset; hidden reacquisition and generation ACK races at the serialized API boundary; completed-sample staleness; monotonic timestamps crossing32-bit wrap and approaching UINT64_MAX; and six-bin correction boundaries/negative inputs. Compile/run commands, source/binary hashes and output are in core-test-results-001.json. All runs used an owned GCOV_PREFIX and GCOV_PREFIX_STRIP=0 before process startup. Near-UINT64_MAX timestamp tests do not imply that2^64 event/fault-counter exhaustion was dynamically exercised; those guards were source reviewed.

## Separate production fixture static review

The separate builder reuses108 original objects and the original HAL, replaces only the entry object, and reconstructs the exact original109-object numerical binary before linking. Independently verified565 original input hashes,109 final object hashes, all library/fixture-source hashes, fixture binary hash and exact original relink hash. Saved fixture-static-attestation-001.json. The original reference source pin and reviewed source hashes, both numerical binaries/manifests still match initial records; core-closure-source-verification-001.json records this.

This is static/build attestation only. Production raw-edge case execution/results remain to be reviewed. Native execution is not AVR/ESP32 vector timing or physical input proof. The fixture's main-time coverage redirect is a defensive measure; callers must still supply owned GCOV_PREFIX before startup. If this reviewer executes it later, a frozen binary copy within this review directory will keep its internal /proc/self/exe-based coverage path owned here.

## Open integration scope

No acceptance of engine Tune/application ordering, target capture/timer/ISR/queue, ownership pins/protected circuitry, storage/schema/migration, browser/TunerStudio, logging/radio/debug or hardware is implied. The future target worker must serialize Capture access and may ACK only after a completed control observation consumed the same invalid generation. Future input demand is OR(corrections enabled, secondary ETH condition dependency); corrections Off alone must not remove a required ETH producer. A protected/inverting stage must preserve the intended LOW-pulse temperature meaning. GPIO46 remains a boot-strap candidate requiring pre-application boot/download protection, not an approved allocation.

## Generated-coverage side effect disclosure

An earlier small production table-cache semantic probe unintentionally updated16 preexisting generated .gcda files in ../speeduino/.pio/build/native_code_coverage when library coverage flushed. The exact list/timestamps are retained in coverage-side-effect.json; no restoration/reset was attempted. Generated coverage is expressly excluded from every unchanged-source/cache statement. The original tracked production code and numerical binaries/manifests were independently checked afterward. Parent has been notified and will disclose this generated-counter change.
