#!/usr/bin/env python3
"""Conditional boost input/power circuit experiments in real ngspice.

The legacy idle power-stage network is reused explicitly, with a separate
TN0702 input/filter network and simultaneous old-idle RUN loading. This is not
a vendor model, PCB extraction, physical qualification or closed-loop engine
simulation. Optional controller edges are replayed into the electrical model.
"""
import argparse
from dataclasses import asdict, dataclass
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

import numpy as np
import run_idle_circuit as idle

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def nominal(text):
    word = text.split()[0].removesuffix('F')
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([RkMmunp]?)(\d*)', word)
    if not match or (match[3] and '.' in match[1]):
        raise ValueError('Unsupported component value: ' + text)
    return float(match[1] + ('.' + match[3] if match[3] else '')) * {'': 1, 'R': 1, 'k': 1e3, 'M': 1e6, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12}[match[2]]


def replace(text, old, new):
    assert text.count(old) == 1, 'Legacy template changed: ' + old
    return text.replace(old, new, 1)


def binding(directory, carrier):
    data = json.loads((directory / 'net_contract.json').read_text())
    assert data['revision'] == 'BOOST-DRAFT1' and data['physical_default'] is False
    parts = {row['reference']: row for row in data['parts']}
    expected = {
        'J1': {'1': 'BOOST_CMD', '2': 'RUN_5V', '3': 'CARRIER_5V', '4': 'CARRIER_GND'},
        'Q1': {'1': 'GATE', '2': 'BOOST_LS', '3': 'ACT_GND'},
        'Q2': {'1': 'CARRIER_GND', '2': 'CMD_GATE', '3': 'PWM_LED_K'},
        'Q3': {'1': 'CARRIER_GND', '2': 'RUN_GATE', '3': 'RUN_LED_K'},
        'NT1': {'1': 'ACT_GND', '2': 'LOGIC_GND'},
        'R17': {'1': 'CARRIER_5V', '2': 'LED_5V'},
        'C13': {'1': 'LED_5V', '2': 'CARRIER_GND'},
        'C11': {'1': 'CMD_GATE', '2': 'CARRIER_GND'},
        'C12': {'1': 'RUN_GATE', '2': 'CARRIER_GND'},
    }
    assert all(parts[name]['pins'] == pins for name, pins in expected.items())
    assert all(parts[name]['mpn'] == 'TN0702N3-G' for name in ('Q2', 'Q3'))
    values = {name: nominal(parts[name]['value']) for name in
              ('R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R17', 'C9', 'C11', 'C12', 'C13')}
    expected_values = dict(R1=1000, R2=4700, R3=357, R4=357, R5=10000, R6=10000,
                           R17=47, C9=100e-9, C11=100e-9, C12=100e-9, C13=2.2e-6)
    assert all(math.isclose(values[key], value, rel_tol=1e-12) for key, value in expected_values.items())
    for name, value in {'R7': 1000, 'R8': 1000, 'R9': 1000, 'R10': 10000, 'R11': 1000,
                        'R12': 4700, 'R13': 33, 'R14': 10000, 'R15': 120, 'R16': 374}.items():
        assert nominal(parts[name]['value']) == value, name
    assert parts['R3']['pins']['1'] == parts['R4']['pins']['1'] == parts['C9']['pins']['1'] == 'LED_5V'
    own = json.loads((carrier/'net_contract.json').read_text())
    cp = {row['ref']: row for row in own['parts']}
    assert own['revision'] == 'A7-BOOST-INTERFACE-HOLD' and own['boost_interface']['physical_outputs_enabled'] is False
    assert cp['J21']['pins'] == {'1': 'IDLE_CMD', '2': 'RUN_5V', '3': '+5V', '4': 'GND', '5': 'BOOST_CMD'}
    assert cp['U3']['pins']['37'] == 'BOOST_CMD' and cp['R180']['pins'] == {'1': 'BOOST_CMD', '2': 'GND'}
    assert all(nominal(cp[key]['value']) == value for key, value in
               {'R47': 10000, 'R50': 1000, 'R53': 10000, 'R154': 2200, 'R180': 2200}.items())
    old = {row['reference']: row for row in json.loads((ROOT/'hardware/idle-isolated/net_contract.json').read_text())['parts']}
    assert all(nominal(old[key]['value']) == value for key, value in
               {'R1': 1000, 'R2': 2200, 'R3': 357, 'R4': 357, 'R5': 100000, 'R6': 100000}.items())
    return dict(values=values, checked_pin_bindings=expected,
                common_carrier_pins=cp['J21']['pins'], idle_input_loading_only=True,
                qualification='Literal topology/value consistency only; no dynamics or parasitics extracted from CAD')


