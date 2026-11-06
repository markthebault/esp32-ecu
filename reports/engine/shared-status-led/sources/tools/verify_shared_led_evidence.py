#!/usr/bin/env python3
"""Verify/replay frozen shared-I2C LED software evidence without a device."""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/engine/shared-status-led"
ENVS = ("compact_n16r8_flex_dev", "compact_n16r8_web", "compact_a3_web", "compact_a3_timing_bench")
REVIEWED = set(""".gitignore docs/engine-feature-coverage.md docs/engine-flex-fuel.md
firmware/boards/esp32-s3-44pin-n16r8.json firmware/include/ecu/board_status.hpp
firmware/include/ecu/flex_hardware.hpp firmware/include/ecu/status_led.hpp
firmware/include/ecu/switch_acquisition.hpp firmware/include/ecu/switch_service.hpp
firmware/include/ecu/switch_transport.hpp firmware/main/engine_target.cpp
firmware/main/espnow.cpp firmware/main/switch_service.cpp firmware/main/web_assets.hpp
firmware/platformio.ini firmware/sdkconfig.n16r8.defaults
firmware/tests/shared_i2c_service_test.cpp firmware/tests/status_led_test.cpp
firmware/tests/switch_service_test.cpp hardware/flex-input/README.md
hardware/flex-input/architecture.json scripts/build_firmware_preserved.py
scripts/check_flex_ingress.py scripts/embed_web.py scripts/test_firmware.sh
scripts/tuning_sdkconfig.py tools/radio_simulator.py tools/test_status_led_ui.py web/index.html""".split())
EXECUTION = REVIEWED | {"firmware/main/app.cpp", "firmware/include/ecu/engine.hpp",
    "firmware/include/ecu/pins.hpp", "firmware/include/ecu/idle_hardware.hpp",
    "firmware/tests/switch_fakes/driver/i2c_master.h", "firmware/tests/switch_fakes/freertos/FreeRTOS.h",
    "tools/verify_shared_led_evidence.py", "scripts/audit_target_isr.py"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def require(value, message):
    if not value:
        raise ValueError(message)


def safe(name):
    path = Path(name)
    require(not path.is_absolute() and ".." not in path.parts, "Unsafe artifact path")
    return path


def verify(report=REPORT, live=False, replay=False):
    report = report.resolve()
    manifest = read(report / "artifact-manifest.json")
    names = {row["path"] for row in manifest["artifacts"]}
    require(len(names) == len(manifest["artifacts"]), "Duplicate artifact")
    paths = list(report.rglob("*"))
    require(not any(path.is_symlink() for path in paths), "Symlink artifact")
    # Nested reviewer manifests are ordinary evidence, not this packet's index.
    actual = {str(path.relative_to(report)) for path in paths if path.is_file() and path != report / "artifact-manifest.json"}
    require(actual == names, "Artifact set differs")
    for row in manifest["artifacts"]:
        path = report / safe(row["path"])
        require(path.stat().st_size == row["bytes"] and sha(path) == row["sha256"], "Changed artifact: " + row["path"])
    summary = read(report / "summary.json")
    require(summary["scope"] == "shared_i2c_led_software" and summary["checks_passed"] is True, "Scope/check mismatch")
    require(EXECUTION <= set(summary["source_hashes"]), "Required execution source bindings missing")
    for name in ("target_capture_producer", "protected_circuit", "native_CAD", "flashed", "physical_qualification", "full_speeduino_parity"):
        require(summary[name] is False, "Overstated completion: " + name)
    for name, digest in summary["source_hashes"].items():
        snapshot = report / "sources" / safe(name)
        require(sha(snapshot) == digest, "Source snapshot mismatch: " + name)
        if live:
            require((ROOT / name).is_file() and sha(ROOT / name) == digest, "Live source differs: " + name)
    independent = read(report / "reviews/independent/review.json")
    require(independent["accepted"] is True and not independent["open_findings"], "Independent acceptance missing")
    require(set(independent["source_hashes"]) == REVIEWED, "Independent reviewed source set differs")
    for name, digest in independent["source_hashes"].items():
        require(summary["source_hashes"].get(name) == digest, "Review source mismatch: " + name)
    build = read(report / "build/summary.json")
    require(type(build["exit_code"]) is int and build["exit_code"] == 0 and
            all(build[name] is True for name in ("source_inputs_unchanged", "default_cache_unchanged", "generation_only_declared_output")), "Build attestation failed")
    require(set(build["environments"]) == set(ENVS) and len(build["environments"]) == 4, "Build environment set")
    compiled = read(report / "build/sources-before.json")
    require(compiled == read(report / "build/sources-after.json"), "Compile inputs changed")
    required_compile = {name for name in EXECUTION if name.split("/")[0] in ("firmware", "web", "scripts")}
    require(required_compile <= set(compiled), "Required compilation input binding missing")
    for name, digest in compiled.items():
        require(summary["source_hashes"].get(name) == digest, "Compile source binding differs: " + name)
    require(read(report / "build/default-cache-before.json") == read(report / "build/default-cache-after.json"), "Default cache changed")
    require(set(build["declared_generation_changes"]) <= {"firmware/main/web_assets.hpp"}, "Undeclared generation change")
    require(sha(report / "sources/firmware/main/web_assets.hpp") == build["generated_assets_sha256"], "Generated header binding")
    html = (report / "sources/web/index.html").read_text().encode()
    require(hashlib.sha256(html).hexdigest() == build["web_index_sha256"], "Web source binding")
    embedded = {row["environment"]: row for row in build["embedded_UI"]}
    require(set(embedded) == set(ENVS), "Embedded UI environment set")
    for env in ENVS:
        require(embedded[env]["web_expected"] == (env != ENVS[-1]) and embedded[env]["current_index_in_flash_rodata"] == (env != ENVS[-1]), "Embedded UI receipt")
    architecture = read(report / "sources/hardware/flex-input/architecture.json")
    require(architecture["implementation"]["shared_bus_led_driver"] and not architecture["implementation"]["target_producer"] and not architecture["implementation"]["protected_input_circuit"], "Architecture scope")
    require(architecture["allocation"]["status_led"]["IODIR_expected"] == 0 and architecture["allocation"]["status_led"]["IOCON_expected"] == 4, "Legal nonuniform register contract")
    side_effect = read(report / "provenance/platformio-cache-side-effect.json")
    require(side_effect["original_prior_elf_recovered"] is False and side_effect["source_history_and_frozen_reports_retained"] is True, "Cache-loss disclosure missing")
    require(not read(report / "provenance/prior-elf-search-001.json")["matching_paths"], "Recovery disclosure differs")
    archives = {row["environment"]: row for row in build["elf_archives"]}
    require(set(archives) == set(ENVS) and len(build["elf_archives"]) == 4, "ELF archive set")
    images = {row["path"].split("/")[1]: row for row in build["artifacts"] if row["path"].endswith("/firmware.bin")}
    require(set(images) == set(ENVS), "Image set")
    helper_spec = importlib.util.spec_from_file_location("frozen_preserved_build", report / "sources/scripts/build_firmware_preserved.py")
    helper = importlib.util.module_from_spec(helper_spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        helper_spec.loader.exec_module(helper)
    finally:
        sys.dont_write_bytecode = previous
    with tempfile.TemporaryDirectory(prefix="ecu-shared-led-") as temporary:
        work = Path(temporary)
        for env in ENVS:
            row = archives[env]
            require(0 < row["elf_bytes"] <= 64000000, "ELF size limit")
            archive = report / "build" / safe(row["path"])
            require(sha(archive) == row["sha256"], "Archive binding")
            with gzip.GzipFile(fileobj=io.BytesIO(archive.read_bytes())) as compressed:
                body = compressed.read(row["elf_bytes"] + 1)
            require(len(body) == row["elf_bytes"] and hashlib.sha256(body).hexdigest() == row["elf_sha256"], "Lossless ELF binding")
            elf = work / (env + ".elf")
            elf.write_bytes(body)
            require(helper.embedded_index(elf, html) == (env != ENVS[-1]), "Actual ELF flash UI differs")
            image = report / "build" / safe(images[env]["path"])
            require(image.stat().st_size <= 2097152 and sha(image) == images[env]["sha256"], "Factory app image binding")
            policy = read(report / "audits" / env / "audit.json")
            require(policy["passed"] and policy["elf_sha256"] == row["elf_sha256"] and policy["binary_sha256"] == sha(image), "Linked policy binding")
            expected = "gated_engine_dummy_loads_only" if env == ENVS[-1] else "engine_scheduler_physical_writes_compile_time_inhibited"
            require(policy["policy"] == expected, "Physical output policy")
            policy_sources = {"firmware/platformio.ini", "firmware/main/engine_target.cpp", "firmware/main/app.cpp",
                              "firmware/include/ecu/pins.hpp", "firmware/include/ecu/idle_hardware.hpp"}
            require(set(policy["source_sha256"]) == policy_sources, "Policy source set differs")
            for name, digest in policy["source_sha256"].items():
                require(summary["source_hashes"].get(name) == digest, "Policy source binding differs: " + name)
            if env != ENVS[-1]:
                usb = read(report / "audits" / (env + "-usb.json"))
                require(usb["elf_sha256"] == row["elf_sha256"] and usb["exclusive_usb"] is True and usb["sdk_original_retained"] is True, "USB source/ELF binding")
                require(summary["source_hashes"].get(usb["project_driver_source"]) == usb["project_driver_sha256"], "USB driver source differs")
                config = report / "build/sdkconfigs-after" / ("sdkconfig." + env)
                require(sha(config) == usb["sdkconfig_sha256"], "USB effective config differs")
        closure = read(report / "audits/isr-dev/closure.json")
        require(closure["passed_static_placement"] and not closure["failures"] and closure["elf_sha256"] == archives[ENVS[0]]["elf_sha256"], "ISR closure binding")
        browser = read(report / "browser/results.json")
        require(browser["passed"] and not browser["page_errors"] and browser["scope"] == "native_SDK_model_UI_replay_not_physical_LED", "Browser scope/result")
        if replay:
            frozen = report / "sources"
            cjson = report / "dependencies/cjson"
            flags = ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            subprocess.run(["cc", *flags, "-c", str(cjson / "cJSON.c"), "-o", str(work / "cjson.o")], check=True, capture_output=True)
            environment = {**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1", "GCOV_PREFIX": str(work / "owned-gcov"), "GCOV_PREFIX_STRIP": "0"}
            for name, source, shared in (("core", "status_led_test.cpp", None), ("legacy", "switch_service_test.cpp", False), ("shared", "shared_i2c_service_test.cpp", True)):
                command = ["g++", "-std=c++17", *flags, "-Wall", "-Wextra", "-Werror", "-pedantic", "-pthread", "-I", str(frozen / "firmware/include")]
                if shared is not None:
                    command += ["-I", str(cjson), "-I", str(frozen / "firmware/tests/switch_fakes")]
                if shared:
                    command += ["-DECU_COMPACT_A3=1", "-DECU_SELECTED_N16R8=1", "-DECU_FLEX_G38_DRAFT=1"]
                command += [str(frozen / "firmware/tests" / source)]
                if shared is not None:
                    command += [str(frozen / "firmware/main/switch_service.cpp"), str(work / "cjson.o")]
                binary = work / name
                subprocess.run([*command, "-o", str(binary)], check=True, capture_output=True)
                args = [str(binary)]
                if shared:
                    fixtures = work / "fixtures"
                    fixtures.mkdir()
                    args.append(str(fixtures))
                result = subprocess.run(args, capture_output=True, text=True, env=environment)
                require(result.returncode == 0 and not result.stderr and result.stdout == summary["native_replay_stdout"][name], "Native replay differs: " + name)
                if shared:
                    require({p.name: sha(p) for p in fixtures.iterdir()} == {p.name: sha(p) for p in (report / "fixtures").iterdir()}, "Actual-service fixture replay differs")
            print("Replayed frozen portable/legacy/shared services with sanitizers and six exact mocked-I2C fixtures")
    print("Verified", len(names), "artifacts and", len(summary["source_hashes"]), "sources; target capture/circuit/HIL and full parity remain open")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--check-live-sources", action="store_true")
    parser.add_argument("--replay", action="store_true")
    options = parser.parse_args()
    verify(options.report, options.check_live_sources, options.replay)
