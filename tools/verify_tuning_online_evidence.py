#!/usr/bin/env python3
"""Verify the immutable own009/referenced-controller application packet.

Replay audits saved host bytes and compiles the frozen own-controller sanitizer
probe. It does not launch TunerStudio, access hardware, or prove ECU parity.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/engine/tuning-online-009"
PIN = "9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20"
APP_SHA = "3ebafb867fef3722816e768879501845904f81bc5e13249c77d170e9adf61cf8"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def read(path):
    body = path.read_bytes()
    return gzip.decompress(body) if path.suffix == ".gz" else body


def document(path):
    return json.loads(read(path))


def safe_name(name):
    path = Path(name)
    require(not path.is_absolute() and ".." not in path.parts, "Unsafe path: " + name)
    return path


def reference_page(analysis, msq):
    """Reconstruct page 2 from actual reads/writes, then match the saved MSQ."""
    page = {}
    before = None
    writes = []
    burns = []
    crc_checks = []
    runtime = bytearray(139)
    seen = set()
    samples = set()
    for index, row in enumerate(analysis["transactions"]):
        request = bytes.fromhex(row["request_hex"])
        answer = bytes.fromhex(row["response_hex"])
        if row["kind"] == "raw_F":
            continue
        if request[:1] in (b"p", b"r"):
            require(len(request) == 7, "Read request size")
            _, number, offset, count = struct.unpack("<BBHH", request[1:])
            require(answer[:1] == b"\0" and len(answer) == count + 1, "Read response size/status")
            if request[:1] == b"p" and number == 2:
                page.update(enumerate(answer[1:], offset))
                if set(page) == set(range(288)) and before is None:
                    before = bytes(page[n] for n in range(288))
            elif request[:1] == b"r" and number == 0x30:
                require(offset + count <= 139, "Reference runtime bounds")
                if offset == 0:
                    seen.clear()
                runtime[offset:offset + count] = answer[1:]
                seen.update(range(offset, offset + count))
                if len(seen) == 139:
                    samples.add((struct.unpack_from("<H", runtime, 14)[0],
                                 struct.unpack_from("<H", runtime, 4)[0],
                                 runtime[6] - 40, runtime[7] - 40))
        elif request[:1] == b"M":
            require(len(request) >= 7, "Write request size")
            _, number, offset, count = struct.unpack("<BBHH", request[1:7])
            require(number == 2 and len(request) == 7 + count and answer == b"\0", "Write acknowledgement")
            require(before is not None, "Write precedes complete page read")
            writes.append((number, offset, count, request[7:].hex()))
            page.update(enumerate(request[7:], offset))
        elif request[:1] == b"b":
            require(request == b"b\0\2" and answer == b"\4", "Burn acknowledgement")
            burns.append(index)
        elif request == b"d\0\2" and len(page) == 288:
            require(answer[:1] == b"\0" and len(answer) == 5, "Page CRC response")
            computed = zlib.crc32(bytes(page[n] for n in range(288)))
            require(int.from_bytes(answer[1:], "big") == computed, "Controller page CRC differs")
            crc_checks.append((bool(burns), computed))
    require(before is not None and set(page) == set(range(288)), "Incomplete VE page")
    after = bytes(page[n] for n in range(288))
    require(writes == [(2, 240, 1, "56")] and len(burns) == 1, "Actual application edit/burn differs")
    require([(n, a, b) for n, (a, b) in enumerate(zip(before, after)) if a != b] == [(240, 85, 86)], "Unexpected changed VE bytes")
    require((True, 0xbe04ef33) in crc_checks, "Missing matching post-burn CRC")
    root = ET.fromstring(msq)
    constants = {node.attrib["name"]: node for node in root.iter() if "name" in node.attrib}
    version = next(node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "versionInfo")
    require(version.attrib["signature"] == "speeduino 202504-dev", "Saved MSQ identity differs")
    values = []
    for name, size, scale in (("veTable", 256, 1), ("rpmBins", 16, 100), ("fuelLoadBins", 16, 2)):
        array = [float(value) / scale for value in constants[name].text.split()]
        require(len(array) == size and all(value.is_integer() and 0 <= value <= 255 for value in array), "MSQ encoding: " + name)
        values.extend(int(value) for value in array)
    require(bytes(values) == after, "Saved MSQ does not match complete controller page")
    require(samples and all(rpm == 0 and pressure == 100 and iat in (24, 25) and clt in (84, 85)
                            for rpm, pressure, iat, clt in samples), "Synthetic runtime fixture differs")


def verify(report=REPORT, live=False, replay=False):
    report = report.resolve()
    entries = document(report / "artifact-manifest.json")["artifacts"]
    require(len({row["path"] for row in entries}) == len(entries), "Duplicate artifact path")
    files = {str(p.relative_to(report)) for p in report.rglob("*") if p.is_file() and p != report / "artifact-manifest.json"}
    require(files == {row["path"] for row in entries}, "Artifact set differs")
    for row in entries:
        path = report / safe_name(row["path"])
        require(not path.is_symlink(), "Symlink artifact: " + row["path"])
        body = path.read_bytes()
        require(len(body) == row["bytes"] and sha(body) == row["sha256"], "Changed artifact: " + row["path"])
    summary = document(report / "summary.json")
    require(summary["scope"] == "own009_discovery_and_production_reference_serial", "Packet scope")
    require(summary["checks_passed"] and not any(summary[name] for name in
            ("own_online_accepted", "physical_qualification", "full_speeduino_parity", "vendor_request_sent")), "Overstated acceptance")
    for name, row in summary["sources"].items():
        body = (report / safe_name(row["snapshot"])).read_bytes()
        require(sha(body) == row["sha256"], "Snapshot differs: " + name)
        if live:
            require((ROOT / safe_name(name)).read_bytes() == body, "Live source changed: " + name)
    for name, row in summary["upstream_sources"].items():
        require(sha((report / safe_name(row["snapshot"])).read_bytes()) == row["sha256"], "Upstream snapshot differs: " + name)
    require((report / "reference/mainController.ini").read_bytes() == (report / "upstream/reference/speeduino.ini").read_bytes(), "Reference INI snapshot differs")
    require(summary["tests"]["python"] == 221 and "Ran 221 tests" in (report / "validation/python-full.log").read_text(), "Full Python test record")
    require(summary["tests"]["new_serial_capture"] == 16 and "Ran 16 tests" in (report / "validation/serial-capture-tests.log").read_text(), "Serial/capture test record")
    final_review = document(report / "reviews/revision005/review.json")
    application_review = document(report / "reviews/revision005/public-application-write-burn-review.json")
    for name, row in final_review["frozen_implementation"].items():
        require(row["matches"] and summary["sources"][name]["sha256"] == row["frozen_sha256"], "Implementation review binding: " + name)
    require(final_review["validation"]["tests_passed"] and final_review["validation"]["test_count"] == 16, "Independent tests")
    docs_review = document(report / "reviews/publication-review.json")
    require(docs_review["accepted"] and not docs_review["open_findings"], "Publication review not accepted")
    for name, digest in docs_review["source_hashes"].items():
        require(summary["sources"][name]["sha256"] == digest, "Publication source binding: " + name)
    for name, digest in docs_review["packet_hashes"].items():
        require(sha((report / safe_name(name)).read_bytes()) == digest, "Publication artifact binding: " + name)
    native = document(report / "reference/native-build-manifest.json")
    require(native["speeduino_sha"] == PIN and not native["unit_test"], "Reference production pin")
    require(native["numerical_relink_sha256"] == native["base_binary_sha256"], "Exact numerical relink differs")
    require(native["binary_sha256"] == application_review["native_build_binary_sha256"], "Reviewed serial binary differs")
    require(len(native["locked_original_input_hashes"]) == 565, "Original input set")
    input_review = document(report / "reviews/revision005/launch-input-hash-validation.json")
    require(set(input_review) == set(native["locked_original_input_hashes"]), "Reviewed native input set differs")
    for name, digest in native["locked_original_input_hashes"].items():
        require(input_review[name]["matches"] and input_review[name]["expected"] == input_review[name]["current"] == digest,
                "Reviewed native input differs: " + name)
    for name, digest in native["fixture_sources"].items():
        require(summary["sources"][name]["sha256"] == digest, "Native producer binding: " + name)
    for label, count, identity in (("own", 1640, "ESP32ECU DEV 009 INHIBITED"), ("reference", 10838, "speeduino 202504-dev")):
        analysis = document(report / label / "stream-analysis.json.gz")
        require(analysis["wire_sha256"] == sha(read(report / label / "wire.log.gz")), "Wire binding: " + label)
        require(analysis["complete_transactions"] == count and analysis["capture_complete"] and not analysis["invalid_frames"], "Invalid/incomplete capture: " + label)
        require(analysis["signatures"] == [identity], "Captured identity: " + label)
        session = document(report / label / "session.json")
        require(session["application_sha256"] == APP_SHA, "Application binary hash differs")
        require(session["ini_sha256"] == sha((report / label / "mainController.ini").read_bytes()), "Application INI differs")
        for name, digest in session.get("sources", {}).items():
            require(summary["sources"][name]["sha256"] == digest, "Launch producer binding: " + name)
        debug = read(report / label / "application-debug.log.gz").decode()
        if label == "own":
            require(analysis["command_counts"] == {"F": 328, "I": 328, "f": 656, "Q": 328}, "Own discovery differs")
            require(debug.count("Unsupported Controller Firmware: ESP32ECU DEV 009 INHIBITED") == 328, "Missing own rejection warnings")
            require(sha((report / label / "mainController.ini").read_bytes()) == summary["sources"]["tuning/esp32-ecu-secondary.ini"]["sha256"], "Own application definition binding")
        else:
            require(session["ini_sha256"] == application_review["pinned_ini_sha256"], "Pinned application definition differs")
            require(analysis["command_counts"] == {"F": 1, "I": 1, "f": 2, "Q": 1, "S": 1, "d": 18, "p": 22, "r": 10790, "M": 1, "b": 1}, "Reference workflow differs")
            require("Unsupported Controller Firmware" not in debug and "burned page 2" in debug, "Reference application state")
            reference_page(analysis, (report / label / "reference-app-edited.msq").read_bytes())
            closure = document(report / label / "closure.json")
            require(closure["returncode"] == 0 and not closure["failure"] and not closure["physical_interface"], "Native fixture closure")
            native_tx = sum(len(bytes.fromhex(line.split()[2])) for line in read(report / label / "native-events.log.gz").decode().splitlines() if line.startswith("tx "))
            require(native_tx == analysis["bytes"]["TX"] == 752363, "Final reference TX accounting differs")
    vendor = document(report / "vendor/attachment-manifest.json")
    with zipfile.ZipFile(report / "vendor-support.zip") as archive:
        require(len(archive.namelist()) == len(vendor["files"]) and set(archive.namelist()) == set(vendor["files"]), "Vendor attachment set")
        for name, row in vendor["files"].items():
            body = archive.read(str(safe_name(name)))
            require(sha(body) == row["sha256"] and body == (report / safe_name(row["packet_source"])).read_bytes(), "Vendor attachment binding: " + name)
    if replay:
        spec = importlib.util.spec_from_file_location("frozen_tuning_capture", report / "sources/tools/analyze_tuning_wire.py")
        analyzer = importlib.util.module_from_spec(spec)
        previous = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec.loader.exec_module(analyzer)
        finally:
            sys.dont_write_bytecode = previous
        with tempfile.TemporaryDirectory(prefix="ecu-online-evidence-") as temporary:
            work = Path(temporary)
            for label in ("own", "reference"):
                wire = work / (label + ".log")
                wire.write_bytes(read(report / label / "wire.log.gz"))
                require(analyzer.analyze(wire) == document(report / label / "stream-analysis.json.gz"), "Capture replay differs: " + label)
            binary = work / "own-protocol-probe"
            subprocess.run(["g++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I" + str(report / "sources/firmware/include"), str(report / "reviews/revision001/protocol_probe.cpp"), "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1"})
            require(json.loads(result.stdout) == document(report / "reviews/revision001/protocol-probe.json"), "Own sanitizer replay differs")
            subprocess.run([sys.executable, "-B", "-m", "unittest", "test_tuning_wire_analysis"], cwd=report / "sources/tools", check=True)
        print("Replayed both saved streams, page/MSQ/CRC audit, own sanitizer probe and four analyzer tests")
    print("Verified", len(entries), "artifacts and", len(summary["sources"]), "source snapshots; own online support and physical/full parity remain open")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--check-live-sources", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    verify(args.report, args.check_live_sources, args.replay)
