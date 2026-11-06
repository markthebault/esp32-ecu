#!/usr/bin/env python3
"""Make both A6 antenna rule areas exclude copper on all six copper layers.

Fresh native copy only. Retains every pad and track; any existing crossing must
be repaired separately. Copper exclusion does not establish RF performance.
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    assert source != out and source not in out.parents
    contract = json.loads((source / 'net_contract.json').read_text())
    assert contract['revision'] == 'A6-FLEX-RGB-HOLD'
    before_hash = sha(source / 'esp32-ecu.kicad_pcb')
    shutil.copytree(source, out, ignore=shutil.ignore_patterns(
        '*drc.*', '*.kicad_prl', '*.lck', '*~'))
    path = out / 'esp32-ecu.kicad_pcb'
    board = p.LoadBoard(str(path))
    assert board.GetCopperLayerCount() == 6
    original_pads, original_copper = pad_state(board), copper_state(board)
    copper_layers = (p.F_Cu, p.In1_Cu, p.In2_Cu, p.In3_Cu, p.In4_Cu, p.B_Cu)
    mask = p.LSET()
    for layer in copper_layers:
        mask.AddLayer(layer)
    zones = [z for z in board.Zones() if z.GetIsRuleArea()]
    assert len(zones) == 2
    changes = []
    for zone in zones:
        assert all((zone.GetDoNotAllowTracks(), zone.GetDoNotAllowVias(),
                    zone.GetDoNotAllowPads(), zone.GetDoNotAllowCopperPour()))
        outline = zone.Outline()
        assert outline.OutlineCount() == 1 and outline.Outline(0).PointCount() == 4
        vertices = [(outline.Outline(0).CPoint(i).x / 1e6,
                     outline.Outline(0).CPoint(i).y / 1e6) for i in range(4)]
        assert vertices in [[(16., 29.), (43., 29.), (43., 36.), (16., 36.)],
                            [(20., 32.), (39., 32.), (39., 40.), (20., 40.)]]
        before = [board.GetLayerName(l) for l in copper_layers if zone.IsOnLayer(l)]
        zone.SetLayerSet(mask)
        assert all(zone.IsOnLayer(l) for l in copper_layers)
        changes.append(dict(uuid=zone.m_Uuid.AsString(), vertices_mm=vertices,
                            before_layers=before,
                            after_layers=[board.GetLayerName(l) for l in copper_layers]))
    p.ZONE_FILLER(board).Fill(board.Zones())
    assert pad_state(board) == original_pads and copper_state(board) == original_copper
    p.SaveBoard(str(path), board)
    with (out / 'rf-drc.log').open('xb') as log:
        proc = subprocess.run(['kicad-cli', 'pcb', 'drc', '--exit-code-violations',
            '--severity-all', '--format', 'json', '--output', str(out / 'rf-drc.json'),
            str(path)], stdout=log, stderr=subprocess.STDOUT)
    assert proc.returncode in (0, 5)
    drc = json.loads((out / 'rf-drc.json').read_text())
    proof = dict(source=str(source), source_pcb_sha256=before_hash,
        output_pcb_sha256=sha(path), script_sha256=sha(Path(__file__)),
        geometry_helper_sha256=sha(Path(__file__).with_name('finish_a6_routes.py')),
        rule_area_changes=changes, original_pads_and_tracks_retained=True,
        ground_zone_fills_refreshed=True, native_exit=proc.returncode,
        violations=dict(Counter(v['type'] for v in drc['violations'])),
        unconnected=len(drc['unconnected_items']), parity=len(drc['schematic_parity']),
        scope=__doc__, manufacturing_release=False, RF_qualified=False)
    (out / 'rf-update.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert sha(source / 'esp32-ecu.kicad_pcb') == before_hash
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    main()
