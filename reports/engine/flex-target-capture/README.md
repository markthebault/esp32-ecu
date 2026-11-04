# GPIO38 target capture software evidence

The separate `compact_n16r8_flex_dev` profile now connects both-edge MCPWM capture to the serialized controller owner. Configuration, diagnostics, command expiry and completed-control fault ACK share the same source/version contract. Historical/default profiles retain their original GPIO38 LED wiring.

This is a software development checkpoint. The protected flex circuit, PCB/case integration, sensor selection, target execution/HIL and physical qualification remain open. No device was flashed. The selected profile keeps physical engine outputs inhibited. Schema9, own010 and MSL007 numerical layouts remain unchanged; negotiated flex screen telemetry and online vendor support remain open.

The owner retains actual producer calibration/revision and fences publication against context, ingress generation and arm boundary. Immutable commands retain their original sample expiry, Capture fault generation and publication revocation floor. New samples cannot renew old demands. Invalid or rejected publications permanently revoke older queued commands. Both fuel and spark must be cut to bypass the flex guard. Flex edges never refresh crank/cam producer age.

The fixed earlier sync-bracket epoch preserves pulse differences under changing callback latency. Only channel2 interrupt/status bits are masked or cleared. The hardware has one latch per channel and no FIFO. Software acceptance cannot establish lossless capture or target latency. Intentional rearm clears waveform continuity while retaining monotonic clocks, source and fault history.

The retained checks include:

- 12,806 portable owner/clock assertions under ASan/UBSan.
- 27,665 assertions around the actual target and control translation units using deterministic SDK/RTOS API models, plus allocation/register/enable failure modes. These models do not execute ESP-IDF or silicon.
- The full native suite,57 configuration/API/log tests,27 fixed-gasoline SIL cases, existing flex editor/log tests and actual Chrome acquisition fixtures with46 malformed/stale/missing/escaping cases. The SIL model does not implement ethanol chemistry.
- Four preserved firmware builds with unchanged source/default-cache checks, exact compressed ELF archives and complete HTML/JS mapped into the three web images. Four policy/ISR audits and three USB ownership audits pass. The draft capture build has six ISR roots,31 reachable functions and no floating-point instructions in the audited closure. These are static checks, not runtime or physical qualification.

`summary.json` binds the source snapshots. `build/summary.json` binds the losslessly compressed ELFs and app images. `audits/` retains the unmodified policy checks with explicit build-path adapters. `native/` contains actual-service API-model fixtures; `browser/` discloses their use. `plant/` retains the27 fixed-gasoline runs. `validation/earlier-attempts/` preserves failed discovery, selector, linker and regression attempts; final sources and final runs are authoritative.

The current default PlatformIO cache was retained and compared before/after each isolated build. This does not recover raw caches lost during the earlier direct-build incident documented in the shared-status-LED packet. Earlier frozen reports and production Speeduino reference evidence remain unchanged; this increment did not execute upstream Speeduino.

Verify the packet and optionally replay the frozen owner/actual-service tests and four ISR placement audits:

```sh
python3 -B tools/verify_flex_target_evidence.py --check-live-sources --replay
```

Replay uses the bundled cJSON and source snapshots plus the installed C++/Xtensa toolchains. It needs no device, network, upstream execution or running service. Browser reruns are documented in the source guide. Independent functional review is retained in `reviews/independent/`; packaging verification is the parent agent's scope.

The unchanged radio layer still gates generic controller-fault indication on RPM>0. Indicating a required flex failure at rest, along with negotiated flex screen telemetry, remains separate goal work; the capture review does not accept new radio/LED behavior.

Independent functional review accepted47 bound paths with no open findings in its stated scope. Own probes include2,548 protocol assertions,117,937 interval checks across7,128 waveforms and11,000 legacy-map comparisons, Capture-only queue/floor regressions,39 UI checks, actual-service and ODR tests,56 final ELF/source checks and a rerun of the draft ISR audit. Raw generated reviewer executables/objects are omitted from this curated packet with their hashes; original cache copies remain. Packaging/verifier review is excluded.
