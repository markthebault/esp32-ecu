#!/usr/bin/env python3
"""Add the declared RGB common-supply resistor to a fresh unrouted A6 copy.

Only the explicit DRAFT2 to DRAFT3 ECO is allowed: R179 is added and J23 pin1
changes from +5V to LED_5V. Original footprints/pad geometry and all other pin
nets are preserved unless an explicit full repack is selected. Source copies
are never changed; no fabrication release or physical assembly qualification.
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
from dataclasses import asdict, fields
from pathlib import Path

import pcbnew as pcb

import build_hardware as builder
from build_a5_idle_interface import place
from build_a6_flex_rgb import convert
from design import Part
from kicad9_carrier_copy import chunks
from pack_a6 import pack
from place_a6_back import place_back
from place_a6_front import place_corner

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def physical_pads(board):
    return sorted((f.GetReference(), p.GetNumber(), p.GetPosition().x,
                   p.GetPosition().y, p.GetSize().x, p.GetSize().y,
                   p.GetDrillSize().x, p.GetDrillSize().y)
                  for f in board.GetFootprints() for p in f.Pads() if p.GetNumber())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repack', action='store_true',
                        help='Explicitly permit a completely new placement and route')
    parser.add_argument('--packing-attempts', type=int, default=512)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    assert not output.exists(), 'Choose a fresh output'
    contract = json.loads((source / 'net_contract.json').read_text())
    assert contract['revision'] == 'A6-FLEX-RGB-HOLD'
    profile_path = ROOT / 'hardware/flex-input/status-led.json'
    profile = json.loads(profile_path.read_text())
    change = profile['harness_supply_revision']
    assert contract['status_led']['contract'] == change['parent_contract']
    assert contract['status_led']['source_sha256'] == change['parent_source_sha256']
    assert profile['contract'] in ('RGB-MCP21-DRAFT3', 'RGB-MCP21-DRAFT4')
    current = {p['ref']: p for p in contract['parts']}
    assert 'R179' not in current
    assert current['J23']['pins']['1'] == '+5V'
    assert change['changed_existing_pin'] == {'J23': {'1': {'old': '+5V', 'new': 'LED_5V'}}}
    desired = {r['ref']: convert(r, 'status_led') for r in profile['parts']}
    mounting = next(r for r in profile['parts'] if r['ref'] == 'R179').get('mounting', {})
    back = mounting.get('side') == 'B.Cu'
    assert not (back and args.repack), 'Back-mount profile preserves the front placement; omit--repack'
    assert set(desired) - current.keys() == {'R179'}
    for ref, part in desired.items():
        if ref == 'R179':
            continue
        expected = dict(current[ref]['pins'])
        if ref == 'J23':
            expected['1'] = 'LED_5V'
        assert part.pins == expected, ('Unexpected topology change', ref)
    source_hashes = {str(p.relative_to(source)): sha(p) for p in source.rglob('*')
                     if p.is_file() and p.suffix not in ('.kicad_prl', '.lck')}
    board = pcb.LoadBoard(str(source / 'esp32-ecu.kicad_pcb'))
    assert not board.GetTracks(), 'This ECO requires an explicit unrouted copy'
    old_pads = physical_pads(board)
    old_nets = {(f.GetReference(), p.GetNumber()): p.GetNetname()
                for f in board.GetFootprints() for p in f.Pads() if p.GetNumber()}
    shutil.copytree(source, output, ignore=shutil.ignore_patterns('*.kicad_prl', '*.lck', '*~'))
    if board.FindNet('LED_5V') is None:
        board.Add(pcb.NETINFO_ITEM(board, 'LED_5V'))
    jack = next(f for f in board.GetFootprints() if f.GetReference() == 'J23')
    pad = next(p for p in jack.Pads() if p.GetNumber() == '1')
    pad.SetNet(board.FindNet('LED_5V'))
    part = desired['R179']
    authored_fp = ROOT / 'hardware/flex-input/footprints' / (part.footprint.split(':')[-1] + '.kicad_mod')
    if authored_fp.exists():
        target = output / 'lib/ecu.pretty' / authored_fp.name
        assert not target.exists()
        shutil.copyfile(authored_fp, target)
    fp = pcb.FootprintLoad(str(output / 'lib/ecu.pretty'), part.footprint.split(':')[-1])
    assert fp is not None
    fp.SetReference(part.ref)
    fp.SetValue(part.value)
    fp.SetFPID(pcb.LIB_ID('ECU', part.footprint.split(':')[-1]))
    fp.SetPath(pcb.KIID_PATH('/' + builder.uid('root') + '/' + builder.uid('status_led') + '/' + builder.uid(part.ref)))
    if back:
        # Native KiCad needs the owning board's layer stack when flipping.
        board.Add(fp)
        fp.Flip(fp.GetPosition(), False)
    fp.Reference().SetLayer(pcb.B_Fab if back else pcb.F_Fab)
    fp.Reference().SetTextSize(pcb.VECTOR2I(pcb.FromMM(.8), pcb.FromMM(.8)))
    fp.Value().SetVisible(False)
    for pad in fp.Pads():
        pad.SetNet(board.FindNet(part.pins[pad.GetNumber()]))
    preferred = [jack.GetPosition().x / 1e6, jack.GetPosition().y / 1e6]
    back_check = None
    if back:
        xy, angle, back_check = place_back(board, fp, preferred, already_added=True)
    elif args.repack:
        fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(preferred[0]), pcb.FromMM(preferred[1])))
        board.Add(fp)
        xy, angle = preferred, 0
    else:
        xy, angle = place_corner(board, fp, preferred)
    new_row = asdict(part)
    new_row.update(placed_xy_mm=xy, placed_angle_deg=angle, placed_side='B.Cu' if back else 'F.Cu')
    contract['parts'].append(new_row)
    current['J23'].update(pins=desired['J23'].pins, names=desired['J23'].names,
                          note=desired['J23'].note)
    packing = None
    if args.repack:
        field_names = {f.name for f in fields(Part)}
        objects = {r['ref']: Part(**{k: v for k, v in r.items() if k in field_names})
                   for r in contract['parts']}
        desired_xy = {r['ref']: r['placed_xy_mm'] for r in contract['parts']}
        packing = pack(board, objects, desired_xy, attempts=args.packing_attempts,
                       problem_path=output / 'guard-packing-input.json')
        for row in contract['parts']:
            position = packing['positions'][row['ref']]
            row.update(placed_xy_mm=position['xy_mm'], placed_angle_deg=position['angle_deg'])
        xy = new_row['placed_xy_mm']
        angle = new_row['placed_angle_deg']
    else:
        after_pads = [r for r in physical_pads(board) if r[0] != 'R179']
        assert after_pads == old_pads
    for f in board.GetFootprints():
        for p in f.Pads():
            if not p.GetNumber():
                continue
            key = (f.GetReference(), p.GetNumber())
            if key not in old_nets:
                assert key[0] == 'R179'
            else:
                assert p.GetNetname() == ('LED_5V' if key == ('J23', '1') else old_nets[key]), key
    pcb.ZONE_FILLER(board).Fill(board.Zones())
    pcb.SaveBoard(str(output / 'esp32-ecu.kicad_pcb'), board)
    names = {f.name for f in fields(Part)}
    all_parts = [Part(**{k: v for k, v in row.items() if k in names}) for row in contract['parts']]
    builder.OUT, builder.LIB, builder.PARTS = output, output / 'lib', all_parts
    builder.NOTES = {'status_led': 'A6 HOLD. Common330R supply plus per-color cathode resistors. GP0/1/2 selects red/green/blue; unused outputs low. Reset/readback/power/brightness/temperature and sealed optics unqualified. No fabrication or physical engine release.'}
    builder.write_sheet('status_led')
    library = output / 'lib/ecu.kicad_sym'
    text = library.read_text()
    matches = [(s, e) for s, e, block in chunks(text, 'symbol')
               if re.match(r'\(symbol\s+"J23"\s', block)]
    assert len(matches) == 1
    start, end = matches[0]
    text = text[:start] + builder.symbol(desired['J23'])[0] + text[end:]
    last = text.rfind(')')
    text = text[:last] + '\n' + builder.symbol(part)[0] + '\n' + text[last:]
    library.write_text(text)
    contract['status_led'].update(contract=profile['contract'], source_sha256=sha(profile_path))
    contract['status'] = 'RGB_SUPPLY_ECO_UNROUTED_DRAFT_NOT_FOR_FABRICATION'
    (output / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    # The normal metadata/BOM reconciler performs the final regeneration on
    # another fresh copy. Give it the complete per-reference input now.
    with (output / 'bom.csv').open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['Reference', 'Value', 'MPN', 'Footprint', 'DNP', 'Assembly', 'Note'])
        for row in contract['parts']:
            writer.writerow([row['ref'], row['value'], row['mpn'], row['footprint'],
                             row.get('dnp', False), 'Purchased module' if row['ref'] in ('U1', 'U3')
                             else 'PCB feature' if row['ref'].startswith(('H', 'TP'))
                             else 'Direct-solder THT', row['note']])
    (output / 'rgb-supply-eco.json').write_text(json.dumps(dict(
        source_directory=str(source), source_sha256=source_hashes,
        profile_sha256=sha(profile_path), generator_sha256=sha(Path(__file__)),
        added_reference='R179', placement_xy_mm=xy, placement_angle_deg=angle,
        changed_pin=change['changed_existing_pin'], all_old_pad_geometry_unchanged=not args.repack,
        complete_new_placement=args.repack, complete_new_route_required=True,
        packing=packing, back_placement_check=back_check,
        authored_footprint_sha256=sha(authored_fp) if authored_fp.exists() else None,
        all_other_old_nets_unchanged=True, manufacturing_release=False,
        scope=__doc__), indent=2) + '\n')
    assert all(sha(source / p) == h for p, h in source_hashes.items())
    print('Created guarded RGB candidate with', len(contract['parts']), 'footprints; R179 at', xy, angle)


if __name__ == '__main__':
    main()
