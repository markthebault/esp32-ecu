#!/usr/bin/env python3
"""Create IAC-DRAFT2, a separate THT optical idle driver, never overwrite DRAFT1.

KiCad Python9 is required. This creates placement/netlist material. Routing,
native checks and physical acceptance are separate. No fabrication export.
"""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

import pcbnew as pcb
import build_hardware as builder
from design import Part
from kicad9_carrier_copy import footprint_copy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware/idle-isolated'
PARTS = []
RFP = 'R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical'
CFP = 'C_Disc_D5.0mm_W2.5mm_P5.00mm'


def part(ref, value, footprint, pins, xy, names=None, types=None, mpn='', note='', angle=0):
    item = Part(ref, value, 'ECU:' + footprint, {str(k): v for k, v in pins.items()},
                {str(k): v for k, v in (names or {}).items()},
                {str(k): v for k, v in (types or {}).items()}, 'isolated', xy,
                angle, mpn, note)
    PARTS.append(item)
    return item


part('J1', 'CARRIER INPUT DOMAIN', 'JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical',
     {1: 'IDLE_CMD', 2: 'RUN_5V', 3: 'CARRIER_5V', 4: 'CARRIER_GND'}, (15, 24),
     {1: 'GPIO3', 2: 'HARDWARE RUN', 3: 'INPUT LED POWER', 4: 'INPUT RETURN'},
     {1: 'output', 2: 'output', 3: 'power_out', 4: 'power_out'},
     'B4B-XH-A(LF)(SN)', 'Only optocoupler LED/buffer circuitry uses carrier power/ground. A5 J21; permanent carrier GPIO3 bias required.')
part('J2', 'PROTECTED ACTUATOR SUPPLY', 'TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal',
     {1: 'ACT_12V', 2: 'ACT_GND'}, (90, 57),
     {1: 'EXTERNAL FUSED SWITCHED 9-16V', 2: 'ACTUATOR RETURN'}, {1: 'power_out', 2: 'power_out'},
     '1715721', 'Separate externally fused, relay-switched, reverse/transient-protected branch. Never carrier/sensor supply. No onboard coil current limit.')
part('J3', 'NC TWO-WIRE VALVE', 'JST_VH_B2P-VH_1x02_P3.96mm_Vertical',
     {1: 'ACT_12V', 2: 'IAC_LS'}, (90, 23), {1: 'VALVE PLUS', 2: 'VALVE LOW SIDE'},
     mpn='B2P-VH(LF)(SN)', note='Normally closed, continuous PWM, energize-to-open; actual coil <=2A across voltage/temp. Valve selection and decay remain unqualified.')
part('Q1', 'IRLZ44NPBF', 'TO-220-3_Vertical', {1: 'GATE', 2: 'IAC_LS', 3: 'ACT_GND'}, (90, 39),
     {1: 'GATE', 2: 'DRAIN / LIVE TAB', 3: 'SOURCE'}, mpn='IRLZ44NPBF',
     note='Fast logic-level MOSFET, no automatic current/thermal shutdown or fault feedback. Drain tab must not bridge domains or share an uninsulated regulator heatsink.')
for ref, command, base, cathode, xy in [
        ('Q2', 'IDLE_CMD', 'PWM_BASE', 'PWM_LED_K', (21, 38)),
        ('Q3', 'RUN_5V', 'RUN_BASE', 'RUN_LED_K', (21, 55))]:
    part(ref, '2N3904', 'TO-92_Inline_Wide', {1: 'CARRIER_GND', 2: base, 3: cathode}, xy,
         {1: 'EMITTER', 2: 'BASE', 3: 'COLLECTOR'}, mpn='2N3904BU',
         note='Input-side LED buffer, E-B-C formed leads at2.54mm. Loaded GPIO/RUN levels, saturation and storage over temperature require bench acceptance.')
