#!/usr/bin/env python3
"""Build in a new owned directory; retain and verify the default PIO cache.

PlatformIO removes its build directory when project configuration changes.
Never use this tool to flash; it runs only `pio run` in an isolated build root.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path):
    rows = []
    if not path.exists():
        return rows
    for directory, directories, files in os.walk(path, followlinks=False):
        for name in sorted(directories + files):
            item = Path(directory) / name
            row = {"path": str(item.relative_to(path)), "mode": stat.S_IMODE(item.lstat().st_mode)}
            if item.is_symlink():
                row.update(kind="symlink", target=os.readlink(item))
            elif item.is_file():
                row.update(kind="file", bytes=item.stat().st_size, sha256=sha(item))
            else:
                row.update(kind="directory")
            rows.append(row)
    return sorted(rows, key=lambda row: row["path"])


def inputs():
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "firmware", "web", "config", "scripts"], cwd=ROOT).split(b"\0")
    return {name.decode(): sha(ROOT / name.decode()) for name in sorted(set(names)) if name and (ROOT / name.decode()).is_file()}


def embedded_index(elf, html):
    body = elf.read_bytes()
    if body[:6] != b"\x7fELF\x01\x01":
        return False
    offset = struct.unpack_from("<I", body, 32)[0]
    step, count, string_index = struct.unpack_from("<HHH", body, 46)
    sections = [struct.unpack_from("<IIIIIIIIII", body, offset + n * step) for n in range(count)]
    header = sections[string_index]
    names = body[header[4]:header[4] + header[5]]
    for section in sections:
        name = names[section[0]:].split(b"\0", 1)[0]
        if name == b".flash.rodata":
            return html + b"\0" in body[section[4]:section[4] + section[5]]
    return False


def run(output, environments):
    output = output.resolve()
    if not output.is_relative_to(ROOT / ".cache"):
        raise ValueError("Choose a new output directory below the project's .cache")
    if not environments or any(not re.fullmatch(r"[a-zA-Z0-9_]+", name) for name in environments):
        raise ValueError("Use explicit PlatformIO environment names")
    output.mkdir(parents=True, exist_ok=False)
    default = ROOT / "firmware/.pio/build"
    before = tree(default)
    (output / "default-cache-before.json").write_text(json.dumps(before, indent=2) + "\n")
    if default.exists():
        retained = output / "retained-default-cache"
        shutil.copytree(default, retained, symlinks=True)
        if tree(retained) != before:
            raise ValueError("Default build cache retention differs")
    sdkconfigs = []
    for name in environments:
        path = ROOT / "firmware" / ("sdkconfig." + name)
        if path.is_symlink():
            raise ValueError("Preserve historical SDK config symlink: " + str(path))
        row = {"environment": name, "original_present": path.is_file()}
        if path.is_file():
            retained = output / "retained-sdkconfigs" / path.name
            retained.parent.mkdir(exist_ok=True)
            shutil.copyfile(path, retained)
            row.update(original_sha256=sha(path), retained=str(retained.relative_to(output)))
        sdkconfigs.append(row)
    pre_generation = inputs()
    (output / "sources-pre-generation.json").write_text(json.dumps(pre_generation, indent=2) + "\n")
    generated = ROOT / "firmware/main/web_assets.hpp"
    if generated.is_symlink():
        raise ValueError("Preserve historical generated-asset symlink")
    if generated.exists():
        shutil.copyfile(generated, output / "web_assets.before.hpp")
    with (output / "embed-web.log").open("xb") as log:
        subprocess.run([sys.executable, "-B", str(ROOT / "scripts/embed_web.py")], cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    html = (ROOT / "web/index.html").read_text().encode()
    expected = b'inline constexpr char index[]=R"ECU_ASSET(' + html + b')ECU_ASSET";'
    if expected not in generated.read_bytes():
        raise ValueError("Generated web header does not contain current index")
    shutil.copyfile(generated, output / "web_assets.current.hpp")
    generated_sha = sha(generated)
    source_before = inputs()
    generation_changes = sorted(name for name in pre_generation.keys() | source_before.keys()
                                if pre_generation.get(name) != source_before.get(name))
    if set(generation_changes) - {"firmware/main/web_assets.hpp"}:
        raise ValueError("Asset generation changed an undeclared project source")
    (output / "sources-before.json").write_text(json.dumps(source_before, indent=2) + "\n")
    environment = {**os.environ, "PLATFORMIO_BUILD_DIR": str(output / "build")}
    command = ["pio", "run", "-d", str(ROOT / "firmware")]
    for name in environments:
        command += ["-e", name]
    with (output / "build.log").open("xb") as log:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
    after, source_after = tree(default), inputs()
    if sha(generated) != generated_sha:
        raise ValueError("Generated web assets changed during compilation")
    for row in sdkconfigs:
        path = ROOT / "firmware" / ("sdkconfig." + row["environment"])
        if path.is_file():
            saved = output / "sdkconfigs-after" / path.name
            saved.parent.mkdir(exist_ok=True)
            shutil.copyfile(path, saved)
            row.update(after_sha256=sha(path), after_copy=str(saved.relative_to(output)))
    (output / "default-cache-after.json").write_text(json.dumps(after, indent=2) + "\n")
    (output / "sources-after.json").write_text(json.dumps(source_after, indent=2) + "\n")
    artifacts = [{"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha(path)}
                 for path in sorted((output / "build").glob("*/firmware.*")) if path.is_file()]
    archives = []
    archive_dir = output / "elf-archives"
    archive_dir.mkdir()
    for path in sorted((output / "build").glob("*/firmware.elf")):
        archive = archive_dir / (path.parent.name + ".elf.gz")
        body = path.read_bytes()
        with archive.open("xb") as target:
            with gzip.GzipFile(filename="", fileobj=target, mode="wb", mtime=0) as compressed:
                compressed.write(body)
        if gzip.decompress(archive.read_bytes()) != body:
            raise ValueError("ELF archive differs")
        archives.append({"environment": path.parent.name, "path": str(archive.relative_to(output)),
                         "bytes": archive.stat().st_size, "sha256": sha(archive),
                         "elf_bytes": len(body), "elf_sha256": sha(path)})
    web_environments = {"compact_n16r8_web", "compact_a3_web", "compact_n16r8_flex_dev"}
    embedded = []
    for name in environments:
        elf = output / "build" / name / "firmware.elf"
        expected_ui = name in web_environments
        current = elf.is_file() and embedded_index(elf, html)
        embedded.append({"environment": name, "web_expected": expected_ui, "current_index_in_flash_rodata": current})
        if expected_ui and not current:
            raise ValueError("Current UI absent from compiled flash rodata: " + name)
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "command": command, "exit_code": result.returncode,
              "build_dir_override": environment["PLATFORMIO_BUILD_DIR"], "environments": environments,
              "default_cache_retained": bool(before), "default_cache_unchanged": before == after,
              "source_inputs_unchanged": source_before == source_after, "generated_sdkconfigs": sdkconfigs,
              "artifacts": artifacts, "elf_archives": archives,
              "generated_assets_sha256": generated_sha, "web_index_sha256": hashlib.sha256(html).hexdigest(), "embedded_UI": embedded,
              "declared_generation_changes": generation_changes, "generation_only_declared_output": True,
              "flashed": False, "physical_qualification": False}
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    if result.returncode or before != after or source_before != source_after:
        raise RuntimeError("Build/source/cache verification failed; see " + str(output / "summary.json"))
    print(json.dumps({"environments": environments, "passed": True, "artifacts": len(artifacts), "default_cache_unchanged": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--environment", action="append", required=True)
    arguments = parser.parse_args()
    run(arguments.output, arguments.environment)
