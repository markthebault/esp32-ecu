#!/usr/bin/env python3
"""Restore unchanged routed A6 copper around priority compact analog branches.

The old source and priority source are preserved. Old analog-signal copper and
old changed-pad attachments are excluded explicitly. Only imported old copper
may be removed to resolve native conflicts. New pads/branches and rules stay
fixed. This does not establish parasitics, current, assembly or qualification.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

import pcbnew as p

from finish_a6_routes import copper_state, drc_summary, native_drc, pad_state, sha
from kicad9_carrier_copy import chunks
from pack_a6_analog import MOVABLE

REPLACE_NETS = {'FLEX_RAW', 'FLEX_INPUT_MID', 'FLEX_IN', 'FLEX_REF', 'FLEX_CMP', 'FLEX'}
CHANGED_OLD_PADS = (MOVABLE - {'C164'}) | {'U18', 'J20'}


def copy(source, output):
    shutil.copytree(source, output, ignore=shutil.ignore_patterns(
        '*drc.*', 'rule-controls', 'width-rule-sources', '*.kicad_prl', '*.lck', '*~'))


def net_codes(board):
    return {net.GetNetCode(): net.GetNetname()
            for net in board.GetNetInfo().NetsByNetcode().values()}


def copper_blocks(text):
    result = {}
    for kind in ('segment', 'arc', 'via'):
        for begin, end, block in chunks(text, kind):
            matches = re.findall(r'\(uuid "([^"]+)"\)', block)
            assert len(matches) == 1 and matches[0] not in result
            result[matches[0]] = (begin, end, block)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routed-source', type=Path, required=True)
    parser.add_argument('--priority-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    old, priority, output = (x.resolve() for x in
                             (args.routed_source, args.priority_source, args.output))
    assert not output.exists() and old not in output.parents and priority not in output.parents
    old_path, priority_path = (x / 'esp32-ecu.kicad_pcb' for x in (old, priority))
    old_hash, priority_hash = sha(old_path), sha(priority_path)
    old_board, priority_board = (p.LoadBoard(str(x)) for x in (old_path, priority_path))
    for folder in (old, priority):
        assert json.loads((folder / 'net_contract.json').read_text())['revision'] == 'A6-FLEX-RGB-HOLD'
    assert len(old_board.GetFootprints()) == 263 and len(priority_board.GetFootprints()) == 264
    assert net_codes(old_board) == net_codes(priority_board), 'Raw net codes must match by name'
    old_copper, priority_copper = copper_state(old_board), copper_state(priority_board)
    assert old_copper and priority_copper and not old_copper.keys() & priority_copper.keys()
    desired_pads = pad_state(priority_board)
    moved_pads = [q for f in old_board.GetFootprints()
                  if f.GetReference() in CHANGED_OLD_PADS for q in f.Pads()]
    excluded, imported = {}, set()
    for track in old_board.GetTracks():
        uid = track.m_Uuid.AsString()
        attachments = [q.m_Uuid.AsString() for q in moved_pads
                       if q.GetNetname() == track.GetNetname()
                       and (q.HitTest(track.GetStart()) or q.HitTest(track.GetEnd()))]
        if track.GetNetname() in REPLACE_NETS or attachments:
            excluded[uid] = dict(geometry=old_copper[uid],
                reason='replaced analog signal net' if track.GetNetname() in REPLACE_NETS
                       else 'old attachment at a replaced or moved pad',
                old_pad_uuids=attachments)
        else:
            imported.add(uid)
    blocks = copper_blocks(old_path.read_text())
    assert blocks.keys() == old_copper.keys()
    output.mkdir(parents=True)
    freeze = output / 'sources'
    freeze.mkdir()
    shutil.copyfile(Path(__file__), freeze / Path(__file__).name)
    selected = output / 'round-000'
    copy(priority, selected)
    path = selected / 'esp32-ecu.kicad_pcb'
    text = path.read_text()
    index = text.rfind(')')
    text = text[:index] + '\n' + '\n'.join(blocks[uid][2] for uid in sorted(imported)) + '\n' + text[index:]
    path.write_text(text)
    removed, rounds = set(), []
    for number in range(33):
        board = p.LoadBoard(str(path))
        assert pad_state(board) == desired_pads
        state = copper_state(board)
        assert state == (priority_copper | {uid: old_copper[uid] for uid in imported - removed})
        p.ZONE_FILLER(board).Fill(board.Zones())
        p.SaveBoard(str(path), board)
        drc = native_drc(selected)
        summary = drc_summary(drc)
        to_remove, unresolved = set(), []
        for finding in summary['physical']:
            ids = {item['uuid'] for item in finding['items']}
            old_ids = ids & (imported - removed)
            if old_ids:
                to_remove.update(old_ids)
            else:
                unresolved.append(finding)
        row = dict(round=number, directory=str(selected), pcb_sha256=sha(path),
            unconnected=summary['unconnected'], dangling=summary['dangling'],
            parity=summary['parity'], physical_count=len(summary['physical']),
            physical_types=dict(Counter(v['type'] for v in summary['physical'])),
            next_old_copper_removals=sorted(to_remove), unresolved_findings=unresolved)
        rounds.append(row)
        proof = dict(routed_source=str(old), routed_source_pcb_sha256=old_hash,
            priority_source=str(priority), priority_source_pcb_sha256=priority_hash,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), command=sys.argv,
            excluded_old_copper=excluded, imported_old_count=len(imported),
            removed_conflicting_old_geometry={uid: old_copper[uid] for uid in sorted(removed)},
            selected=str(selected), priority_pads_and_copper_unchanged=True,
            rounds=rounds, complete=not summary['physical'] and not summary['parity'],
            current=summary, routing_required=True, independent_copper_review_required=True,
            scope=__doc__, manufacturing_release=False, physical_fit_qualified=False)
        (output / 'restore-results.json').write_text(json.dumps(proof, indent=2) + '\n')
        print(json.dumps({key: value for key, value in row.items()
                          if key not in ('unresolved_findings', 'next_old_copper_removals')}
                         | dict(removals=len(to_remove), unresolved=len(unresolved))), flush=True)
        if summary['parity'] or unresolved or not to_remove or number == 32:
            break
        next_folder = output / f'round-{number + 1:03d}'
        copy(selected, next_folder)
        path = next_folder / 'esp32-ecu.kicad_pcb'
        text = path.read_text()
        current_blocks = copper_blocks(text)
        assert to_remove <= current_blocks.keys() and not to_remove & priority_copper.keys()
        for begin, end, _ in sorted((current_blocks[uid] for uid in to_remove), reverse=True):
            text = text[:begin] + text[end:]
        path.write_text(text)
        removed.update(to_remove)
        selected = next_folder
    assert sha(old_path) == old_hash and sha(priority_path) == priority_hash


if __name__ == '__main__':
    main()