@dataclass
class Case(idle.Case):
    threshold_a: float = .002
    vto: float = .90463
    kp: float = .22
    cap_scale: float = 1
    filter_scale: float = 1
    gate_cap_scale: float = 1
    command_open: bool = False
    run_open: bool = False
    hotplug: bool = False
    edge_run: str = ''
    edge_start_s: float = 5.5


def edge_waveform(c):
    if not c.edge_run:
        return None
    path = Path(c.edge_run)
    result = json.loads((path / 'result.json').read_text())
    assert result['completed'] and result['physical_execution'] is False
    source = [json.loads(line) for line in (path / 'edges.jsonl').read_text().splitlines()]
    a, b = round(c.edge_start_s*1e6), round((c.edge_start_s+.25)*1e6)
    assert 0 <= a < b <= round(result['duration_s']*1e6), 'Replay window exceeds source experiment'
    previous_sequence, previous_time = 0, -1
    for row in source:
        assert type(row['sequence']) is int and row['sequence'] > previous_sequence, 'Unordered source sequence'
        assert type(row['time_us']) is int and row['time_us'] >= previous_time, 'Unordered source clock'
        assert type(row['high']) is bool and type(row['ch']) is int and isinstance(row['cause'], str)
        previous_sequence, previous_time = row['sequence'], row['time_us']
    terminal = [row for row in source if a <= row['time_us'] <= b and
                (row['cause'].startswith('fixture') or row['cause'] == 'cut:simulation_end')]
    assert not terminal, 'Replay window includes a fixture terminal intervention'
    # Cuts are actual delivered edges too. Restricting this to normal dispatcher
    # events would silently erase the very falling edge a fault replay needs.
    edges = [row for row in source if row['ch'] == 9]
    assert all(row['time_us'] > prev['time_us'] and row['high'] != prev['high']
               for prev, row in zip(edges, edges[1:])), 'Invalid boost transition history'
    high = next((row['high'] for row in reversed(edges) if row['time_us'] <= a), False)
    points = [(0, c.command if high else 0)]
    observed = []
    for row in edges:
        if a < row['time_us'] <= b:
            t = (row['time_us']-a)*1e-6
            points += [(t, points[-1][1]), (t+1e-8, c.command if row['high'] else 0)]
            observed.append(row)
    assert observed and any(row['high'] for row in observed)
    points.append((.2501, points[-1][1]))
    return dict(pwl='PWL(' + ' '.join(f'{t:.12g} {v:.12g}' for t, v in points) + ')',
                controller=result['controller'], source_sha256={name: sha(path/name) for name in ('result.json', 'edges.jsonl')},
                initial_high=points[0][1] > 0,
                interval_s=[a/1e6, b/1e6], replayed_boost_edges=observed,
                qualification='All stored channel9 transitions, including control cuts, replayed with original causes. Initial state before its first edge assumed low. Fixture terminal interventions rejected. Electrical coil starts at zero on the declared fixed supply; no circuit feedback to the engine plant.')


