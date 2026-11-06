#!/usr/bin/env python3
"""Incrementally route a new boost copy, preserving every retained copper item.

The source A6/IAC projects are refused. The external router's rounded protected
geometry is discarded; only new unlocked items are imported into the exact
input copy. Native checks and independent electrical review remain required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import pcbnew as pcb
from kicad9_carrier_copy import chunks
from route_a5_idle_interface import geometry

ROOT = Path(__file__).resolve().parents[1]
CARRIER_NEW_NETS = {'BOOST_CMD', 'IDLE_CMD', 'RUN_5V', '+5V', 'GND'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pads(board):
    return sorted((fp.GetReference(), pad.GetNumber(), pad.GetNetname(), pad.GetPosition().x,
                   pad.GetPosition().y, pad.GetSize().x, pad.GetSize().y, pad.GetDrillSize().x, pad.GetDrillSize().y)
                  for fp in board.GetFootprints() for pad in fp.Pads() if pad.GetNumber())


def prepare(path, output):
    output.mkdir(parents=True, exist_ok=False)
    board = pcb.LoadBoard(str(path))
    assert all(track.IsLocked() for track in board.GetTracks()), 'Expected a new generated copy with protected retained copper'
    shutil.copyfile(path, output/'before.kicad_pcb')
    dsn = output/'boost.dsn'
    assert pcb.ExportSpecctraDSN(board, str(dsn))
    text = dsn.read_text()
    classes = list(chunks(text, 'class'))
    assert classes
    start, _, block = classes[0]
    via = re.search(r'\(use_via ("[^"]+")', block)[1]
    names = {net.GetNetname() for net in board.GetNetsByNetcode().values() if net.GetNetname()}
    carrier = path.name == 'esp32-ecu.kicad_pcb'
    if carrier:
        groups = [('NewGround', names & {'GND'}, 1000),
                  ('NewSupply', names & {'+5V'}, 500),
                  ('NewLogic', names & {'IDLE_CMD', 'BOOST_CMD', 'RUN_5V'}, 300)]
        clearance = 200
    else:
        groups = [('CoilPositive', names & {'ACT_12V', 'BOOST_LS'}, 1000),
                  ('CoilReturn', names & {'ACT_GND'}, 800),
                  ('LogicPower', names & {'LOGIC_GND', 'ACT_5V2', 'CARRIER_5V', 'LED_5V', 'CARRIER_GND'}, 500)]
        clearance = 300
    used = {net for _, members, _ in groups for net in members}
    groups.append(('OtherLogic', names-used, 250 if carrier else 350))
    replacement = '\n'.join('(class ' + name + ' ' + ' '.join(json.dumps(net) for net in sorted(members)) +
        f' (circuit (use_via {via})) (rule (width {width}) (clearance {clearance})))'
        for name, members, width in groups if members)
    for a, b, _ in reversed(classes):
        text = text[:a] + text[b:]
    text = text[:start] + replacement + text[start:]
    if carrier:
        start, _, _ = next(chunks(text, 'via'))
        keepouts = ''.join(f'(keepout "A7-new-route-antenna" (polygon {layer} 0 '
                          '14000 -29000 44000 -29000 44000 -40000 14000 -40000 14000 -29000))\n'
                          for layer in ('F.Cu', 'In1.Cu', 'In2.Cu', 'In3.Cu', 'In4.Cu', 'B.Cu'))
        text = text[:start] + keepouts + text[start:]
    assert '(type protect)' in text or '(type fix)' in text
    dsn.write_text(text)
    report = dict(input_board_sha256=sha(path), dsn_sha256=sha(dsn), protected_copper=[geometry(t) for t in board.GetTracks()],
                  pads=pads(board), route_classes=[dict(name=name, nets=sorted(nets), width_um=width) for name, nets, width in groups],
                  clearance_um=clearance, physical_outputs_enabled=False, manufacturing_release=False)
    helpers = [Path(__file__).resolve(), Path(__file__).with_name('kicad9_carrier_copy.py'), Path(__file__).with_name('route_a5_idle_interface.py')]
    report['tool_source_sha256'] = {str(p.relative_to(ROOT)): sha(p) for p in helpers}
    report['kicad_version'] = pcb.Version()
    for p in helpers:
        target = output/'tool-source'/p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
        assert sha(target) == report['tool_source_sha256'][str(p.relative_to(ROOT))]
    (output/'routing-input.json').write_text(json.dumps(report, indent=2)+'\n')


def import_session(path, session):
    source = json.loads((session.parent/'routing-input.json').read_text())
    assert sha(path) == source['input_board_sha256'], 'Input changed since export'
    original = pcb.LoadBoard(str(path))
    retained = sorted(geometry(track) for track in original.GetTracks())
    assert retained == sorted(source['protected_copper'])
    assert [list(row) for row in pads(original)] == source['pads']
    routed = pcb.LoadBoard(str(path))
    assert pcb.ImportSpecctraSES(routed, str(session))
    assert sum(track.IsLocked() for track in routed.GetTracks()) == len(retained), 'Protected item count changed'
    additions = []
    excluded = []
    for track in routed.GetTracks():
        if track.IsLocked(): continue
        if path.name == 'esp32-ecu.kicad_pcb' and track.GetNetname() not in CARRIER_NEW_NETS:
            excluded.append(geometry(track))
            continue
        new = track.Duplicate()
        new.SetNet(original.FindNet(track.GetNetname()))
        original.Add(new)
        additions.append(geometry(new))
    assert additions
    assert sorted(geometry(track) for track in original.GetTracks() if track.IsLocked()) == retained
    assert [list(row) for row in pads(original)] == source['pads'], 'Original exact pad geometry changed'
    pcb.ZONE_FILLER(original).Fill(original.Zones())
    pcb.SaveBoard(str(path), original)
    source.update(session_sha256=sha(session), output_board_sha256=sha(path),
                  added_copper=additions, retained_copper_exact=True, exact_pads_preserved=True,
                  excluded_router_additions=excluded, zone_fills_recomputed=True,
                  import_tool_sha256=sha(__file__))
    shutil.copyfile(__file__, session.parent/'import-tool.py')
    with (session.parent/'routing-result.json').open('x') as stream: stream.write(json.dumps(source, indent=2)+'\n')
    contract_path = path.parent/'net_contract.json'
    contract = json.loads(contract_path.read_text())
    contract['status'] = 'ROUTED_DRAFT_AWAITING_NATIVE_CHECKS_NOT_FOR_FABRICATION'
    contract_path.write_text(json.dumps(contract, indent=2)+'\n')


def prune_dangling(path, report_path):
    report = json.loads(report_path.read_text())
    rows = report['violations']
    allowed = {'track_dangling', 'via_dangling'}
    assert rows and all(row['type'] in allowed and len(row['items']) == 1 for row in rows), 'Only a pure native dangling-copper report is accepted'
    folder = path.parent/'copper-pruning'/sha(report_path)[:16]
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(path, folder/'before.kicad_pcb')
    # A supplied report is only a hint. Recheck the actual current board before
    # deleting anything, so an old report cannot remove a newly valid route.
    fresh = folder/'current-drc.json'
    command = ['kicad-cli', 'pcb', 'drc', '--severity-all', '--format', 'json', '--all-track-errors',
               '--schematic-parity', '--exit-code-violations', '--output', str(fresh), str(path)]
    checked = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (folder/'native.log').write_text(checked.stdout)
    assert checked.returncode in (0, 5) and fresh.exists()
    actual = json.loads(fresh.read_text())['violations']
    assert all(row['type'] in allowed and len(row['items']) == 1 for row in actual)
    assert {row['items'][0]['uuid'] for row in actual} == {row['items'][0]['uuid'] for row in rows}, 'Native report is stale'
    assert sha(path) == sha(folder/'before.kicad_pcb'), 'Board changed during native recheck'
    board = pcb.LoadBoard(str(path))
    objects = {track.m_Uuid.AsString(): track for track in board.GetTracks()}
    provenance_path = path.parent/'source-provenance.json'
    provenance = json.loads(provenance_path.read_text())
    shutil.copyfile(provenance_path, folder/'before-provenance.json')
    shutil.copyfile(__file__, folder/'tool.py')
    removed = []
    detached = []
    for row in rows:
        uid = row['items'][0]['uuid']
        assert uid in objects
        assert isinstance(objects[uid], pcb.PCB_VIA) == (row['type'] == 'via_dangling')
        track = objects[uid]
        assert geometry(track) in provenance['retained_copper'] or not track.IsLocked(), 'Unrecognized protected geometry'
        removed.append(dict(uuid=uid, geometry=geometry(track), reason='Native unconnected stub after intentional connector/pad replacement'))
        board.RemoveNative(track); detached.append(track)
    pcb.ZONE_FILLER(board).Fill(board.Zones())
    pcb.SaveBoard(str(path), board)
    (folder/'audit.json').write_text(json.dumps(dict(input_board_sha256=sha(folder/'before.kicad_pcb'),
        native_report_sha256=sha(report_path), fresh_native_report_sha256=sha(fresh),
        tool_sha256=sha(folder/'tool.py'),
        output_board_sha256=sha(path), removed=removed,
        physical_outputs_enabled=False, manufacturing_release=False), indent=2)+'\n')
    omitted = [row['geometry'] for row in removed if row['geometry'] in provenance['retained_copper']]
    new_stubs = [row for row in removed if row['geometry'] not in provenance['retained_copper']]
    provenance['retained_copper'] = [row for row in provenance['retained_copper'] if row not in omitted]
    provenance.setdefault('omitted_parent_copper', []).extend(omitted)
    provenance.setdefault('pruned_added_copper', []).extend(new_stubs)
    provenance.setdefault('native_stub_pruning', []).append(dict(audit=str(folder/'audit.json'), sha256=sha(folder/'audit.json')))
    provenance_path.write_text(json.dumps(provenance, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--import-session', type=Path)
    parser.add_argument('--prune-dangling', type=Path)
    args = parser.parse_args()
    assert sum(bool(option) for option in (args.prepare, args.import_session, args.prune_dangling)) == 1
    path = args.board.resolve()
    assert path.parent not in {(ROOT/'hardware/a6-flex-rgb').resolve(), (ROOT/'hardware/idle-isolated').resolve()}
    contract = json.loads((path.parent/'net_contract.json').read_text())
    assert contract['revision'] in ('A7-BOOST-INTERFACE-HOLD', 'BOOST-DRAFT1')
    if args.prepare: prepare(path, args.prepare.resolve())
    elif args.import_session: import_session(path, args.import_session.resolve())
    else: prune_dangling(path, args.prune_dangling.resolve())
    print('Boost routing step completed; native/circuit/physical acceptance remains separate.')


if __name__ == '__main__':
    main()
