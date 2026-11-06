#!/usr/bin/env python3
"""Audit declared A6 copper geometry policy; no current or thermal rating.

DSN width targets alone are not native DRC minimums. The three literal INJ1
neck segments below are a declared exception awaiting load/thermal acceptance.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import pcbnew as p

POWER = {'GND', 'VBAT_FUSED', 'VIN_PROT', 'VIN_FILTERED'} | {
    'INJ%d_LS' % i for i in range(1, 5)}
SUPPLY = {'+5V', '+3V3', 'SENSOR_5V', 'FLEX_12V', 'MAIN_LS', 'PUMP_LS', 'FAN_LS'}
NECKS = {
    '0b7ea104-b013-488f-93e3-d6a76c61494c': ((113051500, 10900000), (113051500, 10944300)),
    '0f7d20d6-419f-4559-84dd-fcca2c17c76a': ((103800000, 10900000), (103800000, 10944300)),
    '885ffd1f-71be-4c13-8ade-664dadba50ad': ((113051500, 10900000), (103800000, 10900000)),
}


def policy(net):
    return ('Power', 1000000) if net in POWER else (
        ('Supply', 500000) if net in SUPPLY else ('Logic', 250000))


def audit(board):
    layers = [l for l in board.GetEnabledLayers().Seq() if p.IsCopperLayer(l)]
    assert len(layers) == 6
    findings, seen_necks, counts = [], set(), defaultdict(Counter)
    traces, vias = [], []
    for t in board.GetTracks():
        uid = t.m_Uuid.AsString()
        if isinstance(t, p.PCB_VIA):
            widths = {board.GetLayerName(l): t.GetWidth(l) for l in layers if t.IsOnLayer(l)}
            row = dict(uuid=uid, net=t.GetNetname(), diameter_nm_by_layer=widths,
                       drill_nm=t.GetDrillValue(), top_layer=board.GetLayerName(t.TopLayer()),
                       bottom_layer=board.GetLayerName(t.BottomLayer()), via_type=t.GetViaType())
            vias.append(row)
            if (set(widths) != {board.GetLayerName(l) for l in layers}
                    or min(widths.values()) < 600000 or t.GetDrillValue() < 300000
                    or any((diameter - t.GetDrillValue()) / 2 < 100000 for diameter in widths.values())
                    or t.GetViaType() != p.VIATYPE_THROUGH
                    or t.TopLayer() != p.F_Cu or t.BottomLayer() != p.B_Cu):
                findings.append(dict(uuid=uid, reason='Via geometry/span differs from declared through-via policy'))
            continue
        assert t.GetClass() == 'PCB_TRACK', t.GetClass()
        group, minimum = policy(t.GetNetname())
        width = t.GetWidth()
        counts[group][str(width / 1e6)] += 1
        a, b = t.GetStart(), t.GetEnd()
        row = dict(uuid=uid, net=t.GetNetname(), group=group, layer=board.GetLayerName(t.GetLayer()),
                   width_nm=width, start_nm=[a.x, a.y], end_nm=[b.x, b.y],
                   centerline_length_mm=t.GetLength() / 1e6)
        traces.append(row)
        if uid in NECKS:
            seen_necks.add(uid)
            if (t.GetNetname() != 'INJ1_LS' or width != 800000 or t.GetLayer() != p.In3_Cu
                    or ((a.x, a.y), (b.x, b.y)) != NECKS[uid]):
                findings.append(dict(uuid=uid, reason='Declared INJ1 neck geometry changed'))
        elif width < minimum:
            findings.append(dict(uuid=uid, reason='Track narrower than declared geometry policy',
                                 minimum_nm=minimum, actual_nm=width, net=t.GetNetname()))
    if seen_necks != set(NECKS):
        findings.append(dict(reason='Declared INJ1 neck objects missing', missing=sorted(set(NECKS) - seen_necks)))
    return dict(passed=not findings, findings=findings,
        track_counts_by_group_width_mm=dict(counts), track_count=len(traces), via_count=len(vias),
        literal_neck_exceptions=[row for row in traces if row['uuid'] in NECKS],
        tracks=traces, vias=vias, nominal_minimum_widths_mm=dict(Power=1, Supply=.5, Logic=.25),
        scope=__doc__, current_thermal_I2t_qualified=False, manufacturing_release=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(p.LoadBoard(str(args.board)))
    result.update(board=str(args.board.resolve()), board_sha256=hashlib.sha256(args.board.read_bytes()).hexdigest(),
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({k: result[k] for k in ('passed', 'findings', 'track_counts_by_group_width_mm', 'track_count', 'via_count')}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
