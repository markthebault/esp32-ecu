#!/usr/bin/env python3
"""Assemble a new immutable checkpoint after independent acceptance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(root, output):
    root, output = root.resolve(), output.resolve()
    cache = root / ".cache/engine/flex-ingress"
    validation = cache / "run-005"
    review = root / ".cache/engine/flex-ingress-review"
    independent = json.loads((review / "review.json").read_text())
    assert independent["accepted"] is True and not independent["open_findings"]
    summary = json.loads((validation / "summary.json").read_text())
    assert summary["compiled_frozen_non_system_inputs"] and summary["input_and_tool_hashes_stable_before_after"]
    for row in summary["sources"]:
        assert sha(Path(row["path"])) == row["sha256"] == sha(validation / row["snapshot"])
    target = root / "firmware/.pio/build/compact_n16r8_web/firmware.elf"
    expected_target = "10c99de1593a9114f8ffb7346ba62165a55876599ffa19ce0fb268fcb2ca48c5"
    assert sha(target) == expected_target
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(validation, output / "validation")
    shutil.copyfile(Path(__file__), output / "validation/assemble.py")
    shutil.copytree(review, output / "reviews/ingress", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    pins = root / ".cache/engine/flex-target-review"
    destination = output / "reviews/pin-preflight"
    destination.mkdir()
    for name in ("preflight-review.json", "recommendation.txt", "primary-documents.json", "source-freeze.json", "source-facts-and-calculations.json", "prior-coverage-side-effect.json"):
        shutil.copyfile(pins / name, destination / name)
    for name in ("project-snapshots", "sdk-snapshots"):
        shutil.copytree(pins / name, destination / name)
    shutil.copytree(pins / "gp7-followup", destination / "gp7-followup", ignore=shutil.ignore_patterns("*.pdf", "*.txt"))
    regression = output / "regression"
    regression.mkdir()
    for name in ("native-regression-001.log", "previous-integration-verify.log", "previous-core-verify.log"):
        shutil.copyfile(cache / name, regression / name)
    readme = """# Bounded flex capture ingress checkpoint

This checkpoint adds an integer-only64-edge ISR handoff, monotonic context/time fences, queue loss accounting, local suppression decisions and exact offered-fault ACK/retry rules. It does not connect a peripheral or a target producer. The standalone ring occupies2808 bytes on both native and Xtensa builds.

The native suite passed62,297 sanitizer assertions, including injected waveform events through the actual capture/control cores. Independent review passed160,202 additional invariant/adversarial assertions, with U64 exhaustion seeding and30,000 randomized lifecycle operations. The full native firmware regression also passed. These are native tests, not real target readings or engine operation.

The standalone Xtensa ISR-root probe has1442 bytes and557 decoded integer instructions, no calls/FPU instructions, IRAM code/literals and DRAM state. Three owned negatives reject mapped flash, an external call and an unmapped flash-range pointer. The last case exposed an initial audit-tool bug; its raw reproduction and closure remain in the review folder. This is not a real SDK callback or latency/interrupt-interference measurement.

The runner discovers non-system dependencies, freezes them before compilation, compiles those copies and verifies originals/snapshots/compiler tools afterward. The22 selected source snapshots, command outputs and four standalone ELFs are retained under validation/. Compiler system headers/libraries are part of the recorded toolchain environment, not a bundled hermetic toolchain. Review freezes and probes remain under reviews/ingress/.

[FLEX-G38-DRAFT1](../../../hardware/flex-input/README.md) prefers GPIO38 capture and a new MCP23008 at0x21 for an ordinary advisory RGB LED, sharing one bounded bus owner with switches at0x20. Existing GPIO38 WS2812/ARM builds are electrically incompatible with the proposed input and remain unchanged. GPIO45/46 stay NC. Required switch challenge/full-byte0x7F IODIR guarding remains unchanged. The independent pin review and GP7 correction rationale are retained under reviews/pin-preflight/.

Large primary-document PDFs are not duplicated here. Their exact URLs/hashes are in the saved primary-document and GP7 records; original downloads remain in .cache/engine/flex-target-review/ and .cache/engine/flex-target/sources/. SDK/project source snapshots supporting the documentary review are bundled. This architecture is not a circuit, CAD or manufacturing release.

The trusted target owner must still implement source-local interrupt masking/clearing, clock reads under the same lock, separate floating-point Capture invalidation, real calibration/revision binding and completed-control ACK bridging. It must retain context/generation/arm boundary when popping, then atomically revalidate and publish after outside-lock floating-point work. A mismatch discards the result and restarts the separate Capture series. Per-arm callback windows are not global IRQ budgets. Masked holdoff does not prove electrical quiet. Required flex currently inhibits target control because no target producer exists. An I2C-latched green LED cannot prove a live CPU or light output.

Physical engine outputs remain inhibited. The protected frontend, new carrier/LED worker, PCB/case integration, actual capture/load/HIL, negotiated flex radio, ethanol chemistry, online vendor support and full Speeduino parity remain open. No device/eFuse/firmware flash, upstream production execution or external message occurred in this increment. Prior evidence packets remain unchanged; the earlier disclosed generated coverage-counter side effect is preserved, not erased.

Reproduce current-source ingress checks with a new output directory:

```sh
python3 -B scripts/check_flex_ingress.py --output NEW_DIRECTORY
CXX=g++ sh scripts/test_firmware.sh
python3 -B tools/verify_flex_ingress_evidence.py --replay
```

The verifier checks frozen artifact/source/review bindings and replays the frozen parent native scenarios plus all four saved ELF audits. It does not rebuild or execute a target image or Speeduino. Later source changes can legitimately differ; --check-live-sources is an optional current-checkpoint comparison.
"""
    (output / "README.md").write_text(readme)
    provenance = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "base_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip(),
        "native_regression_exit_code_observed": 0,
        "selected_existing_elf_sha256": expected_target,
        "existing_target_image_unchanged": True,
        "new_target_build_or_flash": False,
        "primary_PDFs_bundled": False,
        "independent_review_sha256": sha(review / "review.json"),
        "parent_run_summary_sha256": sha(validation / "summary.json"),
        "assembly_script_sha256": sha(Path(__file__))
    }
    (output / "assembly.json").write_text(json.dumps(provenance, indent=2) + "\n")
    assert not any(path.is_symlink() for path in output.rglob("*"))
    artifacts = [{"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(output.rglob("*")) if path.is_file()]
    (output / "artifact-manifest.json").write_text(json.dumps({"artifacts": artifacts}, indent=2) + "\n")
    print(json.dumps({"artifacts": len(artifacts), "manifest_sha256": sha(output / "artifact-manifest.json")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    main(arguments.root, arguments.output)
