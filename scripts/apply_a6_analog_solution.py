#!/usr/bin/env python3
"""Apply a source-bound analog placement solution on a fresh unrouted A6 copy.

Only the fourteen compact passive/filter footprints may move. Recheck native
geometry before saving; copper, parasitics, assembly and engine use remain open.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

import pcbnew as p

from build_a5_idle_interface import box, overlaps
from finish_a6_routes import pad_state
from pack_a6_analog import GOALS, MOVABLE


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, ('Duplicate JSON key', key)
        result[key] = value
    return result


def read(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_object)


def origin(fp):
    return [fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6]


def pins(fp):
    return {q.GetNumber(): [q.GetPosition().x / 1e6, q.GetPosition().y / 1e6]
            for q in fp.Pads()}


def same(first, second):
    assert len(first) == len(second)
    assert all(abs(a - b) <= 1e-6 for a, b in zip(first, second)), (first, second)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--solution', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, output, solution = (x.resolve() for x in
                                (args.source, args.output, args.solution))
    assert not output.exists() and source not in output.parents
    problem_path = source / 'compact-packing-problem.json'
    problem, answer = read(problem_path), read(solution)
    assert problem['schema'] == 2
    assert answer['status'] in ('FEASIBLE', 'OPTIMAL')
    assert answer['problem_sha256'] == sha(problem_path)
    assert set(answer['positions']) == set(problem['movable']) == MOVABLE
    assert problem['goals'] == json.loads(json.dumps(GOALS))
    source_hashes = {str(f.relative_to(source)): sha(f) for f in source.rglob('*')
                     if f.is_file() and f.suffix not in ('.kicad_prl', '.lck')}
    board_path = source / 'esp32-ecu.kicad_pcb'
    board = p.LoadBoard(str(board_path))
    assert not board.GetTracks(), 'Only an unrouted source is supported'
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    assert len(fps) == len(board.GetFootprints()) == 264
    assert set(fps) - MOVABLE == set(problem['fixed'])
    before_pads = pad_state(board)
    fixed_pads = [row for row in before_pads if row[0] not in MOVABLE]
    for ref, data in problem['fixed'].items():
        same(box(fps[ref]), data['court_mm'])
        actual_pins = pins(fps[ref])
        assert actual_pins.keys() == data['absolute_pads_mm'].keys()
        for pin, point in data['absolute_pads_mm'].items():
            same(actual_pins[pin], point)
    old_positions = {ref: dict(xy_mm=origin(fps[ref]),
                              angle_deg=fps[ref].GetOrientationDegrees())
                     for ref in sorted(MOVABLE)}
    for ref, row in answer['positions'].items():
        fp = fps[ref]
        angle = row['angle_deg']
        assert angle in (0, 90, 180, 270)
        xy = row['xy_mm']
        assert len(xy) == 2 and all(type(v) in (int, float) and math.isfinite(v)
                                   for v in xy)
        fp.SetPosition(p.VECTOR2I(0, 0))
        fp.SetOrientationDegrees(angle)
        expected = problem['movable'][ref]
        same(box(fp), expected['rotated_courts_mm'][str(angle)])
        actual_pins = pins(fp)
        assert actual_pins.keys() == expected['rotated_pads_mm'][str(angle)].keys()
        for pin, point in expected['rotated_pads_mm'][str(angle)].items():
            same(actual_pins[pin], point)
        fp.SetPosition(p.VECTOR2I(p.FromMM(xy[0]), p.FromMM(xy[1])))
    assert [row for row in pad_state(board) if row[0] not in MOVABLE] == fixed_pads
    courts = {ref: box(fp) for ref, fp in fps.items()}
    bounds, gap = problem['bounds_mm'], problem['gap_mm']
    for ref in MOVABLE:
        court = courts[ref]
        assert court[0] >= bounds[0] and court[1] >= bounds[1]
        assert court[2] <= bounds[2] and court[3] <= bounds[3]
        assert not overlaps(court, problem['antenna_mm'], gap - 1e-5)
        assert not any(overlaps(court, other_court, gap - 1e-5)
                       for other, other_court in courts.items() if other != ref), ref
    distances = {}
    for ref, rows in GOALS.items():
        for pin, owner, owner_pin, maximum, _ in rows:
            distance = math.dist(pins(fps[ref])[pin], pins(fps[owner])[owner_pin])
            assert distance <= maximum, (ref, pin, owner, owner_pin, distance)
            distances[f'{ref}.{pin}_to_{owner}.{owner_pin}'] = distance
    contract = read(source / 'net_contract.json')
    assert contract['revision'] == 'A6-FLEX-RGB-HOLD'
    assert len(contract['parts']) == len({row['ref'] for row in contract['parts']}) == 264
    for row in contract['parts']:
        fp = fps[row['ref']]
        if row['ref'] in MOVABLE:
            row.update(placed_xy_mm=origin(fp), placed_angle_deg=fp.GetOrientationDegrees())
        actual = {q.GetNumber(): q.GetNetname() for q in fp.Pads() if q.GetNumber()}
        assert actual.keys() == row['pins'].keys(), row['ref']
        for pin, net in row['pins'].items():
            if net is None:
                assert actual[pin].startswith('unconnected-(' + row['ref'] + '-')
                assert actual[pin].endswith('-Pad' + pin + ')')
            else:
                assert actual[pin] == net, (row['ref'], pin, actual[pin], net)
    # Every pre-existing receipt remains an inherited historical source receipt;
    # this new receipt identifies the output board and the applied solution.
    shutil.copytree(source, output, ignore=shutil.ignore_patterns(
        '*.kicad_prl', '*.lck', '*~'))
    p.ZONE_FILLER(board).Fill(board.Zones())
    p.SaveBoard(str(output / 'esp32-ecu.kicad_pcb'), board)
    contract.update(placement_update='analog-placement-update.json',
                    manufacturing_release=False, physical_fit_tested=False)
    (output / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    freeze = output / 'analog-placement-update-sources'
    freeze.mkdir()
    for path in (Path(__file__), Path(__file__).with_name('pack_a6_analog.py'), solution):
        shutil.copyfile(path, freeze / path.name)
    proof = dict(source_directory=str(source), source_sha256=source_hashes,
        problem_sha256=sha(problem_path), solution_sha256=sha(solution),
        solver_status=answer['status'], solution_file=str(solution),
        inherited_receipts_describe_source=True, old_positions=old_positions,
        positions=answer['positions'], direct_pin_distances_mm=distances,
        changed_references=sorted(MOVABLE), fixed_pads_unchanged=True,
        native_geometry_rechecked=True, native_drc_required=True,
        output_pcb_sha256=sha(output / 'esp32-ecu.kicad_pcb'),
        output_contract_sha256=sha(output / 'net_contract.json'),
        scope=__doc__, routing_required=True, manufacturing_release=False,
        physical_fit_qualified=False)
    (output / 'analog-placement-update.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert all(sha(source / name) == value for name, value in source_hashes.items())
    print(json.dumps(dict(output=str(output), direct_pin_distances_mm=distances)))


if __name__ == '__main__':
    main()
