#!/usr/bin/env python3
"""Seed the separate IAC-DRAFT2 power loops, export/import a local router session.

Never routes an archived carrier. Freerouting must run with analytics disabled.
Native all-severity DRC/parity and independent review are separate acceptance.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import pcbnew as pcb
from kicad9_carrier_copy import chunks

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'hardware/idle-isolated/isolated.kicad_pcb'


def seed(board):
    if list(board.GetTracks()):
        raise ValueError('Power seed requires a fresh generated board; existing copper is retained')
    nets = {n.GetNetname(): n for n in board.GetNetsByNetcode().values()}
    paths = [
        ('ACT_12V', pcb.B_Cu, [(90, 23), (90, 30), (98.5, 38.5), (98.5, 53), (90, 53), (90, 57)]),
        ('ACT_12V', pcb.F_Cu, [(70, 15), (73, 18), (85, 18), (90, 23)]),
        ('IAC_LS', pcb.F_Cu, [(85.24, 15), (89, 15), (93.96, 19.96), (93.96, 23),
                             (93.96, 29.3), (92.54, 30.72), (92.54, 39)]),
        ('ACT_GND', pcb.F_Cu, [(95.08, 39), (95.08, 57)]),
    ]
    for net, layer, points in paths:
        for start, end in zip(points, points[1:]):
            track = pcb.PCB_TRACK(board)
            track.SetStart(pcb.VECTOR2I(*(pcb.FromMM(v) for v in start)))
            track.SetEnd(pcb.VECTOR2I(*(pcb.FromMM(v) for v in end)))
            track.SetWidth(pcb.FromMM(2))
            track.SetLayer(layer)
            track.SetNet(nets[net])
            track.SetLocked(True)
            board.Add(track)
    return paths


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=True)
    board = pcb.LoadBoard(str(BOARD))
    paths = seed(board)
    pcb.SaveBoard(str(BOARD), board)
    dsn = folder / 'isolated.dsn'
    assert pcb.ExportSpecctraDSN(board, str(dsn))
    text = dsn.read_text()
    via = re.search(r'\(via "([^"]+)"', text)[1]
    classes = list(chunks(text, 'class'))
    assert len(classes) == 1
    start, end, _ = classes[0]
    nets = [n.GetNetname() for n in board.GetNetsByNetcode().values() if n.GetNetname()]
    groups = [('ActuatorSupply', ['ACT_12V'], 800), ('ActuatorReturn', ['ACT_GND'], 600),
              ('LogicPower', ['ACT_5V2', 'CARRIER_5V', 'CARRIER_GND'], 500)]
    used = {n for _, members, _ in groups for n in members}
    groups.append(('Signals', [n for n in nets if n not in used], 350))
    replacement = '\n'.join('(class ' + name + ' ' + ' '.join(json.dumps(n) for n in members) +
                            f' (circuit (use_via "{via}")) (rule (width {width}) (clearance 300)))'
                            for name, members, width in groups)
    text = text[:start] + replacement + text[end:]
    # The fixed power loops must not be ripped up into thin control routes.
    assert '(type protect)' in text or '(type fix)' in text
    dsn.write_text(text)
    (folder / 'routing-input.json').write_text(json.dumps(dict(
        board_sha256=hashlib.sha256(BOARD.read_bytes()).hexdigest(),
        dsn_sha256=hashlib.sha256(dsn.read_bytes()).hexdigest(),
        power_seed_width_mm=2, power_paths=[dict(net=n, layer=pcb.LayerName(l), points=p) for n, l, p in paths],
        routing_clearance_mm=.3, qualification='Routing input only, not physical current capacity or manufacturing acceptance'), indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--import-session', type=Path)
    parser.add_argument('--clean-dangling', type=Path)
    args = parser.parse_args()
    if sum(bool(x) for x in (args.prepare, args.import_session, args.clean_dangling)) != 1:
        parser.error('Choose exactly one operation')
    if args.prepare:
        prepare(args.prepare.resolve())
    elif args.import_session:
        board = pcb.LoadBoard(str(BOARD))
        assert pcb.ImportSpecctraSES(board, str(args.import_session.resolve()))
        pcb.SaveBoard(str(BOARD), board)
        print('Imported local router copper; native DRC/parity and review still required')
    else:
        report = json.loads(args.clean_dangling.read_text())
        assert all(x['type'] == 'track_dangling' for x in report['violations'])
        assert not report['unconnected_items'] and not report['schematic_parity']
        board = pcb.LoadBoard(str(BOARD))
        before = hashlib.sha256(BOARD.read_bytes()).hexdigest()
        uuids = {i['uuid'] for x in report['violations'] for i in x['items']}
        removed = []
        for track in list(board.GetTracks()):
            if str(track.m_Uuid.AsString()) in uuids:
                assert not track.IsLocked() and track.GetWidth() < pcb.FromMM(2)
                removed.append(dict(uuid=str(track.m_Uuid.AsString()), net=track.GetNetname(),
                                    width_mm=track.GetWidth()/1e6))
                board.Remove(track)
        assert len(removed) == len(uuids)
        pcb.SaveBoard(str(BOARD), board)
        args.clean_dangling.with_name('dangling-cleanup.json').write_text(json.dumps(dict(
            before_sha256=before, after_sha256=hashlib.sha256(BOARD.read_bytes()).hexdigest(),
            removed=removed, qualification='Only unlocked sub2mm dangling stubs removed. Rerun native DRC/connectivity.'), indent=2) + '\n')


if __name__ == '__main__':
    main()
