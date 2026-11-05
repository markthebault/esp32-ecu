#!/usr/bin/env python3
"""Remove only the six declared RF-crossing segments on a fresh A6 copy.

This deliberately opens two signal nets, which must be rerouted and checked.
The source copy and every other pad/track remain unchanged.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import pcbnew as p
from finish_a6_routes import copper_state, pad_state
from kicad9_carrier_copy import chunks

EXPECTED = {'25292cac-079c-456f-bfe8-7f9f1e5f77b2',
            'ccc0bfea-d020-4849-935b-0660589d08ba',
            '25f92cfb-8503-48de-9a6f-63cfaec4c7b9',
            '3ff517ff-aa87-4c2f-b64e-4ab6e025a74a',
            '9680b5bb-8845-478e-97f7-2c6a2992efb7',
            'de5fb6ff-75b4-4870-9019-085826d2cb05'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    assert source != out and source not in out.parents
    assert json.loads((source / 'net_contract.json').read_text())['revision'] == 'A6-FLEX-RGB-HOLD'
    source_hash = sha(source / 'esp32-ecu.kicad_pcb')
    drc = json.loads((source / 'rf-drc.json').read_text())
    conflicts = [v for v in drc['violations'] if v['type'] == 'items_not_allowed']
    ids = {i['uuid'] for v in conflicts for i in v['items']}
    assert len(conflicts) == 6 and ids == EXPECTED
    board = p.LoadBoard(str(source / 'esp32-ecu.kicad_pcb'))
    pads, copper = pad_state(board), copper_state(board)
    assert {copper[uid][0] for uid in ids} == {'WDI', 'INJ2_CMD'}
    shutil.copytree(source, out, ignore=shutil.ignore_patterns(
        '*drc.*', '*.kicad_prl', '*.lck', '*~'))
    path = out / 'esp32-ecu.kicad_pcb'
    text = path.read_text()
    removed = []
    for start, end, block in reversed(list(chunks(text, 'segment'))):
        matching = [uid for uid in ids if '"' + uid + '"' in block]
        if matching:
            assert len(matching) == 1
            removed.extend(matching)
            text = text[:start] + text[end:]
    assert set(removed) == ids and len(removed) == 6
    path.write_text(text)
    board = p.LoadBoard(str(path))
    assert pad_state(board) == pads
    assert copper_state(board) == {uid: value for uid, value in copper.items() if uid not in ids}
    p.ZONE_FILLER(board).Fill(board.Zones())
    p.SaveBoard(str(path), board)
    with (out / 'rf-ripup-drc.log').open('xb') as log:
        proc = subprocess.run(['kicad-cli', 'pcb', 'drc', '--exit-code-violations',
            '--severity-all', '--format', 'json', '--output', str(out / 'rf-ripup-drc.json'),
            str(path)], stdout=log, stderr=subprocess.STDOUT)
    assert proc.returncode in (0, 5)
    result = json.loads((out / 'rf-ripup-drc.json').read_text())
    proof = dict(source=str(source), source_pcb_sha256=source_hash,
        source_drc_sha256=sha(source / 'rf-drc.json'), script_sha256=sha(Path(__file__)),
        removed_segment_geometry={uid: copper[uid] for uid in sorted(ids)},
        original_pads_and_other_tracks_retained=True, output_pcb_sha256=sha(path),
        unconnected=len(result['unconnected_items']),
        violations=dict(Counter(v['type'] for v in result['violations'])),
        parity=len(result['schematic_parity']), scope=__doc__, manufacturing_release=False)
    (out / 'rf-ripup.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert sha(source / 'esp32-ecu.kicad_pcb') == source_hash
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    main()
