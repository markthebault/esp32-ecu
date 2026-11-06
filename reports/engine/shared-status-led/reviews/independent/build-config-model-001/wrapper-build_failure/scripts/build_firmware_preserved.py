#!/usr/bin/env python3
"""Build in a new owned directory; retain and verify the default PIO cache.

PlatformIO removes its build directory when project configuration changes.
Never use this tool to flash; it runs only `pio run` in an isolated build root.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

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
    source_before = inputs()
    (output / "sources-before.json").write_text(json.dumps(source_before, indent=2) + "\n")
    environment = {**os.environ, "PLATFORMIO_BUILD_DIR": str(output / "build")}
    command = ["pio", "run", "-d", str(ROOT / "firmware")]
    for name in environments:
        command += ["-e", name]
    with (output / "build.log").open("xb") as log:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
    after, source_after = tree(default), inputs()
    (output / "default-cache-after.json").write_text(json.dumps(after, indent=2) + "\n")
    (output / "sources-after.json").write_text(json.dumps(source_after, indent=2) + "\n")
    artifacts = [{"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha(path)}
                 for path in sorted((output / "build").glob("*/firmware.*")) if path.is_file()]
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "command": command, "exit_code": result.returncode,
              "build_dir_override": environment["PLATFORMIO_BUILD_DIR"], "environments": environments,
              "default_cache_retained": bool(before), "default_cache_unchanged": before == after,
              "source_inputs_unchanged": source_before == source_after, "artifacts": artifacts,
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
