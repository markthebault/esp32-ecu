#!/usr/bin/env python3
"""Create a fresh boost accessory or A7 copy; never rewrite an older carrier.

KiCad9 Python is required. Copper may remain unrouted. Native checks, source
comparison, circuit experiments and physical acceptance are separate steps.
"""
import argparse
import csv
from dataclasses import fields
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys

import pcbnew as pcb
import build_hardware as builder
from build_a5_idle_interface import place, point_segment
from design import Part
from kicad9_carrier_copy import chunks, footprint_copy
from route_a5_idle_interface import geometry

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'hardware/boost-control'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy_source(source, output):
    before = {str(p.relative_to(source)): sha(p) for p in source.rglob('*')
              if p.is_file() and p.suffix not in ('.kicad_prl', '.lck')}
    output.mkdir(parents=True, exist_ok=False)
    for relative in before:
        path = source / relative
        if path.suffix in ('.kicad_sch', '.kicad_pro', '.kicad_pcb', '.kicad_sym', '.kicad_mod', '.kicad_dru') or relative.startswith('lib/') or path.name in ('fp-lib-table', 'sym-lib-table'):
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    return before


def part(row, page=None):
    aliases = dict(ref=row.get('ref', row.get('reference')), names=row.get('names', row.get('pin_names', {})),
                   types=row.get('types', row.get('pin_types', {})),
                   xy=row.get('xy', row.get('placed_xy_mm')), angle=row.get('angle', row.get('placed_angle_deg', 0)),
                   page=page or row.get('page'))
    return Part(**{field.name: aliases[field.name] if field.name in aliases else row[field.name]
                   for field in fields(Part) if field.name in aliases or field.name in row})


def footprint(output, stem):
    source = DESIGN / 'footprints' / (stem + '.kicad_mod')
    data, removed = footprint_copy(source.read_bytes())
    target = output / 'lib/ecu.pretty' / source.name
    target.write_bytes(data)
    return dict(source=str(source.relative_to(ROOT)), source_sha256=sha(source),
                copy_sha256=sha(target), adapted_metadata=removed)


def write_sheet(output, parts, page, note, single=False):
    builder.OUT, builder.LIB, builder.PARTS = output, output / 'lib', parts
    builder.NOTES = {page: note}
    builder.write_sheet(page)
    path = output / (page + '.kicad_sch')
    text = path.read_text().replace('2026-10-30', '2026-11-05').replace('A0 BENCH', 'BOOST HOLD')
    text = text.replace('ESP32 ECU A0 / ' + page, 'ESP32 ECU boost development / ' + page)
    if single:
        text = text.replace('/' + builder.uid('root') + '/' + builder.uid(page), '/' + builder.uid(page))
        for start, end, block in reversed(list(chunks(text, 'symbol'))):
            if '(lib_id "ECU:NT1")' in block:
                text = text[:start] + block.replace('(in_bom yes)', '(in_bom no)', 1) + text[end:]
        text = text[:-1] + '(sheet_instances (path "/" (page "1"))))'
    path.write_text(text)


def library(output, parts, flags=()):
    (output / 'lib/ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "esp32_ecu_boost")\n' +
        '\n'.join([builder.symbol(p)[0] for p in parts if p.pins] + list(flags)) + ')')


def bind_pad(board, fp, item, key, single=False):
    net = item.pins[key] or builder.nc_net(item, key)
    if board.FindNet(net) is None or board.FindNet(net).GetNetCode() == 0:
        board.Add(pcb.NETINFO_ITEM(board, net))
    pad = next(p for p in fp.Pads() if p.GetNumber() == key)
    pad.SetNet(board.FindNet(net))
    pad.SetPinFunction(item.names.get(key, key))
    pad.SetPinType(item.types.get(key, 'passive'))


def update_fp(board, fp, item, single=False):
    attributes = fp.GetAttributes()
    fp.SetValue(item.value)
    fp.SetPath(pcb.KIID_PATH('/' + ('' if single else builder.uid('root') + '/') + builder.uid(item.page) + '/' + builder.uid(item.ref)))
    for key, value in [('MPN', item.mpn), ('DesignNote', item.note)]:
        fp.SetField(key, value)
        fp.GetFieldByName(key).SetVisible(False)
    fp.Value().SetVisible(False)
    for key in item.pins:
        bind_pad(board, fp, item, key, single)
    # SetPath clears KiCad's board-only bit. Mechanical holes and the unfitted
    # copper tie must retain their original explicit board/BOM attributes.
    fp.SetAttributes(attributes | (pcb.FP_BOARD_ONLY if not item.pins else 0))


