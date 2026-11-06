#!/usr/bin/env python3
"""Route only new A5 links, retaining the archived carrier copper byte geometry.

The router's rounded replacement of protected copper is discarded. Only new
unlocked tracks/vias are copied back into the original native9 A5 board. Native
DRC/parity and independent geometry review remain mandatory. No fab export.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pcbnew as pcb
from kicad9_carrier_copy import chunks

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'hardware/a5-idle-interface/esp32-ecu.kicad_pcb'
NEW_NETS = {'IDLE_CMD', 'RUN_5V', '+5V', 'GND'}


def geometry(t):
    if isinstance(t, pcb.PCB_VIA):
        return ['via', t.GetNetname(), t.GetPosition().x, t.GetPosition().y,
                t.GetWidth(pcb.F_Cu), t.GetDrillValue(), t.TopLayer(), t.BottomLayer()]
    assert not isinstance(t, pcb.PCB_ARC)
    return ['track', t.GetNetname(), t.GetLayer(), t.GetStart().x, t.GetStart().y,
            t.GetEnd().x, t.GetEnd().y, t.GetWidth()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--import-session', type=Path)
    args = parser.parse_args()
    assert bool(args.prepare) != bool(args.import_session)
    if args.prepare:
        folder = args.prepare.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        before = BOARD.read_bytes()
        board = pcb.LoadBoard(str(BOARD))
        assert len(board.GetTracks()) == 2973 and all(t.IsLocked() for t in board.GetTracks())
        dsn = folder / 'carrier.dsn'
        assert pcb.ExportSpecctraDSN(board, str(dsn))
        text = dsn.read_text()
        # Reserve the full provisional inward antenna rectangle for NEW routes.
        # Old protected copper is retained and its RF qualification remains open.
        start, _, _ = next(chunks(text, 'via'))
        keepouts = ''.join(f'(keepout "A5-new-route-antenna" (polygon {layer} 0 '
                           '14000 -29000 44000 -29000 44000 -40000 14000 -40000 14000 -29000))\n'
                           for layer in ('F.Cu', 'In1.Cu', 'In2.Cu', 'In3.Cu', 'In4.Cu', 'B.Cu'))
        text = text[:start] + keepouts + text[start:]
        start, end, block = next(chunks(text, 'class'))
        assert len(list(chunks(text, 'class'))) == 1
        # Use the exported via rule but split routing widths for the new links.
        import re
        via = re.search(r'\(use_via ("[^"]+")', block)[1]
        selected = ('(class IdleNew IDLE_CMD RUN_5V '
                    f'(circuit (use_via {via})) (rule (width 300) (clearance 200)))\n'
                    '(class IdlePowerNew "+5V" GND '
                    f'(circuit (use_via {via})) (rule (width 400) (clearance 200)))\n')
        rest = sorted(n.GetNetname() for n in board.GetNetsByNetcode().values()
                      if n.GetNetname() and n.GetNetname() not in NEW_NETS)
        selected += '(class Existing ' + ' '.join(json.dumps(n) for n in rest) + \
                    f' (circuit (use_via {via})) (rule (width 200) (clearance 200)))'
        text = text[:start] + selected + text[end:]
        dsn.write_text(text)
        assert '(type protect)' in text or '(type fix)' in text
        (folder / 'before.kicad_pcb').write_bytes(before)
        (folder / 'routing-input.json').write_text(json.dumps(dict(
            board_sha256=hashlib.sha256(before).hexdigest(),
            dsn_sha256=hashlib.sha256(dsn.read_bytes()).hexdigest(),
            protected_objects=[geometry(t) for t in board.GetTracks()],
            new_route_antenna_keepout_mm=[14, 29, 44, 40],
            qualification='Incremental routing input. No manufacturing or physical acceptance.'), indent=2) + '\n')
        print('Exported protected carrier; run local router with analytics disabled')
    else:
        session = args.import_session.resolve()
        folder = session.parent
        record = json.loads((folder / 'routing-input.json').read_text())
        assert hashlib.sha256(BOARD.read_bytes()).hexdigest() == record['board_sha256'], 'A5 changed since export'
        original = pcb.LoadBoard(str(BOARD))
        before = sorted(geometry(t) for t in original.GetTracks())
        assert before == sorted(record['protected_objects'])
        routed = pcb.LoadBoard(str(BOARD))
        assert pcb.ImportSpecctraSES(routed, str(session))
        locked = [t for t in routed.GetTracks() if t.IsLocked()]
        added = [t for t in routed.GetTracks() if not t.IsLocked()]
        assert len(locked) == len(before), 'Router did not preserve protected object count'
        assert added and all(t.GetNetname() in NEW_NETS for t in added)
        copied = []
        for track in added:
            new = track.Duplicate()
            new.SetNet(original.FindNet(track.GetNetname()))
            original.Add(new)
            copied.append(geometry(new))
        assert sorted(geometry(t) for t in original.GetTracks() if t.IsLocked()) == before
        pcb.ZONE_FILLER(original).Fill(original.Zones())
        pcb.SaveBoard(str(BOARD), original)
        record.update(session_sha256=hashlib.sha256(session.read_bytes()).hexdigest(),
                      routed_board_sha256=hashlib.sha256(BOARD.read_bytes()).hexdigest(),
                      added_objects=copied, original_geometry_preserved=True)
        (folder / 'routing-result.json').write_text(json.dumps(record, indent=2) + '\n')
        path = BOARD.parent / 'source-provenance.json'
        provenance = json.loads(path.read_text())
        provenance.update(new_connections_unrouted=False, original_copper_geometry_preserved=True,
                          new_track_via_count=len(added), incremental_router_result=str((folder/'routing-result.json').relative_to(ROOT)))
        path.write_text(json.dumps(provenance, indent=2) + '\n')
        path = BOARD.parent / 'net_contract.json'
        contract = json.loads(path.read_text())
        contract['status'] = 'ROUTED_INTERFACE_HOLD_NOT_FOR_FABRICATION'
        path.write_text(json.dumps(contract, indent=2) + '\n')
        print(f'Appended {len(added)} new track/via objects; retained all {len(before)} original objects')


if __name__ == '__main__':
    main()