def deck(c, values, waveform=None):
    text = idle.deck(c).replace('IAC-DRAFT2 conditional lumped fault experiment', 'BOOST-DRAFT1 conditional circuit experiment')
    text = replace(text, 'R154 gpio cg 2200', 'R180 gpio cg 2200')
    command_wire = 'DC 0' if c.command_open else ('PWL(0 1 4m 1 4.00001m 0)' if c.fault == 'command_wire_open' else 'DC 1')
    run_wire = 'DC 0' if c.run_open else ('PWL(0 1 4m 1 4.00001m 0)' if c.fault == 'run_wire_open' else 'DC 1')
    text = replace(text, 'R1 gpio pb 1000', f'Vcmdwire cmdwire 0 {command_wire}\nScmdwire gpio cmdin cmdwire 0 WIRE\nR1 cmdin pb {values["R1"]}')
    text = replace(text, 'R2 run rb 2200', f'Vrunwire runwire 0 {run_wire}\nSrunwire run runin runwire 0 WIRE\nR2 runin rb {values["R2"]}')
    text = replace(text, 'Q2 pc pb gin NPNGEN\nQ3 rc rb gin NPNGEN', '''M2 pc pb gin gin TNINPUT L=1u W=1u
M3 rc rb gin gin TNINPUT L=1u W=1u
* Explicit20V data-limit capacitances, or declared scaled sensitivity. They
* are not claimed bounds at low bias, temperature or with a real harness.
Cpwmgs pb gin {CGS}
Cpwmx pb pc {CGD}
Cpwmout pc gin {CDS}
Crungs rb gin {CGS}
Crunx rb rc {CGD}
Crunout rc gin {CDS}
C11 pb gin {GATECAP}
C12 rb gin {GATECAP}''')
    text = replace(text, 'R5 pb gin 100k', f'R5 pb gin {values["R5"]}')
    text = replace(text, 'R6 rb gin 100k', f'R6 rb gin {values["R6"]}')
    text = replace(text, 'R3 cin5 pla', 'R3 led5 pla')
    text = replace(text, 'R4 cin5 rla', 'R4 led5 rla')
    text = replace(text, 'Dpwled pl pc LED', 'Dpwled pl pc LIGHTLED\nCpw_junction pla pc 15p')
    text = replace(text, 'Drunled rl rc LED', 'Drunled rl rc LIGHTLED\nCrun_junction rla rc 15p')
    text = replace(text, 'C9 cin5 gin 100n', f'R17 cin5 filterres {values["R17"]}\nVfilter filterres led5 0\nC13 led5 gin {values["C13"]*c.filter_scale}\nC9 led5 gin {values["C9"]}')
    # A declared finite-slope optical surrogate avoids an ideal comparator's
    # discontinuous algebraic threshold. It is not a6N137 transfer curve.
    for source, sense, node in [('Bpwr', 'Vpwmled', 'rawpw'), ('Brun', 'Vrunled', 'rawrun')]:
        text = replace(text, f'{source} {node} ag V=(i({sense})>0.005 ? 1 : 0)',
            f'{source} {node} ag V=(.5+.5*tanh((i({sense})-{c.threshold_a})/{c.threshold_a*.01}))')
    text = replace(text, 'Rcoil vin winding 8', 'Rcoil vin winding 36')
    text = replace(text, 'Lcoil winding drain 12m', 'Lcoil winding drain 30m')
    text = replace(text, 'Bgcmd gcmd ag V=(v(ina,ag)>2.4 && v(ena,ag)>2.4 && v(rail,ag)>3.5 ? 1 : 0)', '''* Explicit conditional input hysteresis. A zero-hysteresis ideal comparator
* can chatter at2.4V when starting gate current perturbs its own local rail.
* These2.4/1.0V assumptions are not a procured PDIP guarantee.
Vlogic_one logicone ag 1
Sinput logicone inputok ina ag INPUTSCHMITT
Rinputok inputok ag 10k
Senable logicone enableok ena ag INPUTSCHMITT
Renableok enableok ag 10k
.model INPUTSCHMITT SW(Ron=1 Roff=1e12 Vt=1.7 Vh=.7)
Bgcmd gcmd ag V=(v(inputok,ag)>.5 && v(enableok,ag)>.5 && v(rail,ag)>3.5 ? 1 : 0)''')
    trunk_power = 'PWL(0 1 4m 1 4.00001m 0)' if c.fault == 'trunk_power_open' else 'DC 1'
    trunk_return = 'PWL(0 1 4m 1 4.00001m 0)' if c.fault == 'trunk_return_open' else 'DC 1'
    text = replace(text, 'Sinputpower c5 cin5 pwrctl 0 WIRE', 'Sinputpower trunk5 cin5 pwrctl 0 WIRE')
    text = replace(text, 'Vcarrier_return crwire cg 0', 'Vcarrier_return crwire trunkg 0')
    text = replace(text, '.model NPNGEN', f'''.temp 25
.param CGS={140e-12*c.cap_scale} CGD={60e-12*c.cap_scale} CDS={65e-12*c.cap_scale} GATECAP={values['C11']*c.gate_cap_scale}
.model TNINPUT NMOS(Level=1 Vto={c.vto} Kp={c.kp} Rd=.01 Rs=.01 Tnom=25)
.model LIGHTLED D(Is=1e-18 N=1.5 Rs=3 Cjo=0)
* The explicit15pF LED-junction caps bypass the optical-current sensors.
* Only modeled forward diode current drives light, not displacement current.
Vtrunkpowerctl trunkpowerctl 0 {trunk_power}
Vtrunkreturnctl trunkreturnctl 0 {trunk_return}
Strunkpower c5 trunk5 trunkpowerctl 0 WIRE
Strunkreturn trunkg trunkret trunkreturnctl 0 WIRE
Vtrunkreturn trunkret cg 0
* Both original IAC-DRAFT2 input buffers, including negative BE clamps, are
* attached to the common A7 trunk. Its detector/coil are not modeled here;
* no idle-output acceptance follows from these boost-output observations.
Ridlebase run ibase 2200
Ridleoff ibase trunkg 100k
Qidle icath ibase trunkg NPNGEN
Ridleled trunk5 ianode 357
Didle ianode icath LED
Didlerunclamp trunkg ibase DIODE
Vidlegpio idlesrc cg DC 3.3
Ridlegpiodrive idlesrc idlegpio 30
R154 idlegpio cg 2200
Ridlecmdbase idlegpio icmdbase 1000
Ridlecmdoff icmdbase trunkg 100k
Qidlecmd icmdcath icmdbase trunkg NPNGEN
Ridlecmdled trunk5 icmdanode 357
Didlecmd icmdanode icmdcath LED
Didlecmdclamp trunkg icmdbase DIODE
Cidlebypass trunk5 trunkg 100n
.model NPNGEN''')
    # Full return separation is retained. The internal source/Kelvin star is
    # ideal here; no extracted PCB impedance or isolation capacitance is used.
    text = replace(text, 'wrdata trace.tsv rail_v gate_v ina_v ena_v drain_v gp_v v(ag) i(Lcoil) i(Vpwmled) i(Vrunled) i(Vcarrier_return) i(Vactreturn)',
        'wrdata trace.tsv rail_v gate_v ina_v ena_v drain_v gp_v v(ag) i(Lcoil) i(Vpwmled) i(Vrunled) i(Vcarrier_return) i(Vactreturn) v(pb,gin) v(rb,gin) v(led5,gin) v(nor,ag) v(run,cg) v(mainin,cg) i(Vrun) i(Vgpio) i(Vfilter) v(c5,cg) i(Vtrunkreturn) v(trunkg,cg)')
    if c.hotplug:
        text = replace(text, f'Vcarrier c5 cg DC {c.carrier}', f'Vcarrier c5 cg PWL(0 0 1m 0 1.00001m {c.carrier})')
    # Detector supply/supervisor can start warm, but input capacitors, optical
    # states and coil current start unenergized. No seeded optical high may
    # masquerade as a transmitted input pulse or a hotplug failure.
    if not c.cold:
        text = re.sub(r'v\(pwf\)=\S+', 'v(pwf)=0', text)
        text = re.sub(r'v\(pwmn\)=\S+', 'v(pwmn)=5.1645', text)
        text = re.sub(r'v\(runf\)=\S+', 'v(runf)=0', text)
        text = re.sub(r'v\(runn\)=\S+', 'v(runn)=5.1645', text)
    if c.hotplug:
        text = re.sub(r'v\(cin5\)=\S+', 'v(cin5)=0', text)
    if waveform:
        text = replace(text, f'Vgpio gpiosrc cg DC {c.command}', 'Vgpio gpiosrc cg ' + waveform['pwl'])
    # Every short pulse has explicit absolute-time edges and an observed source
    # witness. No repeated-PULSE middle edge can vanish in a coarse long gap.
    if c.pulse_us:
        old = f'PULSE(0 {c.command} 2m 10n 10n {c.pulse_us*1e-6} 100m)'
        finish = .002+1e-8+c.pulse_us*1e-6
        text = replace(text, old, f'PWL(0 0 .002 0 .00200001 {c.command} {finish:.12g} {c.command} {finish+1e-8:.12g} 0)')
    stop = .8 if c.cold else (.2501 if waveform else .012)
    dt = c.maximum_step_us*1e-6
    text = re.sub(r'tran [^\n]+ uic', f'tran {dt} {stop} 0 {dt} uic', text)
    return text, stop


