# Guarded switch inputs: development checkpoint

Target firmware now acquires the two SW2-J4-DRAFT1 contacts, binds coherent source-tagged samples into the controller, latches faults across skipped control observations and exposes bus/wiring diagnostics in the UI. Defaults make no I2C device requests. Source timestamps, readback/challenge checks, measured acceptance budgets and requalification are explicit. Selected web-build engine outputs remain inhibited.

The separate80x60mm THT accessory has a native schematic/routed PCB, candidate BOM, incompatible internal/contact connectors and a reviewed ground-return pour. **HOLD: no fabrication, physical engine, electrical/environmental, thermal or enclosure-fit qualification.** The expander selftest cannot qualify an analog conditioner or prove two-wire continuity. Fresh secondary-enabled coupled engine acceptance remains open.

- [Current hardware/wiring/debug guide](../../../hardware/switch-inputs/README.md)
- [Source bindings](source-bindings.json), [checks](checks.json) and [artifact manifest](artifact-manifest.json)
- [Independent software assessment](reviews/software/assessment.txt) and [review](reviews/software/review.json):12,278 assertions, including actual engine/switch services, skipped observations, reset/budget/fault races and UI provenance.
- [Independent architecture assessment](reviews/architecture/assessment.txt). The circuit review packet is under `reviews/circuit/`, with its own source bindings, manifest and standalone replay.
- [Native schematic](validation/cad/schematic.svg), [copper](validation/cad/copper.svg), [reference locator](validation/reference-locator/assembly.svg). The locator uses an annotation-only export copy; all serialized non-reference tokens and geometry match the unchanged production PCB. It is not a fit/assembly qualification.
- [Circuit results](validation/circuit/results.json):95 conditional ngspice cases and retained custom decks/vectors. Generic transistor/diode/clamp/supervisor assumptions are not manufacturer models. Bus-feed and carrier3V3-feed currents are separate. Steady18V experiments are not input ratings or automotive surge tests.
- Native/full existing Python tests, three additional stale-binding tests, eight installed-Chrome workflows and three Linux target builds passed. Static output-policy/ISR/USB audits do not establish actual timing, heap, stack or physical behavior.

The immutable software review copied the earlier secondary feature guide as context. The sole declared difference is the updated guide describing this implemented path and its prototype/physical gates; accepted software remains byte-identical. Original local review manifests are retained. Their publication projections explicitly list omitted manufacturer document/page copies and compiled executables/objects. The full local research cache remains intact. The circuit review has a separate standalone publication manifest.

Verification is archival by default. Later project changes do not rewrite this checkpoint. From the repository root:

```sh
python3 tools/verify_switch_inputs_evidence.py
python3 tools/verify_switch_inputs_evidence.py --check-live-sources
uv run --with numpy python tools/verify_switch_inputs_evidence.py --replay --ngspice .cache/tools/ngspice-package/payload/usr/bin/ngspice
```

Replay rebuilds frozen portable/actual-service independent probes in a temporary directory. The optional circuit replay requires the recorded ngspice binary and compares all95 result rows. Native KiCad/target builds and hardware measurements are separate operations. Nothing was flashed and no vendor message was sent.
