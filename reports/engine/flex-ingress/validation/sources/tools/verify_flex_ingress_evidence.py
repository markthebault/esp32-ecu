#!/usr/bin/env python3
"""Verify frozen ingress evidence; optionally replay native/static probes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/engine/flex-ingress"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(name):
    path = Path(name)
    require(not path.is_absolute() and ".." not in path.parts, "Unsafe path: " + name)
    return path


def verify(report=REPORT, live=False, replay=False):
    report = report.resolve()
    manifest = json.loads((report / "artifact-manifest.json").read_text())
    rows = manifest["artifacts"]
    expected = {row["path"] for row in rows}
    require(len(expected) == len(rows), "Duplicate artifact")
    paths = list(report.rglob("*"))
    require(not any(path.is_symlink() for path in paths), "Symlink artifact")
    actual = {str(path.relative_to(report)) for path in paths if path.is_file() and path != report / "artifact-manifest.json"}
    require(actual == expected, "Artifact set differs")
    for row in rows:
        path = report / safe(row["path"])
        require(path.stat().st_size == row["bytes"] and sha(path) == row["sha256"], "Changed artifact: " + row["path"])
    summary = json.loads((report / "validation/summary.json").read_text())
    require(summary["scope"] == "flex_integer_ingress" and summary["checks_passed"], "Scope/checks mismatch")
    for field in ("target_producer_implemented", "protected_circuit_implemented", "target_callback_audited", "physical_qualification", "production_reference_executed", "full_speeduino_parity"):
        require(summary[field] is False, "Overstated qualification: " + field)
    sources = summary["sources"]
    require(summary["compiled_frozen_non_system_inputs"] is True and summary["input_and_tool_hashes_stable_before_after"] is True, "Unfrozen or unstable executable inputs")
    require(json.loads((report / "validation/inputs-before.json").read_text()) == sources == json.loads((report / "validation/inputs-after.json").read_text()), "Input attestations differ")
    require(json.loads((report / "validation/tools-before.json").read_text()) == summary["tools"] == json.loads((report / "validation/tools-after.json").read_text()), "Tool attestations differ")
    require(len({row["snapshot"] for row in sources}) == len(sources), "Duplicate source snapshot")
    by_name = {}
    for row in sources:
        snapshot = report / "validation" / safe(row["snapshot"])
        require(snapshot.stat().st_size == row["bytes"] and sha(snapshot) == row["sha256"], "Changed source binding")
        by_name[row["snapshot"].removeprefix("sources/")] = row["sha256"]
        if live:
            relative = row["snapshot"].removeprefix("sources/")
            current = Path(row["path"]) if relative.startswith("external/") else ROOT / safe(relative)
            require(current.is_file() and sha(current) == row["sha256"], "Live source differs: " + str(current))
    architecture = json.loads((report / "validation/sources/hardware/flex-input/architecture.json").read_text())
    require(architecture["contract"] == "FLEX-G38-DRAFT1" and architecture["implementation"]["portable_integer_ingress"], "Architecture identity")
    require(not any(value for key, value in architecture["implementation"].items() if key != "portable_integer_ingress"), "Architecture overstates implementation")
    require(architecture["allocation"]["flex_signal"]["gpio"] == 38 and architecture["allocation"]["reserved_straps"] == [45, 46], "Pin architecture")
    require(architecture["capture"]["ISR_queue_capacity"] == 64 and architecture["capture"]["retry_holdoff_us"] == 50000 and not architecture["capture"]["hardware_edge_FIFO"], "Ingress architecture")
    require(architecture["shared_i2c"]["total_budget_us"] == 3000 and architecture["shared_i2c"]["switch_IODIR_expected"] == 127 and not architecture["shared_i2c"]["mask_IODIR_bit7_to_accept_reset_value"], "Shared bus architecture")
    independent = json.loads((report / "reviews/ingress/review.json").read_text())
    require(independent["accepted"] is True and not independent["open_findings"], "Independent review not accepted")
    for name, digest in independent["source_hashes"].items():
        require(name in by_name and by_name[name] == digest, "Independent review source mismatch: " + name)
    expected_static = {}
    for name in ("xtensa", "xtensa-flash-negative", "xtensa-call-negative", "xtensa-unmapped-flash-negative"):
        saved = json.loads((report / "validation" / name / "audit.json").read_text())
        require(saved["elf_sha256"] == sha(report / "validation" / name / "probe.elf"), "ELF receipt mismatch")
        require(saved["passed"] == (name == "xtensa"), "Static positive/negative mismatch")
        expected_static[name] = saved
    require("Flash pointer loaded in ISR" in expected_static["xtensa-flash-negative"]["failures"], "Missing flash negative")
    require("Flash pointer loaded in ISR" in expected_static["xtensa-unmapped-flash-negative"]["failures"], "Missing unmapped flash negative")
    require(any(f.startswith("Unexpected direct/indirect ISR call:") for f in expected_static["xtensa-call-negative"]["failures"]), "Missing call negative")
    native = (report / "validation/native-run.stdout").read_text()
    require(native.strip().splitlines() == summary["native"] and not (report / "validation/native-run.stderr").read_text(), "Native receipt mismatch")
    if replay:
        with tempfile.TemporaryDirectory(prefix="ecu-flex-ingress-") as temporary:
            work = Path(temporary)
            environment = {**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1",
                           "GCOV_PREFIX": str(work / "owned-gcov"), "GCOV_PREFIX_STRIP": "0"}
            frozen = report / "validation/sources"
            binary = work / "native"
            subprocess.run(["g++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-pedantic",
                            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I", str(frozen / "firmware/include"),
                            str(frozen / "firmware/tests/flex_ingress_test.cpp"), "-o", str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, env=environment)
            require(result.returncode == 0 and result.stdout == native and not result.stderr, "Frozen native sanitizer replay differs")
            spec = importlib.util.spec_from_file_location("frozen_ingress_audit", frozen / "scripts/check_flex_ingress.py")
            module = importlib.util.module_from_spec(spec)
            previous = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                spec.loader.exec_module(module)
            finally:
                sys.dont_write_bytecode = previous
            for name, saved in expected_static.items():
                directory = work / name
                directory.mkdir()
                fresh = module.audit(report / "validation" / name / "probe.elf", directory)
                require(fresh == saved, "Frozen static replay differs: " + name)
        print("Replayed frozen native sanitizer scenarios and four saved Xtensa ELF audits")
    print("Verified", len(rows), "artifacts and", len(sources), "source snapshots; real target/circuit/HIL remain open")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--check-live-sources", action="store_true")
    parser.add_argument("--replay", action="store_true")
    arguments = parser.parse_args()
    verify(arguments.report, arguments.check_live_sources, arguments.replay)
