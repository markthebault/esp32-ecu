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
    local = [
        ('ACT_5V2', .5, pcb.B_Cu, [(44, 23.31), (41.62, 22)]),
        ('LOGIC_GND', .5, pcb.B_Cu, [(44, 28.31), (41.62, 29.62)]),
        ('ACT_5V2', .5, pcb.B_Cu, [(44, 46.31), (41.62, 45)]),
        ('LOGIC_GND', .5, pcb.B_Cu, [(44, 51.31), (41.62, 52.62)]),
        ('ACT_5V2', .5, pcb.B_Cu, [(58, 28), (58.62, 30)]),
        ('LOGIC_GND', .5, pcb.B_Cu, [(53, 28), (53, 43.24), (51, 45.24)]),
        ('ACT_5V2', .5, pcb.B_Cu, [(83.31, 43.08), (84.62, 43.08)]),
        ('LOGIC_GND', .5, pcb.B_Cu, [(78.31, 43.08), (77, 43.08)]),
        ('ACT_5V2', .5, pcb.B_Cu, [(83.31, 48), (81.5, 46.19), (81.5, 44.89), (83.31, 43.08)]),
        ('LOGIC_GND', .5, pcb.B_Cu, [(78.31, 48), (78.31, 43.08)]),
        ('ACT_5V2', .5, pcb.B_Cu, [(69.31, 24), (70.54, 21)]),
        ('LOGIC_GND', .5, pcb.B_Cu, [(74.31, 24), (73.08, 21)]),
        ('LOGIC_GND', .3, pcb.B_Cu, [(77, 43.08), (78.27, 41.81), (96.88, 41.81), (96.88, 40)]),
        ('LOGIC_GND', .3, pcb.F_Cu, [(96.88, 40), (96.88, 39)]),
        ('DRIVE', .6, pcb.F_Cu, [(84.62, 40.54), (88.5, 43.5)]),
        ('GATE', .6, pcb.F_Cu, [(91.04, 43.5), (90, 42.46), (90, 39)]),
        ('GATE', .35, pcb.F_Cu, [(87, 49), (87, 47), (90.04, 43.96), (91.04, 43.5)]),
        ('ACT_GND', .3, pcb.B_Cu, [(89.54, 49), (90.5, 49.96), (93, 49.96), (93, 43)]),
        ('ACT_GND', .3, pcb.F_Cu, [(93, 43), (93, 41.08), (95.08, 39)]),
    ]
    for net, width, layer, points in local:
        for start, end in zip(points, points[1:]):
            track = pcb.PCB_TRACK(board)
            track.SetStart(pcb.VECTOR2I(*(pcb.FromMM(v) for v in start)))
            track.SetEnd(pcb.VECTOR2I(*(pcb.FromMM(v) for v in end)))
            track.SetWidth(pcb.FromMM(width))
            track.SetLayer(layer)
            track.SetNet(nets[net])
            track.SetLocked(True)
            board.Add(track)
    for net, xy, diameter, drill in [('LOGIC_GND', (96.88, 40), .6, .3), ('ACT_GND', (93, 43), .7, .35)]:
        via = pcb.PCB_VIA(board)
        via.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(v) for v in xy)))
        via.SetWidth(pcb.FromMM(diameter))
        via.SetDrill(pcb.FromMM(drill))
        via.SetViaType(pcb.VIATYPE_THROUGH)
        via.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
        via.SetNet(nets[net])
        via.SetLocked(True)
        board.Add(via)
    return [dict(net=n, layer=pcb.LayerName(l), width_mm=2, points=p) for n, l, p in paths] + [
        dict(net=n, layer=pcb.LayerName(l), width_mm=w, points=p) for n, w, l, p in local]


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
              ('LogicPower', ['ACT_5V2', 'LOGIC_GND', 'CARRIER_5V', 'CARRIER_GND'], 500)]
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
        power_seed_width_mm=2, fixed_seed_paths=paths,
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
        path = BOARD.parent / 'net_contract.json'
        contract = json.loads(path.read_text())
        contract['status'] = 'ROUTED_DESIGN_HOLD_NOT_FOR_FABRICATION'
        path.write_text(json.dumps(contract, indent=2) + '\n')
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