for ref, anode, cathode, output, xy in [
        ('U2', 'PWM_LED_A', 'PWM_LED_K', 'PWM_N', (34, 22)),
        ('U3', 'RUN_LED_A', 'RUN_LED_K', 'RUN_N', (34, 45))]:
    part(ref, '6N137', 'DIP-8_W7.62mm_LongPads',
         {1: None, 2: anode, 3: cathode, 4: None, 5: 'ACT_GND', 6: output, 7: 'ACT_5V2', 8: 'ACT_5V2'}, xy,
         {1: 'NC1', 2: 'ANODE', 3: 'CATHODE', 4: 'NC4', 5: 'GND', 6: 'OUT', 7: 'ENABLE', 8: 'VCC'},
         {5: 'power_in', 6: 'open_collector', 7: 'input', 8: 'power_in'}, '6N137',
         'Vishay DIP8, direct solder. No copper across optical gap. Actual pullup/load and input-current timing conditions require verification.')
part('U4', 'SN74HCT02N', 'DIP-14_W7.62mm_LongPads',
     {1: 'PWM_RUN', 2: 'PWM_N', 3: 'RUN_N', 4: None, 5: 'ACT_GND', 6: 'ACT_GND', 7: 'ACT_GND',
      8: 'ACT_GND', 9: 'ACT_GND', 10: None, 11: 'ACT_GND', 12: 'ACT_GND', 13: None, 14: 'ACT_5V2'}, (51, 30),
     {1: '1Y', 2: '1A', 3: '1B', 4: '2Y_NC', 5: '2A', 6: '2B', 7: 'GND', 8: '3A', 9: '3B',
      10: '3Y_NC', 11: '4A', 12: '4B', 13: '4Y_NC', 14: 'VCC'},
     {1: 'output', 2: 'input', 3: 'input', 4: 'output', 5: 'input', 6: 'input', 7: 'power_in',
      8: 'input', 9: 'input', 10: 'output', 11: 'input', 12: 'input', 13: 'output', 14: 'power_in'},
     'SN74HCT02N', 'Ordinary TTL NOR accepts opto VOL0.6V under its0.8V VIL. NOR(PWM_N,RUN_N) is high only when both input LEDs are lit. Unused inputs grounded.')
part('U1', 'UCC27524P', 'DIP-8_W7.62mm_LongPads',
     {1: 'ENA', 2: 'INA', 3: 'ACT_GND', 4: 'ACT_GND', 5: None, 6: 'ACT_5V2', 7: 'DRIVE', 8: 'ACT_GND'}, (68, 38),
     {1: 'ENA', 2: 'INA', 3: 'GND', 4: 'INB', 5: 'OUTB_NC', 6: 'VDD', 7: 'OUTA', 8: 'ENB'},
     {1: 'input', 2: 'input', 3: 'power_in', 4: 'input', 5: 'output', 6: 'power_in', 7: 'output', 8: 'input'},
     'UCC27524P.B', 'Direct PDIP8, no socket. Exact procured P/P.B electrical guarantee remains a release item. Local supervisor gates ENA independently of logic.')
part('U5', 'MCP100-485DI/TO', 'TO-92_Inline_Wide', {1: 'LOCAL_OK', 2: 'ACT_5V2', 3: 'ACT_GND'}, (68, 21),
     {1: 'RESET_N / D BONDOUT', 2: 'VDD', 3: 'VSS'}, {1: 'output', 2: 'power_in', 3: 'power_in'},
     'MCP100-485DI/TO', 'D-bondout only. Static trip4.60-4.85V; assertion10us is typical without a maximum. No hard brownout-latency claim.')
part('U6', 'LM317AT/NOPB', 'TO-220-3_Vertical', {1: 'ADJ', 2: 'ACT_5V2', 3: 'ACT_12V'}, (71, 58),
     {1: 'ADJ', 2: 'OUT / LIVE TAB', 3: 'IN'}, {1: 'input', 2: 'power_out', 3: 'power_in'},
     'LM317AT/NOPB', '120/374ohm1% divider: DC4.967-5.346V, >=10mA minimum load, >=3V headroom at9V input. Tab is output, not ground. No rail transient/thermal qualification.')
part('D1', 'SB5H100-E3', 'D_DO-201AD_P15.24mm_Horizontal', {1: 'ACT_12V', 2: 'IAC_LS'}, (70, 15),
     {1: 'K / BAND', 2: 'A'}, mpn='SB5H100-E3/54', note='Flyback cathode at valve+, anode at drain. Close coil/diode loop; current decays after cut.')
