#!/usr/bin/env python3
"""Create a compact frontside A6 placement candidate on a fresh unrouted copy.

Only R157..165/C158..160 change packages/placement, D213 moves with the filter,
C164 is added as local
pullup bypass, and U18 rotates90degrees about its body center with0.1mm lateral
clearance adjustment plus0.05mm down, putting feedback pins beside the freed
passive area and allowing the compact supply capacitor above the IC.
Logic values, pin bindings and all other devices stay fixed. Copper from the
routed source remains in that preserved source.
No fabrication, parasitic, physical assembly or engine qualification follows.
"""
import argparse
import csv
from dataclasses import asdict, fields
import hashlib
import json
from pathlib import Path
import re
import shutil

import pcbnew as p
import build_hardware as builder
from build_a5_idle_interface import box
from build_a6_flex_rgb import convert
from design import Part
from finish_a6_routes import copper_state, pad_state
from kicad9_carrier_copy import chunks
from pack_a6_analog import MOVABLE, pack_analog

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT / 'hardware/flex-input/frontend-compact.json')
    parser.add_argument('--attempts', type=int, default=96)
    parser.add_argument('--solver-seconds', type=float, default=120)
    args = parser.parse_args()
    source, out, profile_path = args.source.resolve(), args.output.resolve(), args.profile.resolve()
    assert not out.exists() and source != out and source not in out.parents
    contract = json.loads((source / 'net_contract.json').read_text())
    profile = json.loads(profile_path.read_text())
    assert contract['revision'] == 'A6-FLEX-RGB-HOLD'
    assert contract['flex_input']['source_sha256'] == profile['parent_revision']['source_sha256']
    assert profile['contract'] == 'FLEX-G38-FRONTEND-COMPACT-DRAFT2'
    old = {row['ref']: row for row in contract['parts']}
    desired = {row['ref']: convert(row, 'flex') for row in profile['parts']}
    package_changes = profile.get('existing_package_changes', {})
    assert set(package_changes) <= {'J20'}
    for ref, row in package_changes.items():
        desired[ref] = convert(row, old[ref]['page'])
    replaced = MOVABLE | set(package_changes)
    assert set(desired) - old.keys() == {'C164'}
    for ref, part in desired.items():
        if ref == 'C164':
            assert part.pins == {'1': '+3V3', '2': 'GND'}
        else:
            assert part.pins == old[ref]['pins'], ref
    before = p.LoadBoard(str(source / 'esp32-ecu.kicad_pcb'))
    assert before.GetTracks(), 'Use the preserved routed source for the explicit ECO'
    source_hashes = {str(f.relative_to(source)): sha(f) for f in source.rglob('*')
                     if f.is_file() and 'rule-controls' not in f.parts
                     and 'width-rule-sources' not in f.parts and f.suffix not in ('.kicad_prl', '.lck')}
    old_pads, old_copper = pad_state(before), copper_state(before)
    changed = replaced | {'U18'}
    fixed_pads = [row for row in old_pads if row[0] not in changed]
    preferred = {ref: list(old[ref]['placed_xy_mm']) for ref in MOVABLE if ref in old}
    preferred.update(C160=[94.43, 94.6], C159=[99.8, 109], R160=[94.5, 108.5],
                     R158=[103, 110.5], R159=[105.1, 101.5], C164=[110.2, 98],
                     R163=[107.4, 98.9])
    shield_bounds = box(next(f for f in before.GetFootprints() if f.GetReference() == 'J20'))
    shutil.copytree(source, out, ignore=shutil.ignore_patterns(
        'rule-controls', 'width-rule-sources', '*drc.*', '*.kicad_prl', '*.lck', '*~'))
    freeze = out / 'compact-source-freeze'
    freeze.mkdir(exist_ok=False)
    for item in (Path(__file__), Path(__file__).with_name('pack_a6_analog.py'),
                 ROOT / 'tools/solve_a6_analog_placement.py', profile_path):
        shutil.copyfile(item, freeze / item.name)
    mounted = {row['mounting']['footprint'] for row in profile['parts'] + list(package_changes.values())
               if 'mounting' in row}
    assets = {}
    for stem in sorted(mounted):
        src = ROOT / 'hardware/flex-input/footprints' / (stem + '.kicad_mod')
        dst = out / 'lib/ecu.pretty' / src.name
        if dst.exists():
            assert sha(dst) == sha(src)
        else:
            shutil.copyfile(src, dst)
        assets[stem] = dict(source=str(src.relative_to(ROOT)), sha256=sha(src))
    board_path = out / 'esp32-ecu.kicad_pcb'
    text = board_path.read_text()
    removed_copper = 0
    for kind in ('segment', 'arc', 'via'):
        for begin, end, _ in reversed(list(chunks(text, kind))):
            text = text[:begin] + text[end:]
            removed_copper += 1
    assert removed_copper == len(old_copper)
    removed_refs = set()
    for begin, end, block in reversed(list(chunks(text, 'footprint'))):
        match = re.search(r'\(property "Reference" "([^"]+)"', block)
        assert match
        if match[1] in replaced:
            removed_refs.add(match[1])
            text = text[:begin] + text[end:]
    assert removed_refs == replaced - {'C164'}
    board_path.write_text(text)
    board = p.LoadBoard(str(board_path))
    assert not board.GetTracks()
    comparator = next(f for f in board.GetFootprints() if f.GetReference() == 'U18')
    comparator_position = comparator.GetPosition()
    assert comparator.GetOrientationDegrees() == 0
    comparator.SetPosition(p.VECTOR2I(comparator_position.x + p.FromMM(.1),
                                     comparator_position.y + p.FromMM(7.67)))
    comparator.SetOrientationDegrees(90)
    for ref in sorted(replaced):
        part = desired[ref]
        fp = p.FootprintLoad(str(out / 'lib/ecu.pretty'), part.footprint.split(':')[-1])
        assert fp is not None
        fp.SetReference(ref)
        fp.SetValue(part.value)
        fp.SetFPID(p.LIB_ID('ECU', part.footprint.split(':')[-1]))
        fp.SetPath(p.KIID_PATH('/' + builder.uid('root') + '/' + builder.uid(part.page) + '/' + builder.uid(ref)))
        fp.Reference().SetLayer(p.F_Fab)
        fp.Reference().SetTextSize(p.VECTOR2I(p.FromMM(.8), p.FromMM(.8)))
        fp.Value().SetVisible(False)
        for name, value in (('MPN', part.mpn), ('DesignNote', part.note)):
            fp.SetField(name, value)
            field = fp.GetFieldByName(name)
            field.SetVisible(False)
            field.SetLayer(p.F_Fab)
        for pad in fp.Pads():
            pin = pad.GetNumber()
            assert part.pins[pin] is not None
            pad.SetNet(board.FindNet(part.pins[pin]))
            pad.SetPinType('passive')
        board.Add(fp)
    if 'J20' in package_changes:
        shield = next(f for f in board.GetFootprints() if f.GetReference() == 'J20')
        relative = box(shield)
        shield.SetPosition(p.VECTOR2I(p.FromMM(shield_bounds[2] - relative[2]),
                                     p.FromMM(shield_bounds[3] - relative[3])))
        current_bounds = box(shield)
        assert current_bounds[0] >= shield_bounds[0] and current_bounds[1] >= shield_bounds[1]
        assert current_bounds[2] <= shield_bounds[2] + 1e-6 and current_bounds[3] <= shield_bounds[3] + 1e-6
    try:
        packing = pack_analog(board, preferred, attempts=args.attempts,
                              problem_path=out / 'compact-packing-problem.json',
                              solver_seconds=args.solver_seconds)
    except Exception as error:
        (out / 'compact-packing-failure.json').write_text(json.dumps(dict(
            error=str(error), source=str(source), profile_sha256=sha(profile_path),
            script_sha256=sha(Path(__file__)), source_unchanged=True,
            candidate_complete=False, manufacturing_release=False), indent=2) + '\n')
        raise
    assert [row for row in pad_state(board) if row[0] not in changed] == fixed_pads
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    old['U18'].update(placed_xy_mm=[comparator.GetPosition().x / 1e6,
                                   comparator.GetPosition().y / 1e6],
                      placed_angle_deg=comparator.GetOrientationDegrees())
    for ref in replaced:
        row = asdict(desired[ref])
        fp = fps[ref]
        row.update(placed_xy_mm=[fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6],
                   placed_angle_deg=fp.GetOrientationDegrees(), placed_side='F.Cu')
        if ref in old:
            old[ref].update(row)
        else:
            contract['parts'].append(row)
            old[ref] = row
        assert {q.GetNumber(): q.GetNetname() for q in fps[ref].Pads()} == desired[ref].pins
    assert len(board.GetFootprints()) == len(contract['parts']) == 264
    p.ZONE_FILLER(board).Fill(board.Zones())
    p.SaveBoard(str(board_path), board)
    names = {f.name for f in fields(Part)}
    parts = [Part(**{k: v for k, v in row.items() if k in names}) for row in contract['parts']]
    builder.OUT, builder.LIB, builder.PARTS = out, out / 'lib', parts
    builder.NOTES = {'flex': 'A6 COMPACT HOLD. Smaller ordinary leaded passives and local3V3 bypass C164. Source/CAD checks only; parasitics, timing, supplies, heat, fit and target operation unqualified. Engine outputs inhibited.',
                     'core': 'A6 COMPACT HOLD. J20 internal PH2 shield/lining bond, no normal load current. H5 remains chassis lug. GPIO38 flex input; legacy LED/RMT incompatible. Module, RF, heat, fit and physical outputs unqualified; engine outputs inhibited.'}
    builder.write_sheet('flex')
    if package_changes:
        builder.write_sheet('core')
    library = out / 'lib/ecu.kicad_sym'
    text = library.read_text()
    for begin, end, block in reversed(list(chunks(text, 'symbol'))):
        match = re.match(r'\(symbol "([^"]+)"', block)
        if match and match[1] in removed_refs:
            text = text[:begin] + builder.symbol(desired[match[1]])[0] + text[end:]
    index = text.rfind(')')
    text = text[:index] + '\n' + builder.symbol(desired['C164'])[0] + '\n' + text[index:]
    library.write_text(text)
    contract['flex_input'].update(contract=profile['contract'], source_sha256=sha(profile_path),
                                  source_profile=str(profile_path.relative_to(ROOT)))
    contract.update(status='COMPACT_FRONTEND_PLACEMENT_UNROUTED_HOLD', manufacturing_release=False,
                    physical_fit_tested=False)
    (out / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    with (out / 'bom.csv').open('w', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['Reference', 'Value', 'MPN', 'Footprint', 'DNP', 'Assembly', 'Note'])
        for row in contract['parts']:
            writer.writerow([row['ref'], row['value'], row['mpn'], row['footprint'], row.get('dnp', False),
                             'Purchased module' if row['ref'] in ('U1', 'U3') else 'PCB feature'
                             if row['ref'].startswith(('H', 'TP')) else 'Direct-solder THT', row['note']])
    proof = dict(source=str(source), source_sha256=source_hashes,
        input_profile_sha256=sha(profile_path), generator_sha256=sha(Path(__file__)),
        packing_helper_sha256=sha(Path(__file__).with_name('pack_a6_analog.py')),
        mounted_asset_sha256=assets, removed_copper_count=removed_copper,
        source_copper_retained_in_original=True, old_geometry_unchanged_except=sorted(removed_refs | {'U18'}),
        old_logic_pin_bindings_unchanged=True, added_reference='C164',
        output_pcb_sha256=sha(board_path), packing=packing, scope=__doc__,
        inherited_derived_docs_require_reconciliation=True, manufacturing_release=False)
    (out / 'compact-frontend-eco.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert all(sha(source / name) == expected for name, expected in source_hashes.items())
    print(json.dumps(dict(output=str(out), count=264, direct_distances=packing['direct_pin_distances_mm'])), flush=True)


if __name__ == '__main__':
    main()
