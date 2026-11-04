#!/usr/bin/env python3
"""Create a separate A5 carrier copy with a permanent GPIO3 bias and idle header.

The archived A3/A4 and their manufacturing records are never modified. The
N16R8 geometry/eFuse/RF holds remain. Run with Linux KiCad9 Python.
"""
import argparse
import csv
import hashlib
import json
import math
import re
import shutil
from dataclasses import fields
from pathlib import Path
import pcbnew as pcb
import build_hardware as builder
from design import Part
from kicad9_carrier_copy import board_copy, chunks, footprint_copy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'hardware/a4-n16r8'
OUT = ROOT / 'hardware/a5-idle-interface'


def box(fp):
    items = [item.GetBoundingBox() for item in fp.GraphicalItems() if item.GetLayer() == pcb.F_CrtYd]
    if not items:
        items = [pad.GetBoundingBox() for pad in fp.Pads()]
    return (min(x.GetX() for x in items)/1e6, min(x.GetY() for x in items)/1e6,
            max(x.GetRight() for x in items)/1e6, max(x.GetBottom() for x in items)/1e6)


def overlaps(a, b, gap=.15):
    return a[0] < b[2]+gap and a[2] > b[0]-gap and a[1] < b[3]+gap and a[3] > b[1]-gap


def point_segment(x, y, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    u = max(0, min(1, ((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.hypot(x-a[0]-u*dx, y-a[1]-u*dy)


def annotate(board):
    for drawing in board.GetDrawings():
        if isinstance(drawing, pcb.PCB_TEXT):
            if drawing.GetText() == 'J1 12V':
                drawing.SetPosition(pcb.VECTOR2I(pcb.FromMM(22), pcb.FromMM(31)))
            if 'A4-N16R8 PROVISIONAL' in drawing.GetText():
                drawing.SetText(drawing.GetText().replace('A4-N16R8 PROVISIONAL', 'A5-IDLE HOLD'))
    if not any(isinstance(d, pcb.PCB_TEXT) and d.GetText() == 'J21 IDLE' for d in board.GetDrawings()):
        label = pcb.PCB_TEXT(board)
        label.SetText('J21 IDLE')
        label.SetPosition(pcb.VECTOR2I(pcb.FromMM(26), pcb.FromMM(12)))
        label.SetTextSize(pcb.VECTOR2I(pcb.FromMM(.8), pcb.FromMM(.8)))
        label.SetTextThickness(pcb.FromMM(.12))
        label.SetLayer(pcb.F_SilkS)
        board.Add(label)


def place(board, fp, preferred):
    occupied = [box(f) for f in board.GetFootprints()]
    # Reserve the provisional full inward antenna envelope against new parts.
    occupied.append((14, 29, 44, 40))
    tracks = []
    buckets = {}
    for t in board.GetTracks():
        if isinstance(t, pcb.PCB_VIA):
            a = b = (t.GetPosition().x/1e6, t.GetPosition().y/1e6)
        else:
            assert not isinstance(t, pcb.PCB_ARC), 'Curve geometry needs an explicit collision adapter'
            a = (t.GetStart().x/1e6, t.GetStart().y/1e6)
            b = (t.GetEnd().x/1e6, t.GetEnd().y/1e6)
        radius = (t.GetWidth(pcb.F_Cu) if isinstance(t, pcb.PCB_VIA) else t.GetWidth())/2e6
        index = len(tracks)
        tracks.append((a, b, radius))
        # Conservative circles around new PTH pads avoid existing copper on all layers.
        for bx in range(math.floor((min(a[0], b[0])-radius-2)/4), math.floor((max(a[0], b[0])+radius+2)/4)+1):
            for by in range(math.floor((min(a[1], b[1])-radius-2)/4), math.floor((max(a[1], b[1])+radius+2)/4)+1):
                buckets.setdefault((bx, by), []).append(index)
    candidates = [(x/2, y/2, angle) for x in range(23, 258) for y in range(23, 258)
                  for angle in (0, 90, 180, 270)]
    candidates.sort(key=lambda c: (c[0]-preferred[0])**2+(c[1]-preferred[1])**2+(0 if not c[2] else .05))
    offsets = {}
    for angle in (0, 90, 180, 270):
        fp.SetPosition(pcb.VECTOR2I(0, 0))
        fp.SetOrientationDegrees(angle)
        offsets[angle] = box(fp)
    free_courts = rejected_copper = 0
    for x, y, angle in candidates:
        offset = offsets[angle]
        bounds = (x+offset[0], y+offset[1], x+offset[2], y+offset[3])
        if min(bounds[:2]) < 11 or max(bounds[2:]) > 129 or any(overlaps(bounds, other) for other in occupied):
            continue
        free_courts += 1
        fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y)))
        fp.SetOrientationDegrees(angle)
        clear = True
        for pad in fp.Pads():
            px, py = pad.GetPosition().x/1e6, pad.GetPosition().y/1e6
            radius = max(pad.GetSize().x, pad.GetSize().y)/2e6
            for index in buckets.get((math.floor(px/4), math.floor(py/4)), []):
                a, b, old_radius = tracks[index]
                if point_segment(px, py, a, b) < radius+old_radius+.3:
                    clear = False
                    break
            if not clear:
                break
        if clear:
            board.Add(fp)
            return [x, y], angle
        rejected_copper += 1
    raise RuntimeError(f'No clear placement for {fp.GetReference()}: {free_courts} free courtyards, {rejected_copper} copper conflicts')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace-generated', action='store_true')
    args = parser.parse_args()
    if OUT.exists() and not args.replace_generated:
        raise SystemExit('A5 exists. Preserve edits unless explicitly regenerating this copy.')
    OUT.mkdir(parents=True, exist_ok=True)
    original_hashes = {}
    for file in SOURCE.rglob('*'):
        if not file.is_file() or file.suffix == '.kicad_prl':
            continue
        original_hashes[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
        relative = file.relative_to(SOURCE)
        if file.suffix not in {'.kicad_sch', '.kicad_pro', '.kicad_sym', '.kicad_mod', '.wrl', '.step', '.stl', '.json'} and file.name not in {'NOTICE.md', 'fp-lib-table', 'sym-lib-table'}:
            continue
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if file.suffix == '.kicad_mod':
            data, _ = footprint_copy(file.read_bytes())
            target.write_bytes(data)
        else:
            shutil.copyfile(file, target)
    data, adaptation = board_copy((SOURCE / 'esp32-ecu.kicad_pcb').read_bytes())
    board_file = OUT / 'esp32-ecu.kicad_pcb'
    board_file.write_bytes(data)
    board = pcb.LoadBoard(str(board_file))
    assert board is not None
    for track in board.GetTracks():
        track.SetLocked(True)
    contract = json.loads((SOURCE / 'net_contract.json').read_text())
    contract.update(revision='A5-IDLE-INTERFACE-HOLD', status='NATIVE_INTERFACE_DRAFT_NOT_FOR_FABRICATION',
                    physical_fit_tested=False, manufacturing_release=False)
    contract['gpio']['IDLE_CMD'] = 3
    module = next(p for p in contract['parts'] if p['ref'] == 'U3')
    assert module['pins']['13'] is None
    module['pins']['13'] = 'IDLE_CMD'
    module['note'] += ' A5 adds GPIO3 idle service through J21 and permanent R154 bias; actual eFuse/JTAG routing and loaded output behavior remain unverified.'
    names = {f.name for f in fields(Part)}
    parts = [Part(**{k: v for k, v in p.items() if k in names}) for p in contract['parts']]
    added = [Part('R154', '2k2 1%', 'ECU:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical',
                  {'1': 'IDLE_CMD', '2': 'GND'}, {}, {}, 'core', (0, 0),
                  note='Permanent carrier-side GPIO3 bias, retained when idle harness is unplugged. Exact leaded part and actual strap/eFuse behavior require acceptance.'),
             Part('J21', 'ISOLATED_IDLE_LOGIC', 'ECU:JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical',
                  {'1': 'IDLE_CMD', '2': 'RUN_5V', '3': '+5V', '4': 'GND'},
                  {'1': 'GPIO3', '2': 'HARDWARE RUN', '3': 'LED INPUT POWER', '4': 'CARRIER RETURN'}, {},
                  'core', (0, 0), mpn='B4B-PH-K-S(LF)(SN)',
                  note='PH4 carrier to XH4 IAC-DRAFT2 J1 harness, same1..4 order. Carrier5V feeds optical LED buffers, never actuator logic/coil. Harness/case access and source loading unqualified.')]
    new_footprints = json.loads((OUT / 'new-footprints.json').read_text())
    for stem, entry in new_footprints.items():
        assert hashlib.sha256((OUT / 'lib/ecu.pretty' / (stem + '.kicad_mod')).read_bytes()).hexdigest() == entry['sha256']
    assert len({p.ref for p in parts + added}) == len(parts + added), 'References must be unique before placing or drawing any added part'
    net = pcb.NETINFO_ITEM(board, 'IDLE_CMD')
    board.Add(net)
    u3 = next(f for f in board.GetFootprints() if f.GetReference() == 'U3')
    pad = next(p for p in u3.Pads() if p.GetNumber() == '13')
    pad.SetNet(net)
    pad.SetPinType('bidirectional')
    for item, preferred in zip(added, [(13, 69.5), (38, 21)]):
        fp = pcb.FootprintLoad(str(OUT / 'lib/ecu.pretty'), item.footprint.split(':')[1])
        assert fp is not None
        fp.SetReference(item.ref)
        fp.SetValue(item.value)
        fp.SetFPID(pcb.LIB_ID('ECU', item.footprint.split(':')[1]))
        fp.SetPath(pcb.KIID_PATH('/' + builder.uid('root') + '/' + builder.uid('core') + '/' + builder.uid(item.ref)))
        fp.Reference().SetLayer(pcb.F_Fab)
        fp.Value().SetVisible(False)
        for pin in fp.Pads():
            if pin.GetNumber():
                selected = board.FindNet(item.pins[pin.GetNumber()])
                assert selected is not None
                pin.SetNet(selected)
        xy, angle = place(board, fp, preferred)
        record = {field.name: getattr(item, field.name) for field in fields(Part)}
        record.update(placed_xy_mm=xy, placed_angle_deg=angle)
        contract['parts'].append(record)
        parts.append(item)
        print(item.ref, xy, angle, flush=True)
    annotate(board)
    pcb.ZONE_FILLER(board).Fill(board.Zones())
    pcb.SaveBoard(str(board_file), board)
    builder.OUT, builder.LIB, builder.PARTS = OUT, OUT / 'lib', parts
    builder.NOTES = {'core': 'A5 IDLE INTERFACE HOLD. GPIO3 has permanent R154 bias and J21 optical-input harness. Module fit, eFuse/JTAG and physical IO remain unverified. Outputs remain inhibited.'}
    builder.write_sheet('core')
    flags = [block for _, _, block in chunks((SOURCE / 'lib/ecu.kicad_sym').read_text(), 'symbol')
             if re.match(r'\(symbol "#FLG\d+"', block)]
    assert flags, 'Retain the original power flags used by the unchanged sheets'
    (OUT / 'lib/ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "esp32_ecu_a5")\n' +
                                         '\n'.join([builder.symbol(p)[0] for p in parts if p.pins] + flags) + ')')
    for file in OUT.glob('*.kicad_sch'):
        file.write_text(file.read_text().replace('A4 N16R8 FIT HOLD', 'A5 IDLE INTERFACE HOLD')
                        .replace('A4-N16R8 PROVISIONAL', 'A5 IDLE INTERFACE HOLD')
                        .replace('ESP32 ECU A0 / core', 'ESP32 ECU A5 / core').replace('A0 BENCH', 'A5 HOLD'))
    contract['idle_interface'] = dict(connector='J21', permanent_bias='R154 2k2', gpio=3,
                                    accessory='IAC-DRAFT2 J1', physical_output_enabled=False,
                                    actual_efuses_read=False, harness_fit_tested=False)
    (OUT / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    (OUT / 'source-provenance.json').write_text(json.dumps(dict(source_revision='A4-N16R8', source_sha256=original_hashes,
        board_adaptation=adaptation, new_footprints=new_footprints, old_copper_locked=True, new_connections_unrouted=True,
        scope='New native9 copy. Original tracks/pads/zones require independent geometry/net audit; zone fills are recomputed. Module/eFuse/RF/fit holds remain.'), indent=2) + '\n')
    with (OUT / 'bom.csv').open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['Reference', 'Value', 'MPN', 'Footprint', 'DNP', 'Assembly', 'Note'])
        for p in contract['parts']:
            writer.writerow([p['ref'], p['value'], p['mpn'], p['footprint'], p.get('dnp', False),
                             'Purchased assembled module' if p['ref'] in ['U1', 'U3'] else 'Through hole', p['note']])
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == digest for p, digest in original_hashes.items())
    print('A5 copy created. New nets require routing/native checks; no manufacturing release.')


if __name__ == '__main__':
    main()