part('D2', '1N4007', 'D_DO-41_SOD81_P10.16mm_Horizontal', {1: 'ACT_12V', 2: 'ACT_5V2'}, (72, 65),
     {1: 'K / BAND', 2: 'A'}, mpn='1N4007-E3/54', note='LM317 output-discharge protection: A atOUT, K atIN. Does not provide input reverse-battery protection.')
for ref, base, xy in [('D3', 'PWM_BASE', (26.5, 31.5)), ('D4', 'RUN_BASE', (28, 62))]:
    part(ref, '1N4148', 'D_DO-35_SOD27_P3.81mm_Vertical_AnodeUp', {1: base, 2: 'CARRIER_GND'}, xy,
         {1: 'K / BAND', 2: 'A'}, mpn='1N4148-TAP', note='Input transistor reverse BE clamp only; not an isolation bridge.')
for ref, value, a, b, xy, note in [
        ('R1', '1k 1%', 'IDLE_CMD', 'PWM_BASE', (15, 35), 'GPIO buffer base; loaded GPIO voltage unmeasured'),
        ('R2', '1k8 1%', 'RUN_5V', 'RUN_BASE', (15, 52), 'RUN base load stays within source budget conditionally'),
        ('R3', '357R 1%', 'CARRIER_5V', 'PWM_LED_A', (27, 21), 'LED current conditional7.63-14.85mA'),
        ('R4', '357R 1%', 'CARRIER_5V', 'RUN_LED_A', (27, 45), 'LED current conditional7.63-14.85mA'),
        ('R5', '100k', 'PWM_BASE', 'CARRIER_GND', (21, 44), 'Base-emitter off bias'),
        ('R6', '100k', 'RUN_BASE', 'CARRIER_GND', (21, 61), 'Base-emitter off bias'),
        ('R7', '1k', 'ACT_5V2', 'PWM_N', (45, 22), 'Opto pullup; timing load condition must match'),
        ('R8', '1k', 'ACT_5V2', 'RUN_N', (45, 46), 'Opto pullup; timing load condition must match'),
        ('R9', '1k', 'PWM_RUN', 'INA', (62, 36), 'Logic-to-driver input series'),
        ('R10', '10k', 'INA', 'ACT_GND', (62, 43), 'Driver input off bias'),
        ('R11', '1k', 'LOCAL_OK', 'ENA', (63, 28), 'Independent local supervisor enable'),
        ('R12', '4k7', 'ENA', 'ACT_GND', (63, 33), 'Mandatory enable off bias overrides internal pullup'),
        ('R13', '33R', 'DRIVE', 'GATE', (81, 37), 'MOS gate damping; actual switching remains unmeasured'),
        ('R14', '10k', 'GATE', 'ACT_GND', (84.5, 48), 'Local gate-source off bias'),
        ('R15', '120R 1%', 'ACT_5V2', 'ADJ', (66, 51), 'Regulator minimum load and divider high arm'),
        ('R16', '374R 1%', 'ADJ', 'ACT_GND', (61, 57), 'Regulator divider low arm')]:
    part(ref, value, RFP, {1: a, 2: b}, xy, note=note + '; exact leaded passive part/temperature rating pending')
for ref, rail, xy in [('C1', 'ACT_5V2', (43, 17)), ('C2', 'ACT_5V2', (43, 40)),
                       ('C3', 'ACT_5V2', (58, 24)), ('C4', 'ACT_5V2', (78.5, 44)),
                       ('C5', 'ACT_5V2', (72, 28)), ('C8', 'ACT_12V', (80, 53)),
                       ('C9', 'CARRIER_5V', (22, 15))]:
    part(ref, '100nF 50V', CFP, {1: rail, 2: 'CARRIER_GND' if ref == 'C9' else 'ACT_GND'}, xy,
         note='Local leaded decoupler; exact part, lead spacing, rail transients and placement acceptance pending')
part('C6', '100uF 50V', 'CP_Radial_D8.0mm_P3.50mm', {1: 'ACT_12V', 2: 'ACT_GND'}, (91, 46.5),
     {1: 'PLUS', 2: 'MINUS'}, note='Input reservoir; exact D8/P3.5 leaded part, ripple/thermal and interruption response pending')
part('C7', '22uF 16V', 'CP_Radial_D8.0mm_P3.50mm', {1: 'ACT_5V2', 2: 'ACT_GND'}, (61, 64),
     {1: 'PLUS', 2: 'MINUS'}, note='LM317 local output reservoir, no generic old-LDO ESR-window claim; exact leaded part/fit and transient behavior pending')