def cases(edge_runs, edge_starts=None):
    result = [Case('warm'), Case('cold', cold=True, maximum_step_us=20)]
    result += [Case(fault, fault=fault) for fault in ('command_low', 'run_low', 'command_wire_open', 'run_wire_open', 'actuator_return_open', 'actuator_power_open', 'trunk_power_open', 'trunk_return_open', 'rail_drop', 'drain_short')]
    result += [Case('boost_stub_power_open', fault='carrier_power_open'), Case('boost_stub_return_open', fault='carrier_return_open')]
    result += [Case('return_bridge_negative', fault='actuator_return_open', bridge=True),
               Case('late_supervisor', fault='rail_drop', pg_assert_us=100)]
    result += [Case('hotplug_open', hotplug=True, command_open=True, run_open=True, threshold_a=.000251),
               Case('hotplug_cap_sensitivity', hotplug=True, command_open=True, run_open=True,
                    threshold_a=.000251, vto=.1, kp=.1, cap_scale=16, filter_scale=.8, gate_cap_scale=.95),
               Case('low_run_high_rail', carrier=4.5, run=3.84, command=2.64)]
    result += [Case(f'pulse_{us}us', pulse_us=us, command=2.4, maximum_step_us=.1) for us in (1, 40, 100, 200, 500)]
    for index, path in enumerate(edge_runs):
        result.append(Case(f'engine_edges_{index}', edge_run=str(path.resolve()),
                           edge_start_s=edge_starts[index] if edge_starts else 5.5, maximum_step_us=2))
    return result


