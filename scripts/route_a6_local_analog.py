#!/usr/bin/env python3
"""Route the compact A6 feedback and bypass branches before general copper.

Each branch uses one declared signal layer, no added vias, native DRC/parity
gates and an explicit length ceiling. This is conditional layout work, not a
parasitic extraction, circuit qualification or fabrication release.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import pcbnew as p

import finish_a6_routes as routing

# Input and comparator-output traces occupy different layers with an intervening
# ground plane. Actual return continuity/capacitance still requires review.
BRANCHES = [
    ('FLEX_CMP', 'U18', '1', 'R160', '1', p.B_Cu, 1.5, 2),
    ('FLEX_IN', 'R160', '2', 'U18', '3', p.In2_Cu, 1.5, 2),
    ('+5V', 'C160', '1', 'U18', '8', p.F_Cu, 1, 2),
    ('+3V3', 'C164', '1', 'R163', '1', p.F_Cu, 1, 2),
    ('FLEX_REF', 'C159', '1', 'U18', '2', p.F_Cu, 1, 2),
    ('FLEX_IN', 'R158', '2', 'U18', '3', p.In2_Cu, 1.5, 2),
    ('FLEX_IN', 'R159', '1', 'U18', '3', p.In2_Cu, 1.5, 2),
    ('FLEX_REF', 'R162', '1', 'U18', '2', p.F_Cu, 1.5, 3),
    ('FLEX_REF', 'R161', '2', 'U18', '2', p.F_Cu, 1.5, 3),
    ('FLEX_REF', 'U18', '6', 'U18', '2', p.F_Cu, 1.5, 3),
    ('FLEX_CMP', 'R163', '2', 'U18', '1', p.B_Cu, 1.5, 3),
    ('FLEX_CMP', 'R164', '1', 'U18', '1', p.B_Cu, 1.5, 3),
    ('FLEX', 'R165', '1', 'R164', '2', p.In3_Cu, 1.5, 3),
    ('FLEX_INPUT_MID', 'C158', '1', 'R158', '1', p.In2_Cu, 1.5, 2),
    ('FLEX_INPUT_MID', 'D213', '1', 'R158', '1', p.In2_Cu, 1.5, 2),
    ('FLEX_INPUT_MID', 'R157', '2', 'R158', '1', p.In2_Cu, 1.5, 2),
]


def copy(source, output):
    shutil.copytree(source, output, ignore=shutil.ignore_patterns(
        '*drc.*', 'rule-controls', 'width-rule-sources', '*.kicad_prl', '*.lck', '*~'))


def connected_ids(board, start):
    connectivity = board.GetConnectivity()
    connectivity.Build(board)
    pending, seen = [start], set()
    while pending:
        item = pending.pop()
        uid = item.m_Uuid.AsString()
        if uid in seen:
            continue
        seen.add(uid)
        pending.extend(connectivity.GetConnectedTracks(item))
        pending.extend(connectivity.GetConnectedPads(item))
    return seen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--step', type=float, default=.05)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    assert source not in output.parents and not output.exists()
    assert .025 <= args.step <= .1
    contract = json.loads((source / 'net_contract.json').read_text())
    assert contract['revision'] == 'A6-FLEX-RGB-HOLD'
    assert contract['flex_input']['contract'] == 'FLEX-G38-FRONTEND-COMPACT-DRAFT2'
    source_hashes = {f.name: routing.sha(f) for f in source.iterdir() if f.is_file()}
    original = p.LoadBoard(str(source / 'esp32-ecu.kicad_pcb'))
    assert not original.GetTracks(), 'Start from the revised unrouted placement'
    pads = routing.pad_state(original)
    output.mkdir(parents=True)
    freeze = output / 'sources'
    freeze.mkdir()
    for path in (Path(__file__), Path(routing.__file__)):
        shutil.copyfile(path, freeze / path.name)
    selected = output / 'baseline'
    copy(source, selected)
    drc = routing.native_drc(selected)
    baseline = routing.drc_summary(drc)
    assert not baseline['physical'] and not baseline['parity'] and not baseline['dangling']
    trials = []

    def receipt():
        proof = dict(source=str(source), source_sha256=source_hashes,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            command=sys.argv, selected=str(selected), baseline=baseline,
            current=routing.drc_summary(drc), trials=trials,
            complete=len(trials) == len(BRANCHES) and all(t['accepted'] for t in trials),
            routing_required=True, independent_copper_review_required=True,
            scope=__doc__, manufacturing_release=False, physical_fit_qualified=False)
        (output / 'local-analog-results.json').write_text(json.dumps(proof, indent=2) + '\n')

    for number, (net, ref1, pin1, ref2, pin2, layer, factor, allowance) in enumerate(BRANCHES, 1):
        board = p.LoadBoard(str(selected / 'esp32-ecu.kicad_pcb'))
        pins = {(f.GetReference(), q.GetNumber()): q for f in board.GetFootprints() for q in f.Pads()}
        start, end = pins[ref1, pin1], pins[ref2, pin2]
        assert start.GetNetname() == end.GetNetname() == net
        direct = math.dist(routing.xy(start.GetPosition()), routing.xy(end.GetPosition()))
        ceiling = factor * direct + allowance
        row = dict(branch=number, net=net, start=f'{ref1}.{pin1}', end=f'{ref2}.{pin2}',
                   layer=board.GetLayerName(layer), direct_mm=direct, maximum_added_length_mm=ceiling)
        if end.m_Uuid.AsString() in connected_ids(board, start):
            row.update(accepted=True, already_connected=True)
            trials.append(row)
            receipt()
            print(json.dumps(row), flush=True)
            continue
        old_layers = routing.LAYERS
        routing.LAYERS = (layer,)
        try:
            row.update(routing.route(board, net, routing.item_points(start), routing.item_points(end),
                                     args.step, 500000, 5, 1))
            assert row['vias'] == 0 and row['length_mm'] <= ceiling, row
        except (RuntimeError, AssertionError) as error:
            row.update(accepted=False, error=str(error))
            trials.append(row)
            receipt()
            print(json.dumps(row), flush=True)
            break
        finally:
            routing.LAYERS = old_layers
        trial = output / f'trial-{number:03d}'
        copy(selected, trial)
        p.ZONE_FILLER(board).Fill(board.Zones())
        assert routing.pad_state(board) == pads
        pcb_path = trial / 'esp32-ecu.kicad_pcb'
        p.SaveBoard(str(pcb_path), board)
        next_drc = routing.native_drc(trial)
        before = routing.drc_summary(drc)
        after = routing.drc_summary(next_drc)
        checked = p.LoadBoard(str(pcb_path))
        checked_pins = {(f.GetReference(), q.GetNumber()): q
                        for f in checked.GetFootprints() for q in f.Pads()}
        pair_connected = checked_pins[ref2, pin2].m_Uuid.AsString() in connected_ids(checked, checked_pins[ref1, pin1])
        row.update(accepted=bool(not after['physical'] and not after['parity']
                     and not after['dangling'] and after['unconnected'] < before['unconnected']
                     and pair_connected), pair_connected=pair_connected,
                   unconnected=after['unconnected'], physical_findings=len(after['physical']),
                   parity=after['parity'], dangling=after['dangling'],
                   pcb_sha256=routing.sha(pcb_path), path=str(pcb_path))
        trials.append(row)
        if row['accepted']:
            selected, drc = trial, next_drc
        receipt()
        print(json.dumps(row), flush=True)
        if not row['accepted']:
            break
    assert all(routing.sha(source / name) == value for name, value in source_hashes.items())


if __name__ == '__main__':
    main()
