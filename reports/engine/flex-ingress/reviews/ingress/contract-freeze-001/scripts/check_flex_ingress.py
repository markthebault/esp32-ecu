#!/usr/bin/env python3
"""Run native ingress scenarios and an owned standalone Xtensa placement probe.

No device, real SDK callback or Speeduino executable is run. This is not a
hardware timing, protected frontend, target worker or lossless capture test.
The output directory must be new so earlier receipts are never overwritten.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path.home() / ".platformio/packages/toolchain-xtensa-esp-elf/bin/xtensa-esp32s3-elf-"
FRAMEWORK = Path.home() / ".platformio/packages/framework-espidf"
ROOT_NAME = "flex_ingress_isr_probe"
LINKER = """ENTRY(flex_ingress_isr_probe)
SECTIONS {
 .iram0.text 0x40370000 : { *(.iram1.*.literal) *(.iram1 .iram1.*) }
 .dram0.data 0x3fc90000 : { *(.dram1 .dram1.*) *(.data .data.*) *(.bss .bss.*) }
 .flash.text 0x42000000 : { *(.literal .literal.*) *(.text .text.*) }
 .flash.rodata 0x3c000000 : { *(.rodata .rodata.*) *(.probe_flash) *(.eh_frame*) *(.init_array*) }
}
"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def audit(elf, directory):
    """Conservative no-call ISR root audit in this small freestanding ELF."""
    data = elf.read_bytes()
    require(data[:6] == b"\x7fELF\x01\x01", "Expected little endian ELF32")
    offset = struct.unpack_from("<I", data, 32)[0]
    step, count, strings_index = struct.unpack_from("<HHH", data, 46)
    headers = [struct.unpack_from("<IIIIIIIIII", data, offset + n * step) for n in range(count)]
    strings = data[headers[strings_index][4]:headers[strings_index][4] + headers[strings_index][5]]
    sections = {strings[h[0]:].split(b"\0", 1)[0].decode(): h for h in headers}

    def section_for(address):
        return next((name for name, h in sections.items() if h[3] and h[3] <= address < h[3] + h[5]), "UNKNOWN")

    def word(address):
        name = section_for(address)
        require(name != "UNKNOWN", "Unknown literal address")
        h = sections[name]
        return struct.unpack_from("<I", data, h[4] + address - h[3])[0]

    symbols_text = subprocess.check_output([str(PREFIX) + "nm", "-S", "-n", "-C", str(elf)], text=True)
    (directory / "symbols.txt").write_text(symbols_text)
    symbols = {}
    for line in symbols_text.splitlines():
        match = re.fullmatch(r"([0-9a-f]+) ([0-9a-f]+) [a-zA-Z] (.+)", line)
        if match:
            symbols[match[3]] = (int(match[1], 16), int(match[2], 16))
    require(ROOT_NAME in symbols, "Missing ISR probe root")
    start, size = symbols[ROOT_NAME]
    require(size > 0, "Empty ISR probe")

    def disassemble(address, end):
        text = subprocess.check_output([str(PREFIX) + "objdump", "-d", "-C", "--start-address=" + str(address), "--stop-address=" + str(end), str(elf)], text=True)
        parsed = {}
        for line in text.splitlines():
            match = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)", line)
            if match and not match[3].startswith("."):
                parsed[int(match[1], 16)] = {"bytes": match[2], "instruction": match[3]}
        return parsed

    # GNU's linear Xtensa decoder can lose alignment at jump-over padding.
    # Follow actual control flow and restart decoding at every missing PC.
    cache = disassemble(start, start + size)
    work, visited, instructions = [start], set(), []
    failures, literals = [], []
    while work:
        pc = work.pop()
        if pc in visited:
            continue
        if not start <= pc < start + size:
            failures.append("Branch leaves the audited root: " + hex(pc))
            continue
        if pc not in cache:
            cache.update(disassemble(pc, min(start + size, pc + 256)))
        require(pc in cache, "Cannot decode instruction at " + hex(pc))
        visited.add(pc)
        current = cache[pc]
        instruction = current["instruction"]
        instructions.append({"pc": hex(pc), **current})
        op = instruction.split()[0]
        if section_for(pc) != ".iram0.text":
            failures.append("Instruction outside IRAM")
        if op.startswith("call"):
            failures.append("Unexpected direct/indirect ISR call: " + instruction)
        if op in ("jx", "break", "break.n", "ill", "ill.n"):
            failures.append("Unresolved jump or trap: " + instruction)
        match = re.match(r"l32r\s+[^,]+, ([0-9a-f]+)", instruction)
        if match:
            address = int(match[1], 16)
            if section_for(address) != ".iram0.text":
                failures.append("Literal outside IRAM")
            value = word(address)
            literals.append({"pc": hex(pc), "literal": hex(address), "value": hex(value), "value_section": section_for(value)})
            if section_for(value).startswith(".flash"):
                failures.append("Flash pointer loaded in ISR")
        if op.startswith(("ret", "rfe", "rfde", "rfw")) or op in ("jx", "break", "break.n", "ill", "ill.n"):
            continue
        branch = op == "j" or op.startswith("b") and not op.startswith("break") or op.startswith("loop")
        if branch:
            match = re.search(r"([0-9a-f]+) <", instruction)
            require(match is not None, "Unresolved branch: " + instruction)
            work.append(int(match[1], 16))
            if op == "j":
                continue
        work.append(pc + len(current["bytes"]) // 2)
    state = {}
    for name in ("probe_ingress", "probe_clock"):
        require(name in symbols, "Missing probe state " + name)
        address, state_size = symbols[name]
        state[name] = {"address": hex(address), "bytes": state_size, "section": section_for(address)}
        if section_for(address) != ".dram0.data":
            failures.append("Probe state outside DRAM")
    require(state["probe_ingress"]["bytes"] <= 4096, "Ingress DRAM budget exceeded")
    report = {"elf_sha256": sha(elf), "root": ROOT_NAME, "root_bytes": size,
              "instruction_count": len(instructions), "state": state,
              "literals": literals, "failures": sorted(set(failures)), "passed": not failures,
              "scope": "standalone_ingress_and_clock_static_probe_not_actual_target_callback"}
    (directory / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    (directory / "root-disassembly.json").write_text(json.dumps(sorted(instructions, key=lambda x: int(x["pc"], 16)), indent=2) + "\n")
    return report


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def execute(command, name, environment=None):
        result = subprocess.run(list(map(str, command)), cwd=ROOT, env=environment, capture_output=True, text=True)
        (output / (name + ".stdout")).write_text(result.stdout)
        (output / (name + ".stderr")).write_text(result.stderr)
        commands.append({"command": list(map(str, command)), "returncode": result.returncode,
                         "stdout": name + ".stdout", "stderr": name + ".stderr"})
        (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        require(result.returncode == 0, "Command failed, see " + str(output / (name + ".stderr")))
        return result.stdout

    native = output / "native"
    native.mkdir()
    execute(["g++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-MMD", "-MF", native / "dependencies.d",
             "-I", ROOT / "firmware/include", ROOT / "firmware/tests/flex_ingress_test.cpp", "-o", native / "test"], "native-build")
    environment = {**os.environ, "ASAN_OPTIONS": "detect_leaks=1:abort_on_error=1", "UBSAN_OPTIONS": "halt_on_error=1",
                   "GCOV_PREFIX": str(output / "owned-gcov"), "GCOV_PREFIX_STRIP": "0"}
    native_text = execute([native / "test"], "native-run", environment)
    require(re.fullmatch(r"flex_ingress_checks [1-9][0-9]*\ningress_bytes [1-9][0-9]* edge_bytes [1-9][0-9]*\n", native_text), "Unexpected native result")
    require(not (output / "native-run.stderr").read_text(), "Unexpected native sanitizer diagnostics")
    linker = output / "probe.ld"
    linker.write_text(LINKER)
    for mode, name in enumerate(("xtensa", "xtensa-flash-negative", "xtensa-call-negative")):
        directory = output / name
        directory.mkdir()
        obj, elf = directory / "probe.o", directory / "probe.elf"
        execute([str(PREFIX) + "g++", "-std=c++17", "-Os", "-mlongcalls", "-ffunction-sections", "-fdata-sections",
                 "-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
                 "-Wall", "-Wextra", "-Werror", "-DESP_PLATFORM", "-DFLEX_PROBE_NEGATIVE_MODE=" + str(mode),
                 "-I", ROOT / "firmware/include", "-I", ROOT / "firmware/.pio/build/compact_n16r8_web/config",
                 "-I", FRAMEWORK / "components/esp_common/include", "-MMD", "-MF", directory / "dependencies.d", "-c",
                 ROOT / "firmware/tests/flex_ingress_xtensa_probe.cpp", "-o", obj], directory.name + "-compile")
        execute([str(PREFIX) + "g++", "-nostdlib", "-Wl,-T," + str(linker), obj, "-lgcc", "-o", elf], directory.name + "-link")
        report = audit(elf, directory)
        if mode == 1:
            require(not report["passed"] and "Flash pointer loaded in ISR" in report["failures"], "Owned flash negative was not rejected")
        elif mode == 2:
            require(not report["passed"] and any(f.startswith("Unexpected direct/indirect ISR call:") for f in report["failures"]), "Owned external-call negative was not rejected")
        else:
            require(report["passed"], "Standalone Xtensa audit failed")
    source_paths = {ROOT / "scripts/check_flex_ingress.py", ROOT / "hardware/flex-input/architecture.json", ROOT / "hardware/flex-input/README.md", ROOT / "docs/engine-flex-fuel.md", ROOT / "docs/engine-feature-coverage.md", ROOT / "scripts/test_firmware.sh"}
    for dependency in output.rglob("dependencies.d"):
        words = dependency.read_text().replace("\\\n", " ").split()
        source_paths.update(Path(word) for word in words[1:] if Path(word).is_file())
    sources = []
    for path in sorted(source_paths):
        relative = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else "external/" + str(path).lstrip("/")
        destination = output / "sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
        sources.append({"path": str(path), "snapshot": str(destination.relative_to(output)), "sha256": sha(path), "bytes": path.stat().st_size})
    tools = []
    for tool in (Path(subprocess.check_output(["which", "g++"], text=True).strip()), Path(str(PREFIX) + "g++"), Path(str(PREFIX) + "nm"), Path(str(PREFIX) + "objdump")):
        tools.append({"path": str(tool), "sha256": sha(tool), "version": subprocess.check_output([str(tool), "--version"], text=True).splitlines()[0]})
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "scope": "flex_integer_ingress",
               "checks_passed": True, "native": native_text.strip().splitlines(), "sources": sources, "tools": tools,
               "target_producer_implemented": False, "protected_circuit_implemented": False,
               "target_callback_audited": False, "physical_qualification": False,
               "production_reference_executed": False, "full_speeduino_parity": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(native_text.strip())
    print("Standalone Xtensa placement passed; owned flash/call negatives rejected. Target/circuit/HIL remain open.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
