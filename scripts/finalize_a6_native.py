#!/usr/bin/env python3
"""Make a new A6 copy with explicit local variants for relocated assembly ink.

This does not route, alter copper/pads, relax DRC or release manufacturing files.
Native ERC/DRC/parity and independent circuit/copper review remain mandatory.
Run with the system KiCad 9 Python interpreter.
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

import pcbnew as pcb

from kicad9_carrier_copy import chunks
from route_a5_idle_interface import geometry


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(folder):
    return {
        str(p.relative_to(folder)): sha(p)
        for p in folder.rglob('*')
        if p.is_file() and p.suffix not in ('.kicad_prl', '.lck')
    }


def pads(board):
    return sorted(
        (f.GetReference(), p.GetNumber(), p.GetNetname(),
         p.GetPosition().x, p.GetPosition().y, p.GetSize().x, p.GetSize().y,
         p.GetDrillSize().x, p.GetDrillSize().y, p.GetOrientationDegrees())
        for f in board.GetFootprints() for p in f.Pads()
    )


def update_symbol_footprints(path, variants):
    text = path.read_text()
    changes = []
    for start, end, block in chunks(text, 'symbol'):
        match = re.match(r'\(symbol\s+(?:\(lib_id\s+)?"(?:ECU:)?([^"]+)"', block)
        if match is None or match[1] not in variants:
            continue
        ref = match[1]
        old, new = variants[ref]['old'], variants[ref]['new']
        updated, count = re.subn(
            r'(\(property\s+"Footprint"\s+)"[^"]+"',
            lambda m: m[1] + json.dumps(new), block)
        assert count == 1 and json.dumps(old) in block, (path, ref, count)
        changes.append((start, end, updated))
    for start, end, block in reversed(changes):
        text = text[:start] + block + text[end:]
    if changes:
        path.write_text(text)
    return len(changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--drc', type=Path, required=True,
                        help='Native DRC report identifying library mismatches')
    parser.add_argument('--routing-input', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    assert not output.exists(), 'Choose a fresh output; existing work is preserved'
    contract = json.loads((source / 'net_contract.json').read_text())
    assert contract['revision'] == 'A6-FLEX-RGB-HOLD'
    original = inventory(source)
    record = json.loads(args.routing_input.read_text())
    allowed = {m['reference'] for m in record['cosmetic_moves']
               if m['reference'] is not None}
    drc = json.loads(args.drc.read_text())
    references = set()
    for violation in drc['violations']:
        assert violation['type'] == 'lib_footprint_mismatch', violation['type']
        assert len(violation['items']) == 1
        description = violation['items'][0]['description']
        assert description.startswith('Footprint '), description
        references.add(description.removeprefix('Footprint '))
    assert references and references <= allowed, (references, allowed)
    shutil.copytree(source, output, ignore=shutil.ignore_patterns(
        '*.kicad_prl', '*.lck', '*~'))
    board_path = output / 'esp32-ecu.kicad_pcb'
    board = pcb.LoadBoard(str(board_path))
    old_pads, old_copper = pads(board), sorted(geometry(t) for t in board.GetTracks())
    footprints = {f.GetReference(): f for f in board.GetFootprints()}
    library = output / 'lib/ecu.pretty'
    plugin = pcb.PCB_IO_MGR.PluginFind(pcb.PCB_IO_MGR.KICAD_SEXP)
    assert plugin is not None
    variants = {}
    for ref in sorted(references):
        fp = footprints[ref]
        old = str(fp.GetFPID().GetLibItemName())
        new = old + '_A6_' + ref
        target = library / (new + '.kicad_mod')
        assert not target.exists()
        fp.SetFPID(pcb.LIB_ID('ECU', new))
        plugin.FootprintSave(str(library), fp)
        assert target.is_file()
        variants[ref] = dict(
            old='ECU:' + old, new='ECU:' + new,
            library_sha256=sha(target),
            reason='Only the recorded overlapping ink was moved from F.SilkS '
                   'to F.Fab. Copper, pads, courtyard and body geometry retained.',
            moved_ink=[m for m in record['cosmetic_moves'] if m['reference'] == ref])
        row = next(p for p in contract['parts'] if p['ref'] == ref)
        assert row['footprint'].split(':')[-1] == old
        row['footprint'] = 'ECU:' + new
    assert pads(board) == old_pads
    assert sorted(geometry(t) for t in board.GetTracks()) == old_copper
    pcb.SaveBoard(str(board_path), board)
    check = pcb.LoadBoard(str(board_path))
    assert pads(check) == old_pads
    assert sorted(geometry(t) for t in check.GetTracks()) == old_copper
    count = 0
    for path in list(output.glob('*.kicad_sch')) + [output / 'lib/ecu.kicad_sym']:
        count += update_symbol_footprints(path, variants)
    assert count == 3 * len(variants), (count, variants)
    (output / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    with (output / 'bom.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        if row['Reference'] in variants:
            row['Footprint'] = variants[row['Reference']]['new']
    with (output / 'bom.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    fit_path = output / 'module-fit.json'
    fit = json.loads(fit_path.read_text())
    fit.update(
        status_led='MCP23008 0x21 GP0/1/2 drives ordinary common-anode RGB '
                   'through three NPN sinks; J23 PH5. No GPIO38 RMT/WS2812.',
        gpio38='U3 pad32 protected flex input candidate, J22 VH3; sensor '
               'supply/pinout/protection and physical behavior unqualified.',
        compatible_build='compact_n16r8_flex_dev',
        manufacturing_release=False)
    fit_path.write_text(json.dumps(fit, indent=2) + '\n')
    evidence = dict(
        source_directory=str(source), source_sha256=original,
        drc_report_sha256=sha(args.drc),
        routing_input_sha256=sha(args.routing_input), variants=variants,
        pads_and_copper_unchanged=True,
        native_checks_pending=True, manufacturing_release=False,
        qualification=__doc__)
    (output / 'local-footprint-variants.json').write_text(
        json.dumps(evidence, indent=2) + '\n')
    assert inventory(source) == original, 'Source copy changed during operation'
    print(f'Created {output}; {len(variants)} assembly-ink variants, '
          'pad/copper geometry unchanged; fresh native checks required')


if __name__ == '__main__':
    main()
