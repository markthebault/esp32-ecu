# Expanded production boost reference checkpoint

The separate native Speeduino fixture now exposes sixteen real engine-output ports plus production boost PWM, raw ADC inputs and crank/cam callbacks. Independent review passed the fixture, adapter, provenance and audit scope. The full ECU goal remains active. Normal engine outputs remain inhibited and the fitted PCB still has four injector/four coil commands.

- `sources.zip`: thirteen-file source overlay on commit `64d5f46`, with reproduction and limits.
- `validation.zip`: build/generated-adapter identities, eight native test groups with 96 saved cases, unchanged independent review histories, 13 final tamper-rejection controls, finite-step analysis and the separate delta assessment.
- `runs.zip`: nine ordinary project/reference cases, the independent seven-cylinder case and two passive observer diagnostics. Each includes source/model snapshots; project shared libraries are retained so all twelve cases can be audited after extraction. Reference executables, object/coverage files and proprietary applications are excluded.

**The reference comparison is not accepted as converged.** Both reference step-refinement checks fail the unchanged 2% gate. The observer reproduces ordinary event/trace/capture prefixes and finds different cylinder/mixture outcomes near partial-to-full sync, without isolating a production bug. Native prescribed-shaft partition invariance is a separate, narrower result.

The delta assessment supersedes the earlier coupling review's unsupported protection-cap explanation. In both reference cap settings, raw ADC1023 is rejected and production MAP holds at47kPa with boost_cut0; their complete edge histories are identical. These runs do not compare a common recognized overpressure condition. The original assessments remain byte-for-byte unchanged.

Audits recompute before/after-halt mass, energy, fuel and heat balances, replay all sparse output edges and bound capture timestamps. A passing invariant audit does not establish controller equivalence, model calibration, pressure tracking or physical operation. Reference halt stops engine schedulers only; native boost status is reported separately from the simulation-ending valve cut.

For commands and assumptions see `docs/engine-expanded-boost-reference.md` in the source overlay. Coupled reference sensitivity, turbo/map matching, remaining engine features, protected PCB expansion, supported online tuning and target/physical qualification are unfinished. No physical engine, vehicle, electrical, EMI/surge, thermal, splash, RF or printed-fit qualification is claimed.