def add_fp(board, output, item, single=False, attach=True):
    fp = pcb.FootprintLoad(str(output / 'lib/ecu.pretty'), item.footprint.split(':')[1])
    assert fp is not None, item.ref
    fp.SetReference(item.ref)
    fp.SetFPID(pcb.LIB_ID('ECU', item.footprint.split(':')[1]))
    if attach:
        board.Add(fp)
    fp.Reference().SetLayer(pcb.F_Fab)
    update_fp(board, fp, item, single)
    return fp


def bom(output, rows):
    with (output / 'bom.csv').open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['Reference', 'Value', 'MPN candidate', 'Footprint', 'Assembly', 'Note'])
        for row in rows:
            writer.writerow([row.get('ref', row.get('reference')), row['value'], row['mpn'], row['footprint'],
                             row.get('placed_side', 'front'), row['note']])


def accessory(output):
    source = ROOT / 'hardware/idle-isolated'
    design = json.loads((DESIGN / 'circuit-draft1.json').read_text())
    assert sha(source / 'net_contract.json') == design['parent_contract_sha256']
    inherited = copy_source(source, output)
    contract = design['circuit']
    parts = [part(row, 'isolated') for row in contract['parts']]
    board = pcb.LoadBoard(str(output / 'isolated.kicad_pcb'))
    aliases = design['net_renames']
    for new in aliases.values():
        board.Add(pcb.NETINFO_ITEM(board, new))
    # Net names are keys in KiCad9's internal map. Rebind items instead of
    # mutating NETINFO_ITEM names in place and leaving that map inconsistent.
    for item in list(board.GetTracks()) + [pad for fp in board.GetFootprints() for pad in fp.Pads()]:
        if item.GetNetname() in aliases:
            item.SetNet(board.FindNet(aliases[item.GetNetname()]))
    # Input-network geometry and both connectors change. Other copper stays
    # locked, including local detector/driver bypass and the source star.
    reroute = set(design['reroute_nets'])
    old_footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    detached_pads = [next(pad for pad in old_footprints[row['reference']].Pads() if pad.GetNumber() == row['pin'])
                     for row in design.get('remove_parent_pad_branches', [])]
    retained = []
    omitted_parent = []
    removed = []
    for track in list(board.GetTracks()):
        moved_endpoint = not isinstance(track, pcb.PCB_VIA) and any(
            track.GetNetname() == pad.GetNetname() and (track.GetStart() == pad.GetPosition() or track.GetEnd() == pad.GetPosition())
            for pad in detached_pads)
        declared_spur = track.m_Uuid.AsString() in design.get('remove_parent_track_uuids', [])
        if track.GetNetname() in reroute or moved_endpoint or declared_spur:
            # The KiCad9 Remove wrapper transfers ownership to Python, whose
            # generic SWIG track proxy can then corrupt the live board. Keep
            # detached native objects alive until this short process exits.
            board.RemoveNative(track)
            removed.append(track)
            omitted_parent.append(geometry(track))
        else:
            track.SetLocked(True)
            retained.append(geometry(track))
    origins = {}
    for stem in design['new_footprints']:
        origins[stem] = footprint(output, stem)
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for item in parts:
        row = next(row for row in contract['parts'] if row['reference'] == item.ref)
        fp = footprints.get(item.ref)
        if fp is not None and fp.GetFPID().GetLibItemName() != item.footprint.split(':')[1]:
            board.RemoveNative(fp)
            removed.append(fp)
            fp = None
        if fp is None:
            fp = add_fp(board, output, item, single=True)
        else:
            update_fp(board, fp, item, single=True)
        fp.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(v) for v in item.xy)))
        fp.SetOrientationDegrees(item.angle)
        if row['placed_side'] == 'back' and fp.GetLayer() != pcb.B_Cu:
            fp.Flip(fp.GetPosition(), False)
            fp.SetOrientationDegrees(item.angle)
        fp.Reference().SetLayer(pcb.B_Fab if row['placed_side'] == 'back' else pcb.F_Fab)
    for text in board.GetDrawings():
        if isinstance(text, pcb.PCB_TEXT):
            text.SetText(text.GetText().replace('IAC-DRAFT2', 'BOOST-DRAFT1'))
    write_sheet(output, parts, 'isolated', 'BOOST-DRAFT1 / HOLD. Optical inputs, separate actuator supply and source return. Outputs inhibited. No physical qualification.', single=True)
    library(output, parts)
    pcb.SaveBoard(str(output / 'isolated.kicad_pcb'), board)
    (output / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    bom(output, contract['parts'])
    return source, inherited, dict(design_sha256=sha(DESIGN / 'circuit-draft1.json'),
        retained_copper=retained, omitted_parent_copper=omitted_parent, reroute_nets=sorted(reroute), new_footprints=origins,
        physical_outputs_enabled=False, manufacturing_release=False)


def carrier(output):
    source = ROOT / 'hardware/a6-flex-rgb'
    design = json.loads((DESIGN / 'interface-draft2.json').read_text())
    assert sha(source / 'net_contract.json') == design['parent']['sha256']
    inherited = copy_source(source, output)
    board = pcb.LoadBoard(str(output / 'esp32-ecu.kicad_pcb'))
    retained = []
    for track in board.GetTracks():
        track.SetLocked(True)
        retained.append(geometry(track))
    contract = json.loads((source / 'net_contract.json').read_text())
    rows = contract['parts']
    module = next(row for row in rows if row['ref'] == 'U3')
    assert module['pins']['37'] is None and module['names']['37'] == '45'
    module['pins']['37'] = 'BOOST_CMD'
    module['note'] += ' A7 adds permanent GPIO45 bias and a shared ZH5 idle/boost optical-input header at J21. Actual strapping/eFuse/fit and physical writes remain unqualified/inhibited.'
    origins = {stem: footprint(output, stem) for stem in design['new_footprints']}
    omitted_parent = []
    detached = []
    for replacement in design.get('replaced_parts', []):
        ref = replacement['ref']
        index = next(i for i, old in enumerate(rows) if old['ref'] == ref)
        previous = rows[index]
        assert ref == 'J21' and previous['pins'] == {'1': 'IDLE_CMD', '2': 'RUN_5V', '3': '+5V', '4': 'GND'}
        old_fp = next(fp for fp in board.GetFootprints() if fp.GetReference() == ref)
        xy = [old_fp.GetPosition().x/1e6, old_fp.GetPosition().y/1e6]
        angle = old_fp.GetOrientationDegrees()
        board.RemoveNative(old_fp); detached.append(old_fp)
        row = {**previous, **replacement, 'placed_xy_mm': xy, 'placed_angle_deg': angle, 'xy': xy, 'angle': angle}
        item = part(row)
        fp = add_fp(board, output, item)
        fp.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(v) for v in xy)))
        fp.SetOrientationDegrees(angle)
        # The new five-pin pitch differs from the old four-pin pitch. Remove
        # only copper that actually collides with a different new pin net.
        # All removals are recorded; A6 and its original harness stay intact.
        for track in list(board.GetTracks()):
            if isinstance(track, pcb.PCB_VIA):
                a = b = (track.GetPosition().x/1e6, track.GetPosition().y/1e6)
                radius = track.GetWidth(pcb.F_Cu)/2e6
            else:
                a, b = (track.GetStart().x/1e6, track.GetStart().y/1e6), (track.GetEnd().x/1e6, track.GetEnd().y/1e6)
                radius = track.GetWidth()/2e6
            conflict = False
            for pad in fp.Pads():
                pr = (math.hypot(pad.GetSize().x, pad.GetSize().y) if pad.GetShape() == pcb.PAD_SHAPE_RECT
                      else max(pad.GetSize().x, pad.GetSize().y))/2e6
                if track.GetNetname() != pad.GetNetname() and point_segment(pad.GetPosition().x/1e6, pad.GetPosition().y/1e6, a, b) < pr+radius+.25:
                    conflict = True; break
            if conflict:
                omitted_parent.append(geometry(track)); board.RemoveNative(track); detached.append(track)
        rows[index] = row
    for row in design['added_parts']:
        assert row['ref'] not in {old['ref'] for old in rows}
        item = part(row)
        fp = add_fp(board, output, item, attach=False)
        assert row.get('placed_side', 'front') == 'front'
        xy, angle = place(board, fp, row['preferred_xy_mm'])
        row.update(placed_xy_mm=xy, placed_angle_deg=angle, xy=xy, angle=angle)
        rows.append(row)
    parts = [part(row) for row in rows]
    u3 = next(fp for fp in board.GetFootprints() if fp.GetReference() == 'U3')
    update_fp(board, u3, next(p for p in parts if p.ref == 'U3'))
    flags = [block for _, _, block in chunks((source / 'lib/ecu.kicad_sym').read_text(), 'symbol')
             if re.match(r'\(symbol "#FLG\d+"', block)]
    assert flags
    write_sheet(output, parts, 'core', 'A7 BOOST INTERFACE HOLD. ZH5 J21 shared idle/boost optical input, GPIO45/R180 permanent bias. Separate actuator supplies; engine physical outputs inhibited.')
    library(output, parts, flags)
    for path in output.glob('*.kicad_sch'):
        path.write_text(path.read_text().replace('A6 FLEX', 'A7 BOOST').replace('A6-FLEX', 'A7-BOOST'))
    contract.update(revision='A7-BOOST-INTERFACE-HOLD', status='UNROUTED_INTERFACE_HOLD_NOT_FOR_FABRICATION',
                    manufacturing_release=False, physical_fit_tested=False)
    contract['gpio']['BOOST_CMD'] = 45
    contract['boost_interface'] = dict(contract=design['contract'], connector='J21 ZH5 pin5', permanent_bias='R180 2k2',
        gpio=45, firmware_allocation_active=False, physical_outputs_enabled=False,
        accessory='BOOST-DRAFT1 J1', actual_efuses_read=False, actual_fit_tested=False)
    contract['idle_interface'].update(connector='J21 ZH5 pin1', harness='A7 five-wire insulated fanout; original A5/A6 PH4 harness does not mate',
        shared_pins={'2': 'RUN_5V', '3': '+5V', '4': 'GND'}, physical_output_enabled=False)
    for drawing in board.GetDrawings():
        if isinstance(drawing, pcb.PCB_TEXT):
            drawing.SetText(drawing.GetText().replace('A6-FLEX-RGB HOLD', 'A7 BOOST HOLD'))
    pcb.ZONE_FILLER(board).Fill(board.Zones())
    pcb.SaveBoard(str(output / 'esp32-ecu.kicad_pcb'), board)
    (output / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    bom(output, rows)
    return source, inherited, dict(design_sha256=sha(DESIGN / 'interface-draft2.json'),
        retained_copper=[row for row in retained if row not in omitted_parent], omitted_parent_copper=omitted_parent,
        new_footprints=origins, physical_outputs_enabled=False, manufacturing_release=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('accessory', 'carrier'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    helper_files = [Path(__file__).resolve()] + [Path(sys.modules[name].__file__).resolve() for name in
        ('build_hardware', 'build_a5_idle_interface', 'design', 'kicad9_carrier_copy', 'route_a5_idle_interface')]
    helper_files += [p for p in DESIGN.rglob('*') if p.is_file() and p.suffix in ('.json', '.kicad_mod')]
    frozen = {str(path.relative_to(ROOT)): path.read_bytes() for path in helper_files}
    source, before, record = (accessory if args.kind == 'accessory' else carrier)(args.output.resolve())
    for name, expected in before.items():
        assert sha(source / name) == expected, 'Source changed: ' + name
    record.update(source=str(source.relative_to(ROOT)), source_files_sha256=before,
                  generator_sha256=sha(__file__), source_unchanged=True, new_connections_unrouted=True)
    for relative, content in frozen.items():
        assert (ROOT/relative).read_bytes() == content, 'Generator input changed: ' + relative
        target = args.output/'generator-source'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    record['generator_source_sha256'] = {relative: hashlib.sha256(content).hexdigest() for relative, content in frozen.items()}
    native = Path(pcb._pcbnew.__file__)
    record['native_runtime'] = dict(python=sys.version, python_executable=sys.executable, python_sha256=sha(sys.executable),
        kicad_version=pcb.Version(), wrapper_sha256=sha(pcb.__file__), native_module=str(native), native_module_sha256=sha(native))
    (args.output / 'source-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(dict(created=str(args.output), source_unchanged=True, physical_outputs_enabled=False)))


if __name__ == '__main__':
    main()
