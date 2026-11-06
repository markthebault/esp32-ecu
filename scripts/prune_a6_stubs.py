#!/usr/bin/env python3
"""Prune native-reported dangling A6 copper, gating every round with DRC.

Fresh copies only. Every connected schematic pad and all other copper must
remain. Zero DRC does not establish signal, current or physical qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import pcbnew as p
from finish_a6_routes import copper_state, pad_state, native_drc, drc_summary, copy_native
from kicad9_carrier_copy import chunks


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
    source_sha = sha(source / 'esp32-ecu.kicad_pcb')
    out.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).read_bytes()
    (out / 'runner.py').write_bytes(script)
    selected = out / 'baseline'
    copy_native(source, selected)
    drc = native_drc(selected)
    original = p.LoadBoard(str(source / 'esp32-ecu.kicad_pcb'))
    pads, initial_copper = pad_state(original), copper_state(original)
    summary = drc_summary(drc)
    assert not summary['physical'] and not summary['parity'] and summary['unconnected'] == 0
    rounds, removed_all = [], set()
    for index in range(64):
        stubs = [v for v in drc['violations'] if v['type'] in ('track_dangling', 'via_dangling')]
        if not stubs:
            break
        ids = {item['uuid'] for v in stubs for item in v['items']}
        assert ids and ids <= (initial_copper.keys() - removed_all)
        trial = out / ('round-%03d' % (index + 1))
        copy_native(selected, trial)
        path = trial / 'esp32-ecu.kicad_pcb'
        text = path.read_text()
        found = []
        for kind in ('segment', 'arc', 'via'):
            for begin, end, block in reversed(list(chunks(text, kind))):
                matching = [uid for uid in ids if '"' + uid + '"' in block]
                if matching:
                    assert len(matching) == 1
                    found.extend(matching)
                    text = text[:begin] + text[end:]
        assert set(found) == ids and len(found) == len(ids)
        path.write_text(text)
        board = p.LoadBoard(str(path))
        p.ZONE_FILLER(board).Fill(board.Zones())
        assert pad_state(board) == pads
        assert copper_state(board) == {uid: v for uid, v in initial_copper.items()
                                       if uid not in removed_all | ids}
        p.SaveBoard(str(path), board)
        result = native_drc(trial)
        after = drc_summary(result)
        accept = not after['physical'] and not after['parity'] and after['unconnected'] == 0
        row = dict(path=str(path), input_pcb_sha256=sha(selected / 'esp32-ecu.kicad_pcb'),
                   output_pcb_sha256=sha(path), removed_geometry={uid: initial_copper[uid]
                   for uid in sorted(ids)}, accepted=accept, result=after)
        rounds.append(row)
        if accept:
            removed_all.update(ids)
            selected, drc, summary = trial, result, after
        proof = dict(source=str(source), source_pcb_sha256=source_sha,
            script_sha256=hashlib.sha256(script).hexdigest(), selected=str(selected),
            removed_count=len(removed_all), rounds=rounds, current=summary,
            all_original_pads_and_other_tracks_retained=True,
            scope=__doc__, manufacturing_release=False)
        (out / 'results.json').write_text(json.dumps(proof, indent=2) + '\n')
        print(json.dumps(dict(round=index + 1, removed=len(ids), accepted=accept, result=after)), flush=True)
        if not accept:
            break
    assert sha(source / 'esp32-ecu.kicad_pcb') == source_sha
    print('Selected', selected, summary, flush=True)


if __name__ == '__main__':
    main()
