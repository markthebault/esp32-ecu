#!/usr/bin/env python3
"""Build a separate raw-edge flex fixture from attested production objects.

The original numerical sources, objects, executable and manifest are read only.
Only the new fixture entry point is compiled; the original timer HAL is reused.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PIN = "9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20"
BASE_SHA = "046389d754c996c34cb7e7171b1e42088f5ae6c0615133a3c5e74743f9f6d52c"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source=None):
    source = Path(source or ROOT.parent / "speeduino").resolve()
    base = ROOT / ".cache/engine/speeduino-sim"
    cache = ROOT / ".cache/engine/speeduino-flex-sim"
    cache.mkdir(parents=True, exist_ok=True)
    if not (base / "build-manifest.json").exists():
        raise RuntimeError("Build the pinned32-bit timer numerical adapter first")
    with (cache / "build.lock").open("a+b") as own_lock, (base / "build.lock").open("a+b") as base_lock:
        fcntl.flock(own_lock, fcntl.LOCK_EX)
        fcntl.flock(base_lock, fcntl.LOCK_SH)
        manifest = base / "build-manifest.json"
        m = json.loads(manifest.read_text())
        if m["unit_test"] or m["speeduino_sha"] != PIN or m["timer_counter_bits"] != 32 or m["binary_sha256"] != BASE_SHA or digest(base / "speeduino-sim") != BASE_SHA:
            raise RuntimeError("Numerical reference attestation failed")
        if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() != PIN:
            raise RuntimeError("Reference pin changed")
        subprocess.run(["git", "-C", str(source), "diff", "--exit-code", "HEAD", "--", "speeduino", "lib"], check=True)
        copied = base / ("source-" + m["archive_sha256"][:16] + "-idle-aux-v1")
        inputs = {}
        for name, expected in m["source_hashes"].items():
            path = ROOT / name if name.startswith("tools/") else copied / name
            if digest(path) != expected:
                raise RuntimeError("Numerical source changed: " + name)
            inputs[str(path)] = expected
        for key, directory in (("header_hashes", copied), ("dependency_hashes", source)):
            for name, expected in m[key].items():
                path = directory / name
                if digest(path) != expected:
                    raise RuntimeError("Numerical input changed: " + name)
                inputs[str(path)] = expected
        original = [base / "obj" / (name.replace("/", "_") + ".o") for name in m["source_hashes"] if name != "tools/speeduino_sim_native.hpp"]
        libraries = [source / name for name in m["dependency_hashes"] if name.endswith(".a")]
        for path in original + libraries + [manifest, base / "speeduino-sim"]:
            inputs[str(path)] = digest(path)
        if len(original) != 109:
            raise RuntimeError("Original translation-unit set changed")
        relink = cache / "numerical-reference-relink"
        link_tail = ["-Wl,--start-group", *map(str, libraries), "-Wl,--end-group", "-lgcov", "-pthread"]
        subprocess.run([m["compiler"], *map(str, original), *link_tail, "-o", str(relink)], check=True)
        if digest(relink) != BASE_SHA:
            raise RuntimeError("Cached objects do not exactly reproduce the attested numerical binary")
        fixture_names = ["scripts/build_speeduino_flex.py", "tools/speeduino_flex_sim.cpp", "firmware/include/ecu/flex_fuel.hpp"]
        fixture_sources = {name: digest(ROOT / name) for name in fixture_names}
        flags = [*m["compile_flags"], "-I" + str(ROOT / "firmware/include")]
        entry = cache / "speeduino_flex_sim.o"
        subprocess.run([m["compiler"], *flags, "-x", "c++", "-c", str(ROOT / "tools/speeduino_flex_sim.cpp"), "-o", str(entry)], check=True)
        objects = [path for path in original if path.name != "tools_speeduino_sim.cpp.o"] + [entry]
        binary = cache / "speeduino-flex-sim"
        if binary.exists() and (cache / "build-manifest.json").exists():
            previous = cache / "history" / digest(binary)
            previous.mkdir(parents=True, exist_ok=True)
            for path in (binary, cache / "build-manifest.json"):
                if not (previous / path.name).exists():
                    shutil.copy2(path, previous / path.name)
        temporary = cache / "speeduino-flex-sim.new"
        subprocess.run([m["compiler"], *map(str, objects), *link_tail, "-o", str(temporary)], check=True)
        if any(digest(Path(name)) != expected for name, expected in inputs.items()) or any(digest(ROOT / name) != expected for name, expected in fixture_sources.items()):
            raise RuntimeError("Input/source changed during fixture build")
        os.replace(temporary, binary)
        result = dict(scope="raw_edge_flex_acquisition_and_corrections_groundwork", speeduino_sha=PIN, unit_test=False,
                      binary_sha256=digest(binary), base_manifest_sha256=digest(manifest), base_binary_sha256=BASE_SHA,
                      numerical_relink_sha256=digest(relink), locked_original_input_hashes=inputs, fixture_sources=fixture_sources,
                      compile_flags=flags, timer_counter_bits=32, original_objects_reused=108,
                      object_hashes={str(path): digest(path) for path in objects}, library_hashes={str(path): digest(path) for path in libraries},
                      limits=["Native code, no AVR/ESP32 CPU timing or physical device emulation", "Real production setup, ISR callbacks, oneMSInterval and loop; no status/ethanol injection",
                              "Coincident virtual timer ticks occur before input callbacks, then the production loop", "Reference acquisition remains unchanged, including8-bit count/filter/cache behavior",
                              "Own portable core is not yet integrated with engine Tune, target producer, UI or hardware", "60s original virtual clock bound; no real engine, USB, flash or electrical qualification"])
        (cache / "build-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
        return binary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    print(build(args.source))
