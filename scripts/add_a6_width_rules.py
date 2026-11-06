#!/usr/bin/env python3
"""Add or verify explicit A6 width rules on a fresh native project copy.

Netclass defaults aid editing; custom rules enforce geometric floors. The
INJ1 0.8mm exception needs the separate UUID/geometry audit. No current rating.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import pcbnew as p
from audit_a6_copper import POWER, SUPPLY, NECKS, audit
from finish_a6_routes import copy_native, native_drc, drc_summary, pad_state


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rule(name, nets, minimum):
    condition = ' || '.join("A.NetName == '%s'" % n for n in sorted(nets))
    return '(rule %s\n  (condition %s)\n  (constraint track_width (min %smm)))\n' % (
        json.dumps(name), json.dumps(condition), minimum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-existing', action='store_true',
                        help='Keep an exact existing rule set and rerun its native negative controls.')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    source_files = {name: Path(__file__).with_name(name).read_bytes() for name in (
        'add_a6_width_rules.py', 'audit_a6_copper.py', 'finish_a6_routes.py')}
    assert source != out and source not in out.parents
    assert json.loads((source / 'net_contract.json').read_text())['revision'] == 'A6-FLEX-RGB-HOLD'
    before_pcb = sha(source / 'esp32-ecu.kicad_pcb')
    before_pro = sha(source / 'esp32-ecu.kicad_pro')
    copy_native(source, out)
    snapshots = out / 'width-rule-sources'
    snapshots.mkdir(exist_ok=False)
    for name, content in source_files.items():
        (snapshots / name).write_bytes(content)
    project_path = out / 'esp32-ecu.kicad_pro'
    project = json.loads(project_path.read_text())
    classes = project['net_settings']['classes']
    patterns = [
        dict(netclass=name, pattern=net) for name, nets in (('Power', POWER), ('Supply', SUPPLY))
        for net in sorted(nets)]
    rules = '(version 1)\n\n# Geometry policy only; current/thermal/fuse acceptance is open.\n'
    rules += rule('A6 supply minimum', SUPPLY, '0.5') + '\n'
    rules += rule('A6 power minimum', POWER - {'INJ1_LS'}, '1.0') + '\n'
    rules += '# Exact three-segment INJ1 exception additionally bound by audit_a6_copper.py.\n'
    rules += rule('A6 INJ1 lower floor with audited local neck', {'INJ1_LS'}, '0.8')
    rule_path = out / 'esp32-ecu.kicad_dru'
    if args.verify_existing:
        assert rule_path.read_text() == rules, 'Existing rules differ from the declared policy'
        assert len(classes) == 3 and {c['name']: c['track_width'] for c in classes} == {
            'Default': .25, 'Power': 1., 'Supply': .5}
        assert project['net_settings']['netclass_patterns'] == patterns
        assert project['board']['design_settings']['rules']['min_track_width'] == .25
        assert sha(project_path) == before_pro
    else:
        assert not rule_path.exists(), 'Do not replace pre-existing rules'
        assert len(classes) == 1 and classes[0]['name'] == 'Default'
        default = classes[0]
        default['track_width'] = .25
        for priority, (name, width) in enumerate((('Power', 1.), ('Supply', .5))):
            value = copy.deepcopy(default)
            value.update(name=name, track_width=width, priority=priority)
            classes.append(value)
        assert not project['net_settings'].get('netclass_patterns')
        project['net_settings']['netclass_patterns'] = patterns
        project['board']['design_settings']['rules']['min_track_width'] = .25
        project_path.write_text(json.dumps(project, indent=2) + '\n')
        rule_path.write_text(rules)
    assert sha(out / 'esp32-ecu.kicad_pcb') == before_pcb
    result = audit(p.LoadBoard(str(out / 'esp32-ecu.kicad_pcb')))
    result.update(board_sha256=before_pcb,
                  script_sha256=sha(Path(__file__).with_name('audit_a6_copper.py')))
    (out / 'copper-width-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    drc = native_drc(out)
    summary = drc_summary(drc)
    # The CLI can report zero when a custom-rule file fails to compile. Prove
    # these rules execute by narrowing actual tracks on fresh invalid copies.
    controls = []
    for name, net, initial, narrow, native_reject in (
            ('supply', '+5V', 500000, 250000, True),
            ('power', 'VIN_PROT', 1000000, 800000, True),
            ('extra-INJ1-neck', 'INJ1_LS', 1000000, 800000, False)):
        folder = out / 'rule-controls' / name
        copy_native(source, folder)
        shutil.copyfile(project_path, folder / project_path.name)
        shutil.copyfile(rule_path, folder / rule_path.name)
        board = p.LoadBoard(str(folder / 'esp32-ecu.kicad_pcb'))
        original_pads = pad_state(board)
        track = next(t for t in board.GetTracks() if not isinstance(t, p.PCB_VIA)
                     and t.GetNetname() == net and t.GetWidth() == initial)
        uid = track.m_Uuid.AsString()
        assert uid not in NECKS
        track.SetWidth(narrow)
        assert pad_state(board) == original_pads
        p.ZONE_FILLER(board).Fill(board.Zones())
        p.SaveBoard(str(folder / 'esp32-ecu.kicad_pcb'), board)
        control_drc = native_drc(folder)
        hits = [v for v in control_drc['violations'] if v['type'] == 'track_width'
                and any(i['uuid'] == uid for i in v['items'])]
        control_audit = audit(board)
        explicit_hits = [v for v in control_audit['findings'] if v.get('uuid') == uid]
        controls.append(dict(name=name, target_uuid=uid, net=net,
            initial_width_nm=initial, narrowed_width_nm=narrow,
            native_width_rejected=bool(hits), expected_native_width_rejection=native_reject,
            explicit_audit_rejected=bool(explicit_hits),
            native=drc_summary(control_drc),
            board_sha256=sha(folder / 'esp32-ecu.kicad_pcb'),
            passed=(bool(hits) == native_reject and bool(explicit_hits)
                    and not control_audit['passed'])))
    proof = dict(source=str(source), source_pcb_sha256=before_pcb,
        source_project_sha256=before_pro, output_pcb_sha256=sha(out / 'esp32-ecu.kicad_pcb'),
        output_project_sha256=sha(project_path), rules_sha256=sha(rule_path),
        script_sha256=sha(Path(__file__)), audit_script_sha256=sha(Path(__file__).with_name('audit_a6_copper.py')),
        PCB_bytes_unchanged=True, width_audit_passed=result['passed'], native=summary,
        existing_project_and_rules_verified_unchanged=args.verify_existing,
        active_native_rule_controls=controls,
        source_snapshots_sha256={name: hashlib.sha256(content).hexdigest()
                                 for name, content in source_files.items()},
        passed=(result['passed'] and summary == dict(unconnected=0, dangling=0, physical=[], parity=0)
                and all(row['passed'] for row in controls)),
        scope=__doc__, manufacturing_release=False)
    (out / 'width-rule-update.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert sha(source / 'esp32-ecu.kicad_pcb') == before_pcb
    assert sha(source / 'esp32-ecu.kicad_pro') == before_pro
    print(json.dumps(proof), flush=True)
    if not proof['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
