#!/usr/bin/env python3
"""Conditional RGB DC experiments using explicit authored ngspice equivalents.

The LED and BJT equivalents, port impedance/leakage and source resistance are
assumptions, not manufacturer models or measured limits. Fault paths and the
added series-resistor bound are assessed separately from light, temperature,
reset timing, target readback, rail, enclosure and physical qualification.
"""

import argparse
import hashlib
import itertools
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COLORS = ('red', 'green', 'blue')
NODES = {
    '+5V': 'rail5', '+3V3': 'rail33', 'GND': '0', 'LED_5V': 'led5',
    **{f'LED_{c.upper()}_{suffix}': f'{c}_{short}'
       for c in COLORS for suffix, short in [('B', 'base'), ('COL', 'col'), ('K', 'k')]},
    **{f'LED_GP{n}': f'{c}_gp' for n, c in enumerate(COLORS)},
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Case:
    name: str
    mask: int = 2
    rail5: float = 5.0
    rail33: float = 3.3
    resistor_scale: float = 1.0
    forward_profile: str = 'typical_25C'
    port_ohm: float = 100
    connected5: bool = True
    connected33: bool = True
    fault: str = ''
    guard_scale: float = 1.0
    injected_cb_leak_ua: float = 0
    rail_bleeder_ohm: float = 100


def binding(profile):
    parts = {p['ref']: p for p in profile['parts']}
    assert len(parts) == len(profile['parts']), 'Duplicate component references'
    assert profile['contract'] in ('RGB-MCP21-DRAFT2', 'RGB-MCP21-DRAFT3', 'RGB-MCP21-DRAFT4')
    guarded = profile['contract'] != 'RGB-MCP21-DRAFT2'
    expected = {
        'U19': {'1': 'LED_SCL', '2': 'LED_SDA', '3': 'GND', '4': 'GND', '5': '+3V3',
                '6': 'LED_RESET_N', '7': None, '8': None, '9': 'GND',
                '10': 'LED_GP0', '11': 'LED_GP1', '12': 'LED_GP2',
                '13': None, '14': None, '15': None, '16': None, '17': None, '18': '+3V3'},
        'U20': {'1': 'LED_RESET_N', '2': '+3V3', '3': 'GND'},
        'J23': {'1': 'LED_5V' if guarded else '+5V', '2': 'LED_RED_K',
                '3': 'LED_GREEN_K', '4': 'LED_BLUE_K', '5': None},
        'R176': {'1': 'I2C_SDA', '2': 'LED_SDA'},
        'R177': {'1': 'I2C_SCL', '2': 'LED_SCL'},
        'R178': {'1': '+3V3', '2': 'LED_RESET_N'},
        **{f'C{n}': {'1': '+3V3', '2': 'GND'} for n in (161, 162, 163)},
    }
    resistors = {'R176': 100, 'R177': 100, 'R178': 100000}
    for n, c in enumerate(COLORS):
        upper = c.upper()
        expected[f'Q{8+n}'] = {'1': 'GND', '2': f'LED_{upper}_B', '3': f'LED_{upper}_COL'}
        expected[f'R{167+2*n}'] = {'1': f'LED_GP{n}', '2': f'LED_{upper}_B'}
        expected[f'R{168+2*n}'] = {'1': f'LED_{upper}_B', '2': 'GND'}
        expected[f'R{173+n}'] = {'1': f'LED_{upper}_K', '2': f'LED_{upper}_COL'}
        resistors.update({f'R{167+2*n}': 2200, f'R{168+2*n}': 100000,
                          f'R{173+n}': 680 if n == 0 else 470})
    if guarded:
        expected['R179'] = {'1': '+5V', '2': 'LED_5V'}
        resistors['R179'] = 330
    assert parts.keys() == expected.keys(), 'Unreviewed component/reference set'
    for ref, pins in expected.items():
        assert parts[ref]['pins'] == pins, ('Unreviewed pin path', ref)
    for ref, resistance in resistors.items():
        part = parts[ref]
        power = '4' if ref == 'R179' and profile['contract'] == 'RGB-MCP21-DRAFT4' else '6'
        value = re.fullmatch(r'(\d+(?:\.\d+)?)R 1% 0\.' + power + r'W', part['value'])
        assert value is not None and float(value[1]) == resistance == part['ohm'], ref
        assert part['mpn'] == '', ('Resistor MPN not reviewed', ref)
    for ref, value in [('U19', 'MCP23008-E/P'), ('U20', 'MCP121-270E/TO'),
                       ('Q8', '2N3904BU'), ('Q9', '2N3904BU'), ('Q10', '2N3904BU')]:
        assert parts[ref]['value'] == parts[ref]['mpn'] == value, ref
    assert parts['J23']['value'] == 'ORDINARY RGB LED PH5'
    assert parts['J23']['mpn'] == 'B5B-PH-K-S(LF)(SN)'
    for ref, value, farad in [('C161', '100nF 50V candidate', 1e-7),
                              ('C162', '100nF 50V candidate', 1e-7),
                              ('C163', '10uF 16V radial candidate', 1e-5)]:
        assert parts[ref]['value'] == value and parts[ref]['farad'] == farad, ref
        assert parts[ref]['mpn'] == '', ref
    assert profile['address'] == 0x21 and profile['GP_high_is_on'] is True and profile['unused_gpio_low'] is True
    assert profile['shared_bus_clock_hz'] == 100000 and not profile['extra_bus_pullups']
    assert profile['electrical_scope']['normal_3v3_rail_v'] == [3.0, 3.6]
    assert profile['external_led']['mpn'] == 'WP154A4SEJ3VBDZGW/CA'
    assert profile['external_led']['configuration'] == 'common_anode'
    assert profile['external_led']['pins'] == {'1': 'red_cathode', '2': 'common_anode',
                                              '3': 'blue_cathode', '4': 'green_cathode'}
    assert profile['external_led']['J23_to_led_pin'] == {'1': '2', '2': '1', '3': '4', '4': '3', '5': None}
    guard = parts.get('R179')
    if guard is None:
        assert parts['J23']['pins']['1'] == '+5V'
    else:
        assert guard['pins'] == {'1': '+5V', '2': 'LED_5V'}
        assert guard['ohm'] == 330
        assert parts['J23']['pins']['1'] == 'LED_5V'
        # There must be no second supply path around the common resistor.
        users = {(p['ref'], pin) for p in parts.values() for pin, net in p['pins'].items()
                 if net == 'LED_5V'}
        assert users == {('R179', '2'), ('J23', '1')}, users
    assert parts['J23']['pins']['5'] is None
    assert profile['engine_outputs_enabled'] is False
    return parts, guarded


def deck(case, parts, guarded):
    anode = 'led5' if guarded else 'rail5'
    vf = (2.2, 3.3, 3.3) if case.forward_profile == 'typical_25C' else (2.8, 4.1, 4.0)
    lines = [case.name + ' - authored conditional RGB equivalents',
             '* No manufacturer BJT, expander, LED, regulator or thermal model.',
             '.temp 25',
             f'V5 source5 0 {case.rail5}',
             f'Rsupply source5 rail5 {1 if case.connected5 else 1e12}',
             '* One-ohm Thevenin source is an assumption, not the carrier buck.',
             f'V33 source33 0 {case.rail33}',
             f'R33 source33 rail33 {0.1 if case.connected33 else 1e12}',
             f'Rbleed rail33 0 {case.rail_bleeder_ohm}',
             '.model QEQ NPN(IS=1e-14 BF=50 VAF=50 RB=10 RC=2 RE=1 CJE=5p CJC=4p)',
             '.model DPORT D(IS=1e-12 N=1 RS=10 CJO=5p)']
    selected = {f'R{n}' for n in range(167, 176)} | ({'R179'} if guarded else set())
    for ref in sorted(selected):
        part = parts[ref]
        value = part['ohm'] * case.resistor_scale
        if ref == 'R179':
            value *= case.guard_scale
        a, b = (NODES[part['pins'][pin]] for pin in ('1', '2'))
        lines.append(f'{ref} {a} {b} {value:.12g}')
    for n, c in enumerate(COLORS):
        high = bool(case.mask & (1 << n))
        source = 'rail33' if high and case.connected33 else '0'
        lines += [f'Rport_{c} {source} {c}_gp {case.port_ohm if case.connected33 else 1e12}',
                  f'Dhi_{c} {c}_gp rail33 DPORT', f'Dlo_{c} 0 {c}_gp DPORT',
                  f'Q{8+n} {c}_col {c}_base 0 QEQ',
                  '* Synthetic5ohm slope; knee chosen to meet the stated20mA point.',
                  f'Bled_{c} {anode} {c}_k I=max((v({anode},{c}_k)-{vf[n]-.1:.12g})/5,0)']
        if case.injected_cb_leak_ua:
            lines.append(f'Ileak_{c} {c}_col {c}_base {case.injected_cb_leak_ua}u')
    if case.fault:
        node = anode if case.fault == 'anode-ground' else case.fault.removesuffix('-ground') + '_k'
        lines.append(f'Rfault {node} 0 0.001')
    expressions = ['v(rail5)', 'v(rail33)', f'v({anode})']
    expressions += [f'v({c}_gp)' for c in COLORS]
    expressions += [f'v({c}_base)' for c in COLORS]
    expressions += [f'v({c}_col)' for c in COLORS]
    expressions += [f'v({c}_k)' for c in COLORS]
    expressions += ['i(V5)', 'i(V33)']
    lines += ['.control', 'set wr_singlescale', 'set wr_vecnames', 'op',
              'wrdata values.txt ' + ' '.join(expressions), 'quit', '.endc', '.end', '']
    return '\n'.join(lines)


def run(case, parts, guarded, binary, output):
    folder = output / case.name
    folder.mkdir()
    (folder / 'circuit.cir').write_text(deck(case, parts, guarded))
    process = subprocess.run([str(binary), '-n', '-b', 'circuit.cir'], cwd=folder,
                             env={**os.environ, 'SPICE_SCRIPTS': str(output / 'startup')},
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, timeout=30)
    (folder / 'ngspice.log').write_text(process.stdout)
    assert process.returncode == 0 and (folder / 'values.txt').is_file(), case.name
    lines = (folder / 'values.txt').read_text().splitlines()
    values = [float(v) for v in lines[-1].split()][1:]
    assert len(values) == 17, (case.name, values)
    rail5, rail33, anode = values[:3]
    gp, base, collector, cathode = (values[start:start+3] for start in (3, 6, 9, 12))
    forward = (2.2, 3.3, 3.3) if case.forward_profile == 'typical_25C' else (2.8, 4.1, 4.0)
    led_ma = [max((anode-(point-.1)-drop)/5, 0)*1000 for point, drop in zip(forward, cathode)]
    readback = [None if not case.connected33 or rail33 < 1 else
                1 if level >= .8*rail33 else 0 if level <= .2*rail33 else None for level in gp]
    guard_ohm = parts['R179']['ohm']*case.resistor_scale*case.guard_scale if guarded else None
    guard_ma = (rail5-anode)/guard_ohm*1000 if guarded else None
    guard_w = (rail5-anode)**2/guard_ohm if guarded else None
    return dict(case=asdict(case), rail5_v=rail5, rail33_v=rail33, anode_v=anode,
                gp_v=gp, base_v=base, collector_v=collector, cathode_v=cathode,
                synthetic_led_current_ma=led_ma, conditional_digital_readback=readback,
                guard_current_ma=guard_ma, guard_dissipation_w=guard_w,
                source5_current_ma=-values[15]*1000,
                source33_current_ma=-values[16]*1000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status', type=Path, default=ROOT / 'hardware/flex-input/status-led.json')
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def unique_object(pairs):
        result = dict(pairs)
        assert len(result) == len(pairs), 'Duplicate JSON object keys'
        return result
    profile = json.loads(args.status.read_text(), object_pairs_hook=unique_object)
    parts, guarded = binding(profile)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'startup').mkdir()
    (output / 'startup/spinit').write_text('* Owned empty startup. User spiceinit disabled with-n.\n')
    source_paths = [args.status.resolve(), Path(__file__).resolve()]
    hashes = {str(p): sha(p) for p in source_paths}
    for number, path in enumerate(source_paths):
        (output / f'source-{number}-{path.name}').write_bytes(path.read_bytes())
    cases = []
    for mask, v33, v5, forward in itertools.product((1, 2, 4), (3.0, 3.6), (4.75, 5.25),
                                                   ('typical_25C', 'max_25C')):
        cases.append(Case(f'normal-{len(cases):02d}', mask=mask, rail33=v33, rail5=v5,
                          forward_profile=forward))
    cases += [Case('off', mask=0), Case('all-colors', mask=7)]
    for fault, scale in itertools.product(('anode-ground', 'red-ground', 'green-ground', 'blue-ground'), (.99, 1.01)):
        cases.append(Case(f'{fault}-{scale}', mask=0, rail5=5.25,
                          resistor_scale=scale, fault=fault))
    for mask in (1, 2, 4):
        cases.append(Case(f'weak-port-{mask}', mask=mask, rail33=3.0, port_ohm=1750))
    for on5, on33, leak in itertools.product((False, True), (False, True), (0, 50)):
        cases.append(Case(f'partial-{int(on5)}-{int(on33)}-{leak}', mask=2,
                          connected5=on5, connected33=on33, injected_cb_leak_ua=leak))
    for leak in (0, 50):
        cases.append(Case(f'partial-open-bleed-{leak}', connected33=False,
                          injected_cb_leak_ua=leak, rail_bleeder_ohm=1e12))
    if guarded:
        cases += [Case('guard-open', guard_scale=1e10),
                  Case('guard-shorted-negative', mask=0, guard_scale=1e-5, fault='green-ground')]
    results = [run(c, parts, guarded, args.ngspice.resolve(), output) for c in cases]
    rejected_legacy = not guarded
    if guarded:
        for result in results:
            case = result['case']
            if case['guard_scale'] == 1:
                bound = case['rail5'] / (parts['R179']['ohm']*case['resistor_scale'])*1000
                assert result['guard_current_ma'] <= bound + 1e-3, result
        normal = [r for r in results if r['case']['name'].startswith('normal-')]
        assert all(r['conditional_digital_readback'] == [(r['case']['mask'] >> n) & 1 for n in range(3)] for r in normal)
        for result in normal + [r for r in results if r['case']['name'] == 'all-colors']:
            case = result['case']
            expected = result['rail33_v']/case['rail_bleeder_ohm']*1000
            expected += sum((result['rail33_v']-gp)/case['port_ohm']*1000
                            for n, gp in enumerate(result['gp_v']) if case['mask'] & (1 << n))
            assert abs(result['source33_current_ma']-expected) < .0001, ('3V3 KCL', result)
            assert sum(result['synthetic_led_current_ma']) <= result['guard_current_ma'] + .001
        weak = [r for r in results if r['case']['name'].startswith('weak-port-')]
        assert any(None in r['conditional_digital_readback'] for r in weak), 'Port-impedance sensitivity witness lost'
        assert max(next(r for r in results if r['case']['name'] == 'guard-open')['synthetic_led_current_ma']) < .001
        short = next(r for r in results if r['case']['name'] == 'guard-shorted-negative')
        assert max(short['synthetic_led_current_ma']) > 25, 'Negative control did not expose lost series bound'
    report = dict(contract=profile['contract'], guarded_supply=guarded,
                  passed=guarded, legacy_topology_intentionally_rejected=rejected_legacy,
                  source_sha256=hashes, ngspice_sha256=sha(args.ngspice), cases=results,
                  ngspice_arguments=['-n', '-b', 'circuit.cir'],
                  startup_file_sha256=sha(output / 'startup/spinit'),
                  startup_environment={'SPICE_SCRIPTS': str(output / 'startup')},
                  minimum_1percent_guard_ohm=parts['R179']['ohm']*.99 if guarded else None,
                  zero_drop_current_bound_ma=5.25/(parts['R179']['ohm']*.99)*1000 if guarded else None,
                  zero_drop_guard_power_bound_w=5.25**2/(parts['R179']['ohm']*.99) if guarded else None,
                  qualification=__doc__, manufacturer_model=False, physical_qualification=False,
                  graph_binding='Exact reviewed part/reference/pin/value set; unexpected paths are rejected',
                  unmodelled_functions=['MCP23008 internal implementation and state',
                                       'MCP121 reset timing/threshold/leakage',
                                       'I2C transactions and R176/R177 signal integrity',
                                       'C161/C162/C163 transient supply/decoupling behavior',
                                       'Carrier regulator and full MCU/radio load'],
                  reset_timing_tested=False, carrier_regulator_model=False,
                  physical_brightness_or_loaded_readback_guaranteed=False)
    report['LED_IV_interpretation'] = ('Authored constant knee plus5ohm slope anchored at the '
                                      'datasheet20mA typical or maximum25C point. Not a bound '
                                      'for low-current voltage, temperature, brightness or real LED behavior.')
    assert hashes == {str(p): sha(p) for p in source_paths}
    (output / 'index.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=guarded, cases=len(results), output=str(output),
                          legacy_topology_intentionally_rejected=rejected_legacy)))
    if rejected_legacy:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