for i, xy in enumerate([(14, 14), (96, 14), (14, 66), (96, 66)], 1):
    part('H' + str(i), 'M3 ISOLATED MOUNT', 'MountingHole_3.2mm_M3', {}, xy,
         note='Unplated mount. Insulating spacers/hardware must not bridge carrier/actuator ground or live TO220 tabs. Case fit unmeasured.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace-generated', action='store_true')
    args = parser.parse_args()
    if (OUT / 'isolated.kicad_pcb').exists() and not args.replace_generated:
        raise SystemExit('Draft exists. Inspect edits before --replace-generated.')
    lib = OUT / 'lib'
    footprints = lib / 'ecu.pretty'
    footprints.mkdir(parents=True, exist_ok=True)
    origins = {}
    for stem in sorted({p.footprint.split(':')[1] for p in PARTS}):
        source = ROOT / 'hardware/a4-n16r8/lib/ecu.pretty' / (stem + '.kicad_mod')
        if not source.exists():
            source = ROOT / 'hardware/idle-accessory/lib/ecu.pretty' / (stem + '.kicad_mod')
        if source.exists():
            original = source.read_bytes()
            data, removed = footprint_copy(original)
            (footprints / source.name).write_bytes(data)
            origins[stem] = dict(source=str(source.relative_to(ROOT)), source_sha256=hashlib.sha256(original).hexdigest(),
                                 copy_sha256=hashlib.sha256(data).hexdigest(), omitted_metadata=removed)
        else:
            entry = json.loads((OUT / 'new-footprints.json').read_text())[stem]
            source = footprints / (stem + '.kicad_mod')
            assert hashlib.sha256(source.read_bytes()).hexdigest() == entry['sha256']
            origins[stem] = entry
    shutil.copyfile(ROOT / 'hardware/idle-accessory/lib/NOTICE.md', lib / 'NOTICE.md')
    builder.OUT, builder.LIB, builder.PARTS = OUT, lib, PARTS
    builder.NOTES = {'isolated': 'IAC-DRAFT2 / PHYSICAL OUTPUT DISABLED / HOLD. Optical input domain, separate actuator rail/ground. No safety-isolation, valve, engine or enclosure qualification.'}
    builder.write_sheet('isolated')
    sheet = OUT / 'isolated.kicad_sch'
    text = sheet.read_text().replace('ESP32 ECU A0 / isolated', 'Isolated idle driver IAC-DRAFT2')
    text = text.replace('2026-10-30', '2026-11-04').replace('A0 BENCH', 'IAC-DRAFT2')
    text = text.replace('/' + builder.uid('root') + '/' + builder.uid('isolated'), '/' + builder.uid('isolated'))
    sheet.write_text(text[:-1] + '(sheet_instances (path "/" (page "1"))))')
    (lib / 'ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "esp32_ecu_isolated")\n' +
                                      '\n'.join(builder.symbol(p)[0] for p in PARTS if p.pins) + ')')
    for kind, filetype in [('fp', 'KiCad'), ('sym', 'KiCad')]:
        uri = '${KIPRJMOD}/lib/' + ('ecu.pretty' if kind == 'fp' else 'ecu.kicad_sym')
        (OUT / (kind + '-lib-table')).write_text(f'({kind}_lib_table (version 7) (lib (name "ECU") (type "{filetype}") (uri "{uri}") (options "") (descr "Reviewed leaded copies")))')
    board = pcb.BOARD()
    board.SetCopperLayerCount(2)
    board.GetDesignSettings().SetBoardThickness(pcb.FromMM(1.6))
    nets = {}
    for net in sorted({v if v is not None else builder.nc_net(p, k) for p in PARTS for k, v in p.pins.items()}):
        nets[net] = pcb.NETINFO_ITEM(board, net)
        board.Add(nets[net])
    for item in PARTS:
        fp = pcb.FootprintLoad(str(footprints), item.footprint.split(':')[1])
        assert fp is not None, item.footprint
        fp.SetReference(item.ref)
        fp.SetValue(item.value)
        fp.SetFPID(pcb.LIB_ID('ECU', item.footprint.split(':')[1]))
        fp.SetPath(pcb.KIID_PATH('/' + builder.uid('isolated') + '/' + builder.uid(item.ref)))
        fp.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(v) for v in item.xy)))
        fp.SetOrientationDegrees(item.angle)
        fp.Reference().SetLayer(pcb.F_Fab)
        fp.Value().SetVisible(False)
        if item.ref.startswith('H'):
            fp.SetAttributes(fp.GetAttributes() | pcb.FP_BOARD_ONLY)
        for pad in fp.Pads():
            key = pad.GetNumber()
            if key:
                assert key in item.pins
                pad.SetNet(nets[item.pins[key] if item.pins[key] is not None else builder.nc_net(item, key)])
        board.Add(fp)
    for a, z in [((10, 10), (100, 10)), ((100, 10), (100, 70)), ((100, 70), (10, 70)), ((10, 70), (10, 10))]:
        line = pcb.PCB_SHAPE()
        line.SetShape(pcb.SHAPE_T_SEGMENT)
        line.SetStart(pcb.VECTOR2I(*(pcb.FromMM(v) for v in a)))
        line.SetEnd(pcb.VECTOR2I(*(pcb.FromMM(v) for v in z)))
        line.SetLayer(pcb.Edge_Cuts)
        line.SetWidth(pcb.FromMM(.05))
        board.Add(line)
    gap = pcb.ZONE(board)
    gap.SetIsRuleArea(True)
    gap.SetLayerSet(pcb.LSET.AllCuMask())
    gap.SetDoNotAllowTracks(True)
    gap.SetDoNotAllowVias(True)
    gap.SetDoNotAllowCopperPour(True)
    gap.Outline().NewOutline()
    for x, y in [(35.3, 10), (40.3, 10), (40.3, 70), (35.3, 70)]:
        gap.Outline().Append(pcb.FromMM(x), pcb.FromMM(y))
    board.Add(gap)
    for text, xy in [('IAC-DRAFT2 / HOLD', (55, 11.5)), ('CARRIER', (23, 11.5)), ('ACTUATOR', (56, 68.5))]:
        label = pcb.PCB_TEXT(board)
        label.SetText(text)
        label.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(v) for v in xy)))
        label.SetTextSize(pcb.VECTOR2I(pcb.FromMM(1), pcb.FromMM(1)))
        label.SetTextThickness(pcb.FromMM(.15))
        label.SetLayer(pcb.F_SilkS)
        board.Add(label)
    pcb.SaveBoard(str(OUT / 'isolated.kicad_pcb'), board)
    project = dict(meta=dict(filename='isolated.kicad_pro', version=1),
                   board=dict(design_settings=dict(rules=dict(min_clearance=.3, min_track_width=.3, min_copper_edge_clearance=.5))))
    (OUT / 'isolated.kicad_pro').write_text(json.dumps(project, indent=2) + '\n')
    contract = dict(revision='IAC-DRAFT2', status='PLACEMENT_NETLIST_HOLD_NOT_FOR_FABRICATION', board_mm=[90, 60],
                    copper_layers=2, physical_default=False, isolation_gap_mm=5,
                    domains={'carrier': ['CARRIER_5V', 'CARRIER_GND', 'IDLE_CMD', 'RUN_5V'],
                             'actuator': ['ACT_12V', 'ACT_GND', 'ACT_5V2', 'IAC_LS']},
                    minimum_physical_pulse_us=None, physical_qualification=False,
                    parts=[dict(reference=p.ref, value=p.value, footprint=p.footprint, pins=p.pins,
                                pin_names=p.names, pin_types=p.types, mpn=p.mpn, note=p.note,
                                placed_xy_mm=p.xy, placed_angle_deg=p.angle) for p in PARTS])
    (OUT / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    (OUT / 'footprint-provenance.json').write_text(json.dumps(origins, indent=2) + '\n')
    with (OUT / 'bom.csv').open('w', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['Reference', 'Value', 'MPN candidate', 'Footprint', 'Qualification / procurement'])
        writer.writerows((p.ref, p.value, p.mpn, p.footprint, p.note) for p in PARTS)
    print('Created separate IAC-DRAFT2 placement/netlist; routing and qualification remain pending')


if __name__ == '__main__':
    main()
