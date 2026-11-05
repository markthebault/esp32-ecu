# Coherent flex radio software evidence

Negotiated engine schema5 sends a250-byte base and232-byte full flex extension, each authenticated with the existing full32-byte engine key. The extension binds the exact base HMAC. Both parts must complete before display, ACK or engine liveness. Schemas1..4 retain their exact bytes and required-flex sensor fallback.

One immutable sender pair per peer retains its original time across SDK failures and expires after250ms. The receiver holds at most two sequences for250ms from their first fragment; duplicate fragments cannot extend that deadline. Expiry, eviction and authenticated conflicts retire sequences separately from completed ACK state. Raw-sample age includes original producer age, fragment wait, the stated clock/transit allowance and local elapsed. New control/ADC packets and fresh clock queries cannot renew an old raw sample. Unknown age stays unknown.

Sensor ACKs no longer mask a missing complete-engine ACK. The browser labels those states separately and clears them on HTTP failure. Required invalid or expired flex requests red blinking at zero RPM and while a snapshot is held. This is an advisory software policy, with no measured physical LED or CPU-health claim. The datagram budget remains20/s per peer, normally8complete schema5 observations/s.

Retained checks include:

- 1,049 ASan/UBSan pair/age/policy assertions and81 assertions around actual sender/handler functions in native SDK API models, plus the full native suite.
- 131 configuration/API/control/radio regression cases,15 new receiver cases and every482 individual unauthenticated byte-tamper positions.
- Actual native query/update/base/flex/ACK bytes consumed by the Python receiver; flex qualification expires while base data remains fresh. Owned Chrome checks cover partial/complete/missing ACKs, malformed tuples, HTTP failure, escaping and mobile widths. Existing flex/semi/LED browser checks also pass.
- 27 fixed-gasoline plant cases across three strategies, including exact neutral causal controls, missing input and dropout cuts. This matrix does not execute upstream Speeduino or model ethanol combustion.
- Four preserved firmware builds, four ISR and output-policy audits, three USB ownership audits, exact compressed ELFs and app images. Current HTML is mapped into all three web images; the timing-bench image excludes it. These are static checks without target execution.

Independent review accepted31 implementation paths, then a separate UI/harness recheck produced33 effective accepted paths. Own probes include1,088 sanitizer assertions,21 receiver cases,42 additional actual-source sender checks,35 UI helper checks,24 failure/navigation/recovery checks and417 legacy vectors. The two105,282-byte legacy captures are byte-identical. Independent review excludes final target builds, actual Chrome, packaging and physical behavior. Raw generated reviewer binaries/objects are omitted with hashes; their source, command/dependency receipts and original cache copies remain.

`summary.json` binds final source snapshots. `build/` retains source/cache receipts and exact linked artifacts; `audits/adapters.json` discloses only the build-path substitution used for policy/USB checks. `native/` contains native API-model frames/readback; `browser/` identifies their use. Earlier failed compiler/test/browser-discovery attempts are retained in `validation/parent-logs/` and reviewer history. A regression fixture that rewound time after an expired reply now asserts rejection and recovery through a fresh timed query.

Verify or replay without a device:

```sh
python3 -B tools/verify_flex_radio_evidence.py --check-live-sources --replay
```

Replay copies frozen sources into a new owned cache directory, executes sanitizer pair/service tests, compares all actual frame/readback bytes, runs receiver/legacy tests and repeats four ISR audits. It requires the installed native/ESP32 toolchains, OpenSSL and the hash-matching pinned cJSON dependency. It never flashes or writes into the frozen packet.

The selected N16R8 physical engine outputs remain inhibited. No ESP-IDF task, real radio exchange, screen application, physical LED, USB session, target timing/HIL or engine was exercised. Protected GPIO38 circuitry, PCB/case integration, ethanol-aware plant calibration, online vendor support and wider Speeduino parity remain open. Earlier frozen packets and pinned production comparisons are unchanged. Retaining the current default PlatformIO cache does not recover historical caches lost in the earlier direct-build incident.