def analyze(c, a, stop, waveform):
    t = a[:, 0]
    assert a.shape[1] == 25 and np.all(np.isfinite(a)) and np.all(np.diff(t) >= 0)
    assert t[-1] >= stop-1e-8
    average = lambda n: float(np.trapezoid(a[t>stop-.0005, n], t[t>stop-.0005])/(t[-1]-t[t>stop-.0005][0]))
    above = lambda n, value: float(np.trapezoid((a[:, n]>value).astype(float), t))
    peaks = {name: float(np.max(np.abs(a[:, n]))) for name, n in
             [('coil_a', 8), ('pwm_led_a', 9), ('run_led_a', 10), ('gpio_source_a', 20), ('run_source_a', 19), ('led_filter_input_a', 21)]}
    row = dict(case=asdict(c), rows=len(t), final_time_s=float(t[-1]), final_coil_a=average(8),
        final_gate_v=average(2), peak=peaks, supplied_gpio_high_s=above(6, 1.5),
        conditional_nor_high_s=above(16, 2.4), mos_gate_above4v_s=above(2, 4),
        final_run_v=average(17), final_mainin_v=average(18),
        invalid_rail_gate_s=float(np.trapezoid(((a[:, 1]<4.5)&(a[:, 2]>2)).astype(float), t)),
        mean_late_carrier_return_a=float(np.mean(np.abs(a[t>stop-.0005, 11]))),
        mean_late_trunk_return_a=float(np.mean(np.abs(a[t>stop-.0005, 23]))),
        controller_edge_replay=waveform, physical_execution=False)
    row['maximum_gate_v'] = float(np.max(a[:, 2]))
    high = np.flatnonzero(a[:, 2] > 4)
    row['first_gate_above4v_s'] = float(t[high[0]]) if len(high) else None
    gpio = a[:, 6] > 1.5
    row['observed_source_high_periods'] = int(gpio[0]) + int(np.count_nonzero(gpio[1:] & ~gpio[:-1]))
    if c.pulse_us:
        assert np.max(a[:, 6]) > c.command*.8 and 0 < row['supplied_gpio_high_s'] < c.pulse_us*1e-6+1e-6 and row['observed_source_high_periods'] == 1
    if waveform:
        expected = int(waveform['initial_high']) + sum(edge['high'] for edge in waveform['replayed_boost_edges'])
        assert row['observed_source_high_periods'] == expected, 'Source edge replay lost a supplied pulse'
    return row


