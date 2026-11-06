# Authenticated boost telemetry checkpoint

Schema6 carries BASE, FLEX and BOOST as one authenticated observation. Only the complete set may update display/liveness or be acknowledged. All three parts preserve the original source/time context; both extensions bind the full BASE MAC. Schemas1..5 retain exact bytes for representable legacy samples.

Independent review found metadata starvation. Reserving both metadata and sensor slots fixes it; a metadata-only mutation still fails. Final review also verifies the corrected no-ACK sentinel, clock-order readback and browser states. The15s/four-peer native sender model supplies all6 metadata channels,30 sensor and30 metadata frames per peer,80 complete observations per peer and a maximum200ms assembly span within the250ms deadline.

Validation includes6972 final actual-service assertions under ASan/UBSan, independent codec/state/clock and legacy-byte comparisons,212 broader Python tests,89 final relevant tests,13 Chrome radio checks and the reviewer's current boost-page rerun. The earlier full native suite is included; final service/review evidence supersedes its radio portion. Three fresh Linux firmware builds pass static engine-inhibition, interrupt-placement and USB-ownership audits. Build001 is superseded by build002 after the ACK-age fix; no rejected/intermediate firmware is shipped here.

The archives contain changed/reviewed sources plus the base-Git patch, bounded independent evidence, validation and three inhibited firmware images/ELFs. All payloads are individually hashed. `summary.json` binds source hashes and accepted image identities. The frozen review retains the original starvation witness and the failing partial fix.

```sh
python3 reports/engine/boost-radio/verify.py
python3 reports/engine/boost-radio/verify.py --repo .
```

The second command additionally compares the current project sources; future engineering may legitimately differ. Reconstruct sources from base commit74a186d721b50c6eec1fc7a89e80fda082c0dea8 and `reconstruct.patch`, or overlay the archived project files, then use the reproduction commands in `docs/espnow-engine.md`.

This is an ECU sender/reference receiver contract. No actual screen application, RF/RTOS timing measurement, device flashing, physical valve actuation or vehicle/environmental qualification is provided. Physical engine outputs remain inhibited. Coupled turbo/wastegate simulation, protected boost hardware, desktop tuning acceptance and broader Speeduino feature coverage remain unfinished.
