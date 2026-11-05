#!/usr/bin/env python3
"""Reconcile a fresh A6 draft with declared circuit metadata and draft BOMs.

Refuses topology changes. Preserves source, copper and pad geometry. This does
not release fabrication, sensor wiring, power, fit or physical engine operation.
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import pcbnew as pcb

from build_a6_flex_rgb import convert
from finalize_a6_native import pads
from kicad9_carrier_copy import chunks
from route_a5_idle_interface import geometry

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    # Only the newly owned output copy is regenerated. Retain an existing
    # generated CSV there too, while the source tree stays byte-identical.
    if path.exists():
        previous = path.parent / 'prior-generated' / sha(path) / path.name
        previous.parent.mkdir(parents=True, exist_ok=True)
        if not previous.exists():
            shutil.copyfile(path, previous)
        assert sha(previous) == sha(path)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def metadata(path, changes):
    text, edits = path.read_text(), []
    for start, end, block in chunks(text, 'symbol'):
        match = re.match(r'\(symbol\s+(?:\(lib_id\s+)?"(?:ECU:)?([^"]+)"', block)
        if match is None or match[1] not in changes:
            continue
        part = changes[match[1]]
        for field, value in [('Value', part.value), ('MPN', part.mpn), ('DesignNote', part.note)]:
            block = re.sub(r'(\(property\s+' + json.dumps(field) + r'\s+)"(?:\\.|[^"\\])*"',
                           lambda m: m[1] + json.dumps(value), block)
        edits.append((start, end, block))
    for start, end, block in reversed(edits):
        text = text[:start] + block + text[end:]
    if edits:
        path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frontend', type=Path,
                        default=ROOT / 'hardware/flex-input/frontend.json')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    assert not output.exists(), 'Choose a fresh output'
    source_hashes = {str(p.relative_to(source)): sha(p) for p in source.rglob('*')
                     if p.is_file() and p.suffix not in ('.kicad_prl', '.lck')}
    contract = json.loads((source / 'net_contract.json').read_text())
    assert contract['revision'] == 'A6-FLEX-RGB-HOLD'
    frontend_path = args.frontend.resolve()
    led_path = ROOT / 'hardware/flex-input/status-led.json'
    frontend, led = json.loads(frontend_path.read_text()), json.loads(led_path.read_text())
    changes = {row['ref']: convert(row, page)
               for profile, page in [(frontend, 'flex'), (led, 'status_led')]
               for row in profile['parts']}
    declared = {p['ref']: p for p in contract['parts']}
    package_changes = frontend.get('existing_package_changes', {})
    assert set(package_changes) <= {'J20'}
    compact = frontend['contract'] == 'FLEX-G38-FRONTEND-COMPACT-DRAFT2'
    assert compact or frontend['contract'] == 'FLEX-G38-FRONTEND-DRAFT1'
    assert contract['flex_input']['contract'] == frontend['contract']
    for ref, row in package_changes.items():
        changes[ref] = convert(row, declared[ref]['page'])
    for ref, part in changes.items():
        assert declared[ref]['pins'] == part.pins, ('Topology change refused', ref)
        assert declared[ref]['footprint'].split(':')[-1] == part.footprint.split(':')[-1]
    shutil.copytree(source, output, ignore=shutil.ignore_patterns('*.kicad_prl', '*.lck', '*~'))
    for name, target in [('LICENSE-KiCad.md', 'LICENSE-KiCad.md'),
                         ('NOTICE.md', 'R179-footprint-NOTICE.md'),
                         ('provenance.json', 'R179-footprint-provenance.json')]:
        shutil.copyfile(ROOT / 'hardware/flex-input/footprints' / name, output / 'lib' / target)
    if compact:
        for name in ('compact-capacitor-provenance.json', 'compact-shield-connector-provenance.json'):
            shutil.copyfile(ROOT / 'hardware/flex-input/footprints' / name, output / 'lib' / name)
    board_path = output / 'esp32-ecu.kicad_pcb'
    board = pcb.LoadBoard(str(board_path))
    before_pads, before_copper = pads(board), sorted(geometry(t) for t in board.GetTracks())
    for fp in board.GetFootprints():
        if fp.GetReference() in changes:
            part = changes[fp.GetReference()]
            fp.SetValue(part.value)
            fp.SetField('MPN', part.mpn)
            fp.SetField('DesignNote', part.note)
            for name in ('MPN', 'DesignNote'):
                field = fp.GetFieldByName(name)
                assert field is not None
                field.SetVisible(False)
                field.SetLayer(pcb.F_Fab)
            declared[part.ref].update(value=part.value, mpn=part.mpn, note=part.note)
        # Reconcile inherited component metadata too. An old added connector
        # can have a valid contract/BOM MPN while its embedded PCB field is empty.
        row = declared[fp.GetReference()]
        try:
            existing_mpn = fp.GetFieldText('MPN')
        except KeyError:
            existing_mpn = ''
        if existing_mpn != row['mpn']:
            fp.SetField('MPN', row['mpn'])
        field = fp.GetFieldByName('MPN')
        if field is not None:
            field.SetVisible(False)
            field.SetLayer(pcb.B_Fab if fp.GetLayer() == pcb.B_Cu else pcb.F_Fab)
    pcb.SaveBoard(str(board_path), board)
    check = pcb.LoadBoard(str(board_path))
    assert pads(check) == before_pads
    assert sorted(geometry(t) for t in check.GetTracks()) == before_copper
    for path in list(output.glob('*.kicad_sch')) + [output / 'lib/ecu.kicad_sym']:
        metadata(path, changes)
    contract['status_led'].update(contract=led['contract'], source_sha256=sha(led_path))
    contract['flex_input'].update(contract=frontend['contract'], source_sha256=sha(frontend_path),
                                  source_profile=str(frontend_path.relative_to(ROOT)))
    contract.update(status='NATIVE_DRAFT_METADATA_RECONCILED_HOLD',
                    native_checks_required=True, manufacturing_release=False, physical_fit_tested=False)
    (output / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    provenance_path = output / 'source-provenance.json'
    provenance = json.loads(provenance_path.read_text())
    if 'initial_geometry_placements' not in provenance:
        provenance['initial_geometry_placements'] = provenance.get('placements')
        provenance['initial_geometry_packing'] = provenance.get('packing')
    provenance['placements'] = {p['ref']: dict(xy_mm=p['placed_xy_mm'], angle_deg=p['placed_angle_deg'],
                                              side=p.get('placed_side', 'F.Cu'))
                               for p in contract['parts']}
    provenance['packing'] = dict(role='Historical initial packing moved to initial_geometry_packing; '
                                'current positions also include locality assignment and explicit ECO.',
                                current_coordinates='net_contract.json')
    provenance['latest_metadata_source'] = str(source)
    provenance['latest_metadata_generator_sha256'] = sha(Path(__file__))
    provenance_path.write_text(json.dumps(provenance, indent=2) + '\n')
    with (output / 'bom.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        p = declared[row['Reference']]
        row.update(Value=p['value'], MPN=p['mpn'], Footprint=p['footprint'], Note=p['note'],
                   Assembly='Purchased module' if p['ref'] in ('U1', 'U3') else
                   'PCB feature' if p['ref'].startswith(('H', 'TP')) else 'Direct-solder THT')
    with (output / 'bom.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    # Cable-side pin numbering follows the native carrier contract. It is not
    # an accepted external sensor plug drawing; that contradiction stays open.
    with (ROOT / 'hardware/a3-compact/connector-pinout.csv').open(newline='') as stream:
        housings = {row['Connector']: row['Mating housing'] for row in csv.DictReader(stream)}
    housings.update(J21='PHR-4', J22='VHR-3N', J23='PHR-5')
    if 'J20' in package_changes:
        assert package_changes['J20']['mpn'] == 'B2B-PH-K-S(LF)(SN)'
        assert package_changes['J20']['pins'] == {'1': 'CHASSIS', '2': 'CHASSIS'}
        housings['J20'] = 'PHR-2'
    connectors = []
    counts = defaultdict(int)
    housing_counts = defaultdict(list)
    for p in contract['parts']:
        ref = p['ref']
        if not re.fullmatch(r'J\d+', ref):
            continue
        housing = housings[ref]
        housing_counts[housing].append(ref)
        for pin, net in p['pins'].items():
            if housing.startswith(('XHP-', 'VHR-', 'PHR-')) and net is not None:
                counts[housing.split('-')[0]] += 1
            guidance = 'Carrier pin only; consult existing sensor/idle/service guides'
            if ref == 'J22':
                guidance = 'HOLD: exact sensor plug mapping unresolved; FLEX_12V is not18V limited'
            elif ref == 'J23':
                led_pin = led['external_led']['J23_to_led_pin'][pin]
                guidance = 'NO CONTACT OR WIRE' if led_pin is None else 'Candidate Kingbright LED pin' + led_pin
            elif ref == 'J20' and 'J20' in package_changes:
                guidance = 'Internal PH2 shield/lining bond, both pins CHASSIS; no normal load return. H5 remains designated chassis lug.'
            connectors.append({'Connector': ref, 'Label': p['value'], 'PCB pin': pin,
                               'Net': net or 'NC', 'Mating housing': housing,
                               'Contact populated': net is not None, 'Guidance': guidance})
    write_csv(output / 'connector-pinout.csv', connectors)
    groups = defaultdict(list)
    for p in contract['parts']:
        if not p['ref'].startswith(('H', 'TP')):
            groups[(p['value'], p['mpn'], p['footprint'], p.get('dnp', False))].append(p)
    shopping = []
    for (value, mpn, footprint, dnp), parts in sorted(groups.items()):
        shopping.append({'Section': 'PCB', 'Quantity': 0 if dnp else len(parts),
                         'Optional quantity': len(parts) if dnp else 0, 'Item': value,
                         'MPN / specification': mpn or 'Select exact part',
                         'References / use': ', '.join(p['ref'] for p in parts),
                         'Package / fit': footprint,
                         'Selection status': 'DNP' if dnp else 'Candidate MPN; fit/rating/stock unqualified' if mpn else 'Exact part selection required',
                         'Notes': ' | '.join(dict.fromkeys(p['note'] for p in parts if p['note']))})

    def extra(qty, item, specification, use, note):
        shopping.append(dict(zip(shopping[0], ['Ancillary', qty, 0, item, specification, use,
                                               'Fit and procurement pending', 'Development candidate', note])))

    extra(2, 'ESP32 female socket strip', '1x22 2.54mm', 'U3',
          '22.86mm row spacing and elevated inward antenna geometry unverified; no DIP sockets')
    for housing, refs in sorted(housing_counts.items()):
        extra(len(refs), 'Mating housing', housing, ', '.join(refs),
              'Internal connector; no sealed external connector rating. Service headers require matching plugs.')
    for family, qty in sorted(counts.items()):
        specification = {'XHP': 'SXH-001T-P0.6', 'VHR': 'SVH-21T-P1.1 or SVH-41T-P1.1 by wire/load',
                         'PHR': 'SPH-002T-P0.5S by wire'}[family]
        extra(qty, 'Crimp contact count excluding NC pins', specification, family,
              'Maximum connected-cavity count before spares; actual gauge/tooling/load and unused sensor supply wires require review')
    extra(1, 'Ordinary common-anode RGB LED', led['external_led']['mpn'], 'J23',
          'J23 pins1/2/3/4 map to LED pins2/1/4/3; J23 pin5 empty. Common-anode supply has R179330R in addition to individual cathode resistors. Brightness, lead fit, optics and sealing unqualified.')
    extra(2, 'Sealed normally-open momentary button', 'PAIR and RESET, exact parts pending', 'J2 service harness',
          'See docs/espnow.md; enclosure, cap, cable, seal, wall thickness and physical fit remain unqualified.')
    write_csv(output / 'bom-shopping.csv', shopping)
    summary = dict(footprints=len(contract['parts']), pcb_purchase_groups=len(groups),
                   fitted_pcb_components=sum(not p.get('dnp', False) for g in groups.values() for p in g),
                   dnp_references=[p['ref'] for p in contract['parts'] if p.get('dnp', False)],
                   connected_crimp_contact_counts=dict(counts), manufacturing_release=False)
    (output / 'bom-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    guard = next(p for p in led['parts'] if p['ref'] == 'R179')
    guard_mount_note = ('R179 is horizontal on the back: solder it first, trim leads, '
                        'and verify4mm underside space, insulation and access against the actual assembly.'
                        if guard['mounting']['side'] == 'B.Cu' else
                        'R179 is the upright330R MRS16 candidate on its smaller DIN0204 footprint. '
                        'Match the stated body/rating, formed leads and actual assembly; thermal and case fit remain unqualified.')
    compact_note = (
        'The compact frontend uses nine MRS16 0.4W P70 resistor candidates, R157 through R165. '
        'Their body envelope is a maximum3.6 x1.6mm; lead forming, assembled derating and heat remain unqualified. '
        'R155/R156/R166 retain their750R 0.6W selection. C158/C159 use C315 C0G parts; '
        'C160 and the added local3V3 bypass C164 use C315 X7R parts. Nominal100nF is not an effective-value '
        'or supply-impedance guarantee. The proposed0.8mm holes and2.54mm pitch require checking actual leads '
        'and formed pitch; the specified pitch tolerance can require forming. Use the manufacturer hand-solder '
        'preheat/thermal-shock guidance. J20 uses B2B-PH-K-S(LF)(SN), PHR-2 and two SPH-002T-P0.5S contacts '
        'for the internal CHASSIS shield/lining bond, with no normal load current. H5 remains the chassis lug. '
        'These component/package changes do not establish enclosure, module, electrical or physical fit. '
        if compact else '')
    (output / 'BOM.md').write_text(
        '# A6 development BOM, fabrication on hold\n\n'
        f'The native contract contains {summary["footprints"]} footprints and '
        f'{summary["fitted_pcb_components"]} fitted electronic references. '
        'The [grouped draft shopping CSV](bom-shopping.csv), [per-reference assembly CSV](bom.csv) '
        'and [carrier pinout](connector-pinout.csv) describe this separate draft.\n\n'
        'All listed MPNs are candidates. Match actual power, tolerance, temperature, ESR, lead pitch, '
        'upright formed body and height. Direct-solder DIP devices; only the ESP32 uses sockets. '
        'The old enclosure/material BOM remains historical and does not establish A6 fit. '
        'The PCB has no fabrication release.\n\n'
        'J22 sensor supply is not18V limited, and its external sensor pinout is unresolved. '
        'J23 PH5 has four populated contacts; pin5 remains empty. '
        'R179330R limits its common supply in addition to the three cathode resistors; '
        'the conditional ground-fault bound does not establish brightness or a physical protection rating. '
        f'{guard_mount_note} '
        'The RGB supervisor is MCP121-270E/TO; release hysteresis has a25C table condition. '
        'Rail headroom, loaded GPIO/readback, reset, heat, optics and sealed installation require physical checks.\n\n'
        f'{compact_note}\n')
    (output / 'README.md').write_text(
        '# A6 protected-flex and ordinary-RGB carrier draft\n\n'
        f'This separate120 x120mm six-layer native KiCad9 draft adds{len(frontend["parts"])} flex-input '
        f'and{len(led["parts"])} RGB parts '
        'to the A5 logical design. Placement and all copper are new; old A3/A4/A5 sources remain preserved. '
        '**No fabrication, sensor connection, module/enclosure fit or physical engine release.**\n\n'
        '[Native project](esp32-ecu.kicad_pro) · [Contract](net_contract.json) · [BOM](BOM.md) · '
        '[Carrier pinout](connector-pinout.csv) · [Circuit limits](../flex-input/README.md)\n\n'
        'U3 pad32/GPIO38 receives only the protected flex candidate. Build compact_n16r8_flex_dev; '
        'historical GPIO38 WS2812/RMT firmware is incompatible. Physical engine outputs remain inhibited. '
        'MCP23008 at0x21 uses GP0/1/2 for red/green/blue through NPN sinks; GP3..7 stay low and NC. '
        'Steady green, blue pairing blink and red problem blink are advisory requests. Retained green '
        'does not prove live CPU, current readback or actual light.\n\n'
        'J21 PH4 retains isolated idle logic. J22 VH3 carries1 GND,2 FLEX_12V,3 FLEX_RAW; '
        'FLEX_12V is not an18V regulator and the AEM external plug drawing remains unresolved. '
        'J23 PH5 carries1 LED_5V through R179330R,2 red cathode,3 green cathode,4 blue cathode,5 NC with no contact. '
        'All connectors are internal; sealing/optical-window and harness fit are separate work.\n\n'
        f'{guard_mount_note}\n\n'
        f'{compact_note}\n\n'
        'The N16R8 socket spacing, elevated stack, inward10mm antenna allowance and onboard RGB '
        '47/48 conflict remain unverified. The current native routing/check status must be read from '
        'the contract and attached evidence; software/circuit/native checks do not qualify physical '
        'timing, RF, supply protection, thermal behavior, vehicle operation or splash resistance.\n')
    (output / 'circuit-reconciliation.json').write_text(json.dumps(dict(
        source_directory=str(source), source_sha256=source_hashes,
        generator_sha256=sha(Path(__file__)),
        circuit_inputs={str(frontend_path.relative_to(ROOT)): sha(frontend_path),
                        str(led_path.relative_to(ROOT)): sha(led_path)},
        topology_and_pad_copper_geometry_unchanged=True,
        manufacturing_release=False, scope=__doc__), indent=2) + '\n')
    assert all(sha(source / p) == digest for p, digest in source_hashes.items())
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