def validate(records):
    rows = {row['case']['name']: row for row in records}
    assert .31 < rows['warm']['final_coil_a'] < .35 and rows['warm']['final_gate_v'] > 4
    for name in ('command_low', 'run_low', 'command_wire_open', 'run_wire_open', 'boost_stub_power_open',
                 'boost_stub_return_open', 'trunk_power_open', 'trunk_return_open', 'actuator_power_open', 'rail_drop', 'late_supervisor'):
        assert rows[name]['final_gate_v'] < .1 and rows[name]['final_coil_a'] < .001, name
    assert rows['actuator_return_open']['mean_late_carrier_return_a'] < .05
    assert rows['return_bridge_negative']['mean_late_carrier_return_a'] > .1
    assert rows['drain_short']['final_gate_v'] < .1 and rows['drain_short']['final_coil_a'] > .2
    assert .15 < rows['cold']['first_gate_above4v_s'] < .71
    for name in ('hotplug_open', 'hotplug_cap_sensitivity'):
        assert rows[name]['conditional_nor_high_s'] == 0 and rows[name]['maximum_gate_v'] < .1, name
    assert rows['pulse_1us']['maximum_gate_v'] < .1
    assert rows['pulse_100us']['conditional_nor_high_s'] > 0
    assert rows['late_supervisor']['invalid_rail_gate_s'] > rows['rail_drop']['invalid_rail_gate_s']*3
    for row in records:
        if row['controller_edge_replay']:
            assert row['mos_gate_above4v_s'] > 0 and row['peak']['coil_a'] > .01, row['case']['name']
    return dict(passed=True, qualification='Declared conditional circuit consequences, working unsafe controls and explicit short-pulse loss; no physical acceptance')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accessory', type=Path, required=True)
    parser.add_argument('--carrier', type=Path, required=True)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine-run', type=Path, action='append', default=[])
    parser.add_argument('--engine-start-s', type=float, action='append', default=[],
                        help='One start time per --engine-run, in the same order; defaults to5.5s')
    parser.add_argument('--case', action='append', default=[])
    args = parser.parse_args()
    if args.engine_start_s and (len(args.engine_start_s) != len(args.engine_run) or
                               not all(math.isfinite(v) and v >= 0 for v in args.engine_start_s)):
        parser.error('Supply one finite nonnegative --engine-start-s per --engine-run')
    available = cases(args.engine_run, args.engine_start_s)
    unknown = set(args.case) - {c.name for c in available}
    if unknown:
        parser.error('Unknown circuit case(s): ' + ', '.join(sorted(unknown)))
    selected = [c for c in available if not args.case or c.name in args.case]
    if not selected:
        parser.error('At least one circuit case must be selected')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    accessory = args.accessory.resolve(); carrier = args.carrier.resolve(); checked = binding(accessory, carrier)
    sources = [Path(__file__), Path(idle.__file__), accessory/'net_contract.json', accessory/'isolated.kicad_pcb',
               ROOT/'hardware/boost-control/circuit-draft1.json', ROOT/'scripts/build_boost_hardware.py',
               ROOT/'hardware/a6-flex-rgb/net_contract.json', ROOT/'hardware/idle-isolated/net_contract.json']
    sources += [carrier/'net_contract.json', carrier/'esp32-ecu.kicad_pcb', ROOT/'hardware/boost-control/interface-draft2.json']
    sources += [path.resolve()/name for path in args.engine_run for name in ('result.json', 'edges.jsonl')]
    frozen = {str(path): sha(path) for path in sources}
    for path in sources:
        relative = path.resolve().relative_to(ROOT)
        target = out/'source-snapshot'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        assert sha(target) == frozen[str(path)]
    binary = args.ngspice.resolve()
    report = dict(scope=__doc__.strip(), source_sha256=frozen, contract_consistency=checked,
        ngspice_sha256=sha(binary), ngspice_version=subprocess.check_output([str(binary), '--version'], text=True),
        python_executable=sys.executable, python_sha256=sha(Path(sys.executable).resolve()), python_version=platform.python_version(),
        numpy_version=np.__version__, physical_execution=False, circuit_engine_feedback=False,
        assumptions='Conditional TN25C fit plus explicit hot/cap sensitivity;1% optical sigmoid regularization, threshold/pole not measured. Ideal source47R RUN, inherited Q7 proxy not a device guarantee. Regulator/supervisor/power MOS network inherited, with conditional2.4/1.0V driver-input hysteresis and declared coil36ohm/30mH. Warm detector supply/supervisor; input states and coil start unenergized. Source star ideal. No PCB/harness/thermal/EMI/surge extraction or physical minimum pulse.', results=[])
    (out/'inputs.json').write_text(json.dumps(report, indent=2)+'\n')
    for c in selected:
        directory = out/c.name; directory.mkdir()
        waveform = edge_waveform(c); text, stop = deck(c, checked['values'], waveform)
        (directory/'circuit.cir').write_text(text)
        run = subprocess.run([str(binary), '-b', 'circuit.cir'], cwd=directory, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        (directory/'ngspice.log').write_text(run.stdout)
        assert run.returncode == 0 and (directory/'trace.tsv').exists(), (c.name, run.stdout[-2500:])
        a = np.loadtxt(directory/'trace.tsv', skiprows=1)
        result = analyze(c, a, stop, waveform); report['results'].append(result)
        with gzip.open(directory/'trace.tsv.gz', 'wb') as stream: stream.write((directory/'trace.tsv').read_bytes())
        (directory/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(c.name, result['final_coil_a'], result['final_gate_v'], flush=True)
    assert frozen == {str(path): sha(path) for path in sources}, 'Circuit inputs changed during run'
    report['source_unchanged'] = True
    if not args.case:
        report['validation'] = validate(report['results'])
    (out/'results.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
