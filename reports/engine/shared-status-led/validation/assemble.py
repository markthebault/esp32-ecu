#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path.cwd()
CACHE = ROOT / ".cache/engine/flex-target-integration"
BUILD = ROOT / ".cache/engine/shared-led-build-004"
REVIEW = ROOT / ".cache/engine/shared-led-review"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def main(output):
    output = output.resolve()
    acceptance = json.loads((REVIEW / "review.json").read_text())
    assert acceptance["accepted"] is True and not acceptance["open_findings"]
    sources = json.loads((BUILD / "sources-after.json").read_text())
    for name in acceptance["source_hashes"]:
        sources[name] = acceptance["source_hashes"][name]
    for name in ("tools/verify_shared_led_evidence.py", "tools/verify_flex_ingress_evidence.py", "tools/radio_simulator.py", "tools/test_status_led_ui.py", "scripts/audit_target_isr.py"):
        sources[name] = sha(ROOT / name)
    for name, digest in sources.items():
        assert sha(ROOT / name) == digest, name
    output.mkdir(parents=True, exist_ok=False)
    for name in sources:
        copy(ROOT / name, output / "sources" / name)
    for name in ("summary.json", "sources-before.json", "sources-after.json", "sources-pre-generation.json", "default-cache-before.json", "default-cache-after.json", "build.log", "embed-web.log", "web_assets.current.hpp"):
        copy(BUILD / name, output / "build" / name)
    for folder in ("elf-archives", "retained-sdkconfigs", "sdkconfigs-after"):
        shutil.copytree(BUILD / folder, output / "build" / folder)
    for env in ("compact_n16r8_flex_dev", "compact_n16r8_web", "compact_a3_web", "compact_a3_timing_bench"):
        copy(BUILD / "build" / env / "firmware.bin", output / "build/build" / env / "firmware.bin")
        copy(BUILD / "build" / env / "config/sdkconfig.h", output / "build/effective-sdkconfigs" / (env + ".h"))
    omitted = []
    for path in sorted(REVIEW.rglob("*")):
        relative = path.relative_to(REVIEW)
        if path.is_symlink():
            omitted.append({"path": str(relative), "reason": "symlink kept only in original reviewer cache", "target": os.readlink(path)})
            continue
        if not path.is_file() or ".git" in relative.parts or "__pycache__" in relative.parts:
            continue
        with path.open("rb") as stream:
            binary = stream.read(4) == b"\x7fELF"
        if binary or path.suffix in (".o", ".bin", ".pyc"):
            omitted.append({"path": str(relative), "sha256": sha(path), "bytes": path.stat().st_size, "reason": "raw executable/object retained locally; final firmware has lossless archives"})
            continue
        copy(path, output / "reviews/independent" / relative)
    (output / "reviews/omitted-raw-files.json").write_text(json.dumps(omitted, indent=2) + "\n")
    packaging = ROOT / ".cache/engine/shared-led-packaging-review"
    verdict = json.loads((packaging / "review.json").read_text())
    assert verdict["accepted"] is True
    for path in packaging.iterdir():
        if path.is_file() and not path.is_symlink():
            copy(path, output / "reviews/packaging" / path.name)
    shutil.copytree(ROOT / ".cache/engine/shared-led-audits-001", output / "audits")
    shutil.copytree(CACHE / "led-ui-fixtures-002", output / "fixtures")
    shutil.copytree(CACHE / "ui-001", output / "browser")
    for name in ("platformio-cache-side-effect.json", "prior-elf-search-001.json"):
        copy(CACHE / name, output / "provenance" / name)
    for name in ("native-final-001.log", "python-001.log", "browser-001.log", "led-core-002.log", "legacy-service-001.log", "shared-service-004.log", "isr-dev-001.log", "old-ingress-verify.log", "old-integration-verify.log", "old-core-verify.log"):
        copy(CACHE / name, output / "validation" / name)
    copy(Path(__file__), output / "validation/assemble.py")
    # Complete original logs/corruptions stay local; these receipts explain the
    # rejected pre-final generated-header state without relabeling it as pass.
    for number in ("001", "002", "003"):
        origin = ROOT / (".cache/engine/shared-led-build-" + number)
        copy(origin / "summary.json", output / "provenance" / ("build-" + number + "-summary.json"))
    cjson = Path.home() / ".platformio/packages/framework-espidf/components/json/cJSON"
    for name in ("cJSON.c", "cJSON.h"):
        copy(cjson / name, output / "dependencies/cjson" / name)
    lines = (CACHE / "native-final-001.log").read_text().splitlines()
    core = next(line for line in lines if line.startswith("status_led_checks ")) + "\n"
    legacy = next(line for line in lines if '"actual_service_checks"' in line) + "\n"
    shared = (CACHE / "shared-service-004.log").read_text()
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "scope": "shared_i2c_led_software", "checks_passed": True,
               "source_hashes": sources, "native_replay_stdout": {"core": core, "legacy": legacy, "shared": shared},
               "target_capture_producer": False, "protected_circuit": False, "native_CAD": False,
               "flashed": False, "physical_qualification": False, "full_speeduino_parity": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "README.md").write_text("""# Shared-I2C status LED software checkpoint

The separate `compact_n16r8_flex_dev` build removes GPIO38 RMT ownership, configures it as input and drives an advisory ordinary RGB interface through MCP23008 address0x21. A single monitor owner shares one3ms transaction origin with required switches at0x20. Switch guards run first; LED guarded reads wait for two remaining integer-ms timeout slots. No physical device was flashed.

The driver initializes OLAT off before direction, makes every GP an output (unused GP3..7 NC/low), and verifies a nonuniform IOCON4 frame plus trailing IODIR. Independent review found and closed an initial all-zero/byte-mode alias. Full U64 observation/completion/query ordering, SDK failures, partial ownership cleanup, stale data and cross-task policy coalescing have native checks. SDK allocation/deletion and CPU/lock overhead are not proven hard WCET.

The paired-screens UI separates requested policy from verified/historical latch and clears verification after failed polls. Six actual-service mocked-I2C fixtures,25 malformed payloads and installed Chrome desktop/mobile checks pass. Screenshots explicitly label their native SDK-model replay. Latch readback is not light output or live CPU health; a failed bus/CPU can retain green. A missing LED alone adds no engine dependency, while a shared-bus fault invalidates required switches and produces a control cut in the native controller check.

Parent checks:518 portable LED,243 legacy switch service,2336 actual shared-service assertions (2366 with six fixture exports),74 status allocation cuts, full native regression,28 radio/configuration Python tests and62,297 unchanged ingress assertions. Independent review adds its own8-case SDK model,103 UI checks, build/config/generation negatives and read-only linked-ELF audits. Its exact scope/source hashes are in reviews/independent/review.json.

Final004 has four successful real Linux builds, identical before/after compilation inputs, retained unchanged current default cache and lossless gzip ELF archives. All three web ELFs contain the exact current complete HTML in flash rodata; the bench profile omits web UI. Existing linked-engine policy and exclusive-USB audits pass; the new profile's complete current ISR closure passes static placement. These checks do not establish runtime heap/stack, actual USB, interrupt interference or physical behavior. Only the existing A3 dummy-load image has its separately gated dummy policy; selected N16R8 physical engine scheduling stays inhibited.

Two build-tool issues are disclosed. The first direct PlatformIO invocation after editing platformio.ini automatically removed older generated default environment caches; the original selected10c99... ELF was not recovered after a bounded search. Source history and old immutable report packets remain. Later builds use a fresh owned PLATFORMIO_BUILD_DIR, retain the current default cache/SDK configs and archive resulting ELF bytes losslessly. Initial build001/002 embedded stale UI;003 correctly rejected its unchanged-source assertion because declared header generation occurred before sampling. Final004 regenerates first, permits only the declared header output, then attests stable compilation inputs. Earlier receipts are preserved as history, not relabeled successes for current UI.

The GPIO38 capture worker, source-local masking/publication/control-ACK fences, protected frontend, exact physical LED driver/circuit, PCB/case integration, physical HIL/EMI/surge/thermal/splash/fit, negotiated flex radio, ethanol chemistry and supported online vendor identity remain open. Required target flex still inhibits control. This checkpoint does not complete Speeduino parity or qualify an engine/vehicle.

Current sources are copied under sources/. Native cJSON dependencies are bundled with their license notices. Reviewer executables/objects remain in the original local cache; the omission list retains hashes, while final firmware ELFs are bundled losslessly. Four compressed ELFs and firmware.bin files are records for inspection, not installation instructions or a manufacturing release.

```sh
python3 -B tools/verify_shared_led_evidence.py --replay
python3 -B scripts/build_firmware_preserved.py --output .cache/engine/NEW_BUILD --environment compact_n16r8_flex_dev
```

Default verification uses frozen evidence. Add --check-live-sources only to compare this checkpoint with the current worktree. Replays execute portable/native models only, never an Xtensa or production Speeduino image.
""")
    assert not any(path.is_symlink() for path in output.rglob("*"))
    artifacts = [{"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(output.rglob("*")) if path.is_file()]
    (output / "artifact-manifest.json").write_text(json.dumps({"artifacts": artifacts}, indent=2) + "\n")
    print(json.dumps({"artifacts": len(artifacts), "sources": len(sources), "manifest_sha256": sha(output / "artifact-manifest.json")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output)
