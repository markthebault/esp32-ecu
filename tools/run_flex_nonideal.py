#!/usr/bin/env python3
"""Conditional local-rail/ADC-coupling sensitivity, not a qualified board model.

Uses the selected circuit graph plus authored branch R/L, capacitor ESR/ESL,
rail stimuli and module-current fixtures. Regulator control loops, actual GPIO
thresholds, CPU brownout, ground bounce and extracted PCB parasitics are absent.
No parameter sweep establishes manufacturer limits or physical protection.
"""
import argparse
from dataclasses import asdict, dataclass, replace
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import run_flex_circuit as nominal

ROOT = Path(__file__).resolve().parents[1]
PROFILE = Path('hardware/flex-input/frontend-compact.json')
CORE = Path('hardware/a6-flex-rgb/net_contract.json')
COLUMNS = ['time', 'wave', 'raw', 'in', 'ref', 'cmp', 'gpio', 'pull33',
           'comp5', 'bias', 'pull_mid', 'input_mid', 'sensor_current',
           'source5_current', 'source33_current', 'pull_mid2', 'module33',
           'bus5', 'bus33', 'adc7', 'adc_hold', 'adc_ref', 'sample7', 'sensor5', 'map_adc', 'tps_adc', 'clt_adc', 'iat_adc']
THRESHOLDS = [(.25, .25), (.5, .5), (.75, .75), (.75, .25)]


@dataclass(frozen=True)
class Scenario:
    name: str
    low_us: float = 3000
    duration_ms: float = 220
    max_step_us: float = 1
    solver: str = 'sparse'
    minimum_break_s: float = 1e-15
    cap160_scale: float = 1
    cap164_scale: float = 1
    ceramic_esr_ohm: float = .1
    ceramic_esl_nh: float = 10
    source5_ohm: float = .1
    source33_ohm: float = .1
    branch_ohm: float = .05
    branch_nh: float = 20
    c9_esr_ohm: float = .3
    coupling_pf: float = 0
    c27_scale: float = 1
    sample_pf: float = 20
    sample_ohm: float = 1000
    sample_enabled: bool = True
    adc_phase_us: float = 500
    prior_adc_v: float = 14 / 13
    sensor_fuse_ohm: float = 4.5
    sensor_load_a: float = .02
    drop5_v: float = 0
    drop33_v: float = 0
    disturbance_us: float = 94600
    disturbance_duration_us: float = 1000
    disturbance_rise_us: float = 1
    extra_module_a: float = 0
    ripple5_v: float = 0
    ripple33_v: float = 0
    ripple_hz: float = 100000
    ripple_cycles: int = 10
    ripple_phase_deg: float = 0


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind():
    result = nominal.binding(PROFILE)
    core = nominal.read_json(ROOT / CORE)
    parts = {part['ref']: part for part in core['parts']}
    assert len(parts) == len(core['parts']) == 264
    expected = {
        'R7': ('100R 0.25W', {'1': '+3V3', '2': 'GND'}),
        'C5': ('22u 16V electrolytic', {'1': '+5V', '2': 'GND'}),
        'C6': ('22u 16V electrolytic', {'1': '+5V', '2': 'GND'}),
        'C9': ('22u 10V ESR 0.3-1R', {'1': '+3V3', '2': 'GND'}),
        'C13': ('10u', {'1': '+3V3', '2': 'GND'}),
        'C14': ('100n', {'1': '+3V3', '2': 'GND'}),
        'C28': ('100n', {'1': '+3V3', '2': 'GND'}),
        'C29': ('1u', {'1': '+3V3', '2': 'GND'}),
        'C163': ('10uF 16V radial candidate', {'1': '+3V3', '2': 'GND'}),
        'F2': ('PTC 100mA radial', {'1': '+5V', '2': 'SENSOR_5V'}),
        'C11': ('1u', {'1': 'SENSOR_5V', '2': 'GND'}),
        'R36': ('22k 1%', {'1': 'SENSOR_5V', '2': 'ADC7'}),
        'R37': ('33k 1%', {'1': 'ADC7', '2': 'GND'}),
        'C27': ('10n', {'1': 'ADC7', '2': 'GND'}),
    }
    for channel, signal in enumerate(['MAP', 'TPS', 'CLT', 'IAT']):
        expected[f'R{20+2*channel}'] = ('22k 1%', {'1': signal, '2': f'ADC{channel}'})
        expected[f'R{21+2*channel}'] = ('33k 1%', {'1': f'ADC{channel}', '2': 'GND'})
        expected[f'C{20+channel}'] = ('10n', {'1': f'ADC{channel}', '2': 'GND'})
    for ref, signal in [('R32', 'CLT'), ('R33', 'IAT')]:
        expected[ref] = ('2.49k 1% NTC', {'1': 'SENSOR_5V', '2': signal})
    for ref, (value, pins) in expected.items():
        assert parts[ref]['value'] == value and parts[ref]['pins'] == pins, ref
    assert parts['U6']['mpn'] == 'MCP3208-CI/P'
    assert parts['F2']['mpn'] == 'MF-R010'
    assert parts['U6']['pins']['8'] == 'ADC7'
    assert parts['U6']['pins']['15'] == parts['U6']['pins']['16'] == '+3V3'
    assert parts['D170']['pins'] == {'1': 'ADC7', '2': 'GND'}
    assert parts['D171']['pins'] == {'1': '+3V3', '2': 'ADC7'}
    assert parts['D170']['mpn'] == parts['D171']['mpn'] == 'BAT85,113'
    result.update(native_contract_sha256=sha(ROOT / CORE), core_elements=expected)
    return result


def validate(s):
    assert s.name and all(c.isalnum() or c in '-_' for c in s.name)
    for key, value in asdict(s).items():
        if key in ('name', 'solver', 'sample_enabled'):
            continue
        assert type(value) in (int, float) and math.isfinite(value), key
    assert type(s.sample_enabled) is bool
    assert s.solver in ('sparse', 'klu')
    assert 1e-16 <= s.minimum_break_s <= 1e-12
    assert s.low_us in (1000, 3000, 5000)
    assert 100 <= s.duration_ms <= 1000 and .05 <= s.max_step_us <= 5
    assert .000001 <= s.cap160_scale <= 2 and .000001 <= s.cap164_scale <= 2
    assert .001 <= s.ceramic_esr_ohm <= 10 and .1 <= s.ceramic_esl_nh <= 1000
    assert .001 <= s.source5_ohm <= 10 and .001 <= s.source33_ohm <= 10
    assert .001 <= s.branch_ohm <= 10 and .1 <= s.branch_nh <= 1000
    assert .3 <= s.c9_esr_ohm <= 1
    assert 0 <= s.coupling_pf <= 1000 and 0 <= s.c27_scale <= 2
    assert 1 <= s.sample_pf <= 100 and 100 <= s.sample_ohm <= 10000
    assert 336 <= s.adc_phase_us <= 4000 and 0 <= s.prior_adc_v <= 3.3
    assert 2.5 <= s.sensor_fuse_ohm <= 7.5 and 0 <= s.sensor_load_a <= .1
    assert 0 <= s.drop5_v <= 3 and 0 <= s.drop33_v <= 1
    assert s.disturbance_us > 80000 and s.disturbance_duration_us >= 1
    assert s.disturbance_rise_us > 0
    assert s.disturbance_us + s.disturbance_duration_us + s.disturbance_rise_us < s.duration_ms * 1000
    assert 0 <= s.extra_module_a <= .5
    assert 0 <= s.ripple5_v <= .5 and 0 <= s.ripple33_v <= .3
    assert 1000 <= s.ripple_hz <= 1000000 and type(s.ripple_cycles) is int and 1 <= s.ripple_cycles <= 2000
    assert -360 <= s.ripple_phase_deg <= 360
    if s.ripple5_v or s.ripple33_v:
        assert s.disturbance_us + 2*s.disturbance_rise_us + s.ripple_cycles*1e6/s.ripple_hz < s.duration_ms*1000
    assert not ((s.drop5_v or s.drop33_v) and (s.ripple5_v or s.ripple33_v))


def pwl(points):
    assert all(points[i][0] < points[i + 1][0] for i in range(len(points) - 1))
    return 'PWL(' + ' '.join(f'{time:.12g}u {value:.12g}' for time, value in points) + ')'


def supply_wave(s, normal, drop, ripple):
    if not drop and not ripple:
        return str(normal)
    start = s.disturbance_us
    if drop:
        points = [(0, normal), (start, normal),
                  (start + s.disturbance_rise_us, normal - drop),
                  (start + s.disturbance_rise_us + s.disturbance_duration_us, normal - drop),
                  (start + 2 * s.disturbance_rise_us + s.disturbance_duration_us, normal)]
    else:
        # Explicit PWL knots force integration through every ripple period;
        # an arbitrary-time behavioural sine could alias at the max timestep.
        points = [(0, normal), (start, normal)]
        points += [(start + s.disturbance_rise_us + n * 1e6 / s.ripple_hz / 20,
                    normal + ripple * math.sin(2 * math.pi * n / 20 + math.radians(s.ripple_phase_deg)))
                   for n in range(s.ripple_cycles * 20 + 1)]
        points.append((start + 2*s.disturbance_rise_us + s.ripple_cycles*1e6/s.ripple_hz, normal))
    assert points[-1][0] < s.duration_ms * 1000
    return pwl(points + [(s.duration_ms * 1000, normal)])


def deck(s):
    validate(s)
    lines = nominal.deck(nominal.Case(s.name, low_us=s.low_us,
                         duration_ms=s.duration_ms, max_step_us=s.max_step_us), PROFILE).splitlines()
    # Default wrdata precision rounds distinct sub-ns ADC-switch steps to the
    # same printed timestamp. Preserve the adaptive solver's time ordering.
    lines.insert(lines.index('set wr_vecnames') + 1, 'set numdgt=16')
    # Upstream ngspice887/888: coincident corners can generate sub-ULP
    # breakpoints, and the interactive tran task ignores minbreak. Use the
    # netlist analysis job with run; preserve strict time-order validation.
    option = next(i for i, line in enumerate(lines) if line.startswith('.options '))
    lines[option] += f' {s.solver} minbreak={s.minimum_break_s:.17g}'
    analysis = next(i for i, line in enumerate(lines) if line.startswith('tran '))
    job = lines[analysis]
    lines[analysis] = 'run'
    lines.insert(lines.index('.control'), '.' + job)

    def set_line(prefix, replacement):
        indexes = [i for i, line in enumerate(lines) if line.startswith(prefix + ' ')]
        assert len(indexes) == 1, prefix
        lines[indexes[0]] = replacement

    def cap(ref, node, farad, esr, esl_nh):
        return (f'Rmodel_{ref} {node} {ref}_series_r {esr}\n'
                f'Lmodel_{ref} {ref}_series_r {ref}_body {esl_nh}n\n'
                f'{ref} {ref}_body 0 {farad:.12g}')

    set_line('V5', 'V5 supply5 0 ' + supply_wave(s, 5, s.drop5_v, s.ripple5_v))
    set_line('V33', 'V33 supply33 0 ' + supply_wave(s, 3.3, s.drop33_v, s.ripple33_v))
    set_line('R5wire', f'R5wire supply5 bus5 {s.source5_ohm}')
    set_line('R33wire', f'R33wire supply33 bus33 {s.source33_ohm}')
    set_line('Rcarrier7', 'Rcarrier7 bus33 0 100')
    set_line('Ccarrier9', cap('C9', 'bus33', 22e-6, s.c9_esr_ohm, 10))
    set_line('Rload5', 'Rload5 bus5 0 10000')
    set_line('C160', cap('C160', 'rail5', 100e-9 * s.cap160_scale, s.ceramic_esr_ohm, s.ceramic_esl_nh))
    set_line('C164', cap('C164', 'rail33', 100e-9 * s.cap164_scale, s.ceramic_esr_ohm, s.ceramic_esl_nh))
    set_line('Dgpiohi', 'Dgpiohi gpio module33 DGPIO')
    assert len([line for line in lines if line.startswith('wrdata ')]) == 1
    index = next(i for i, line in enumerate(lines) if line.startswith('wrdata '))
    lines[index] += ' v(module33) v(bus5) v(bus33) v(adc7) v(adc_hold) v(adc_ref) v(sample7) v(sensor5) v(map_adc) v(tps_adc) v(clt_adc) v(iat_adc)'
    extra = ['* Nonideal local branches are authored fixtures, not extracted interconnect.',
             '* Source33 is an independent Thevenin equivalent, not an LD1117 loop/dropout model.',
             '* CPU operation and GPIO transfer thresholds during rail changes are assumed.']
    for origin, node in [('bus5', 'rail5'), ('bus33', 'rail33'),
                         ('bus33', 'module33'), ('bus33', 'adc_ref'), ('bus33', 'rgb33')]:
        extra += [f'Rmodel_branch_{node} {origin} branch_{node} {s.branch_ohm}',
                  f'Lmodel_branch_{node} branch_{node} {node} {s.branch_nh}n']
    for ref, node, value, esr in [('C5', 'bus5', 22e-6, .3), ('C6', 'bus5', 22e-6, .3),
                                  ('C13', 'module33', 10e-6, .3), ('C14', 'module33', 100e-9, .1),
                                  ('C28', 'adc_ref', 100e-9, .1), ('C29', 'adc_ref', 1e-6, .1),
                                  ('C163', 'rgb33', 10e-6, .3)]:
        extra.append(cap(ref, node, value, esr, 10))
    start = s.disturbance_us
    module_wave = pwl([(0, .04), (start, .04), (start + s.disturbance_rise_us, .04 + s.extra_module_a),
                       (start + s.disturbance_rise_us + s.disturbance_duration_us, .04 + s.extra_module_a),
                       (start + 2 * s.disturbance_rise_us + s.disturbance_duration_us, .04),
                       (s.duration_ms * 1000, .04)]) if s.extra_module_a else '.04'
    extra += [f'Imodel_module module33 0 {module_wave}', 'Imodel_comp rail5 0 1m',
              'Imodel_adc adc_ref 0 300u', 'Imodel_rgb rgb33 0 2m',
              '* Input-current mirror only; regulator dynamics/efficiency are not modeled.',
              'Bmodel_reg_input bus5 0 I=max(-i(V33),0)',
              '* Constant F2 resistance probes cold/post-trip values, not thermal/trip behavior.',
              f'Rmodel_F2 bus5 sensor5 {s.sensor_fuse_ohm}',
              cap('C11', 'sensor5', 1e-6, .1, 10),
              f'Imodel_sensors sensor5 0 {s.sensor_load_a}',
              'R36 sensor5 adc7 22000', 'R37 adc7 0 33000',
              '* ADC pin/hold equivalent follows DS21298E Fig4-1 typical quantities.',
              'Cmodel_adc_pin adc7 0 7p', '.model DADC D(IS=1e-12 N=1 RS=10 CJO=5p)',
              'Dmodel_adc_hi adc7 adc_ref DADC', 'Dmodel_adc_lo 0 adc7 DADC',
              f'.model ADC_SAMPLE SW(RON={s.sample_ohm} ROFF=1e12 VT=.5 VH=0)',
              f'Cmodel_adc_sample adc_hold 0 {s.sample_pf}p',
              f'Vmodel_previous adc_previous 0 {s.prior_adc_v}',
              'Bmodel_previous_control previous_control 0 V=1-v(sample7)',
              'Smodel_previous adc_previous adc_hold previous_control 0 ADC_SAMPLE',
              'Smodel_sample adc7 adc_hold sample7 0 ADC_SAMPLE']
    if s.c27_scale:
        extra.append(cap('C27', 'adc7', 10e-9 * s.c27_scale, s.ceramic_esr_ohm, s.ceramic_esl_nh))
    else:
        extra.append('* Fault witness: C27 and its authored ESR/ESL branch are physically open.')
    extra += ['* Fixed true MAP50kPa/TPS10pct at nominal5V. Ideal sensor outputs;',
              '* their loaded board22k/33k/10nF paths below are simulated.',
              'Bmodel_map MAP 0 V=.42*v(sensor5)',
              'Bmodel_tps TPS 0 V=.18*v(sensor5)',
              '* Optional R32/R33 are fitted in this synthetic NTC fixture only.']
    for channel, (signal, node) in enumerate([('MAP', 'map_adc'), ('TPS', 'tps_adc'),
                                             ('CLT', 'clt_adc'), ('IAT', 'iat_adc')]):
        extra += [f'R{20+2*channel} {signal} {node} 22000',
                  f'R{21+2*channel} {node} 0 33000',
                  cap(f'C{20+channel}', node, 10e-9, .1, 10)]
    for channel, signal, temperature in [(2, 'CLT', 85), (3, 'IAT', 25)]:
        resistance = 10000 * math.exp(3950 * (1/(temperature+273.15) - 1/298.15))
        extra += [f'R{30+channel} sensor5 {signal} 2490',
                  f'Rmodel_ntc{channel} {signal} 0 {resistance:.17g}']
    extra.append(f'Vmodel_sample sample7 0 PULSE(0 1 {s.adc_phase_us}u 1n 1n 2.999u 5000u)'
                 if s.sample_enabled else 'Vmodel_sample sample7 0 0')
    if s.coupling_pf:
        extra.append(f'Cmodel_coupling adc7 flex_in {s.coupling_pf}p')
    lines.insert(lines.index('.control'), '\n'.join(extra))
    return '\n'.join(lines) + '\n'


def gpio_edges(time, normalized, rising, falling):
    """Stateful assumed input transfer; no repeated HIGH events from ringing."""
    assert 0 < falling <= rising < 1
    initial = normalized[0]
    state = True if initial >= rising else False if initial <= falling else None
    candidates = nominal.edges(time, normalized, falling, rising)
    result = []
    for when, high in candidates:
        if state is None or high != state:
            state = high
            result.append((when * 1e6, int(high)))
    return result


def build_control(output):
    cjson = Path.home() / '.platformio/packages/framework-espidf/components/json/cJSON'
    assert (cjson / 'cJSON.c').is_file() and (cjson / 'cJSON.h').is_file()
    commands = [
        ['cc', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
         '-c', str(cjson / 'cJSON.c'), '-o', str(output / 'cJSON.o')],
        ['g++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pedantic',
         '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I' + str(cjson),
         '-I' + str(ROOT / 'firmware/include'), str(ROOT / 'tools/flex_circuit_control.cpp'),
         str(output / 'cJSON.o'), '-o', str(output / 'control')]]
    for index, command in enumerate(commands):
        with (output / f'build-{index}.log').open('xb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    (output / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    return output / 'control'


def prepare_ngspice(requested, output):
    """Bind the executable, not only an attested shell wrapper."""
    requested = requested.resolve()
    inputs = {str(requested): sha(requested)}
    executable = requested
    if not requested.read_bytes().startswith(b'\x7fELF'):
        manifest = requested.parent / 'manifest.json'
        declaration = json.loads(manifest.read_text())
        executable = requested.with_name('ngspice-elf')
        if declaration['wrapper_sha256'] != sha(requested) or declaration['ngspice_sha256'] != sha(executable):
            raise ValueError('Ngspice wrapper/executable attestation differs')
        inputs.update({str(manifest): sha(manifest), str(executable): sha(executable)})
    if not executable.read_bytes().startswith(b'\x7fELF'):
        raise ValueError('Use the actual Linux ELF or the attested review wrapper')
    folder = output / 'toolchain'
    folder.mkdir()
    retained = folder / 'ngspice-elf'
    shutil.copyfile(executable, retained)
    retained.chmod(0o755)
    scripts = folder / 'spice-lib/scripts'
    scripts.mkdir(parents=True)
    startup = scripts / 'spinit'
    startup.write_text('* Owned builtin-only startup; no user or external code models\nset num_threads=1\n')
    env = dict(os.environ, SPICE_LIB_DIR=str(scripts.parent), SPICE_SCRIPTS=str(scripts), OMP_NUM_THREADS='1')
    version = subprocess.check_output([str(retained), '-n', '--version'], env=env, stderr=subprocess.STDOUT, text=True)
    record = dict(requested=str(requested), actual_executable=str(executable),
        executable_sha256=sha(retained), startup_sha256=sha(startup), input_sha256=inputs,
        version=version, numpy=np.__version__, user_spiceinit_disabled=True,
        external_code_models_loaded=False)
    (output / 'toolchain.json').write_text(json.dumps(record, indent=2) + '\n')
    return retained, env, inputs


def scenarios():
    base = Scenario('baseline')
    result = [base, replace(base, name='no-sampling-load', sample_enabled=False)]
    for coupling in (1, 5, 50, 500):
        result.append(replace(base, name=f'coupling-{coupling}pf', coupling_pf=coupling))
    for scale in (.1, .5):
        result.append(replace(base, name=f'bypass-{int(scale * 100)}pct', cap160_scale=scale,
                              cap164_scale=scale, coupling_pf=1))
    result += [replace(base, name='series-stress', ceramic_esr_ohm=1, ceramic_esl_nh=100,
                       branch_nh=100, c9_esr_ohm=1, cap160_scale=.1, cap164_scale=.1, coupling_pf=5),
               replace(base, name='five-volt-dip', drop5_v=.4, coupling_pf=1),
               replace(base, name='three-volt-dip', drop33_v=.3, coupling_pf=1),
               replace(base, name='module-load-step', extra_module_a=.25, coupling_pf=1),
               replace(base, name='ripple-five', ripple5_v=.1, coupling_pf=1),
               replace(base, name='ripple-three', ripple33_v=.05, ripple_hz=1000000, coupling_pf=1),
               replace(base, name='open-filter-witness', c27_scale=0, coupling_pf=5, adc_phase_us=2000),
               replace(base, name='sensor-load-40ma', sensor_load_a=.04, coupling_pf=1),
               replace(base, name='sensor-load-60ma', sensor_load_a=.06, coupling_pf=1),
               replace(base, name='sensor-posttrip-40ma', sensor_load_a=.04, sensor_fuse_ohm=7.5, coupling_pf=1)]
    # Existing short bursts above deliberately fall between scans. These
    # positive exposure fixtures overlap MAP/rail apertures or a whole scan.
    result += [
        replace(base, name='ripple-five-map-aperture', ripple5_v=.1, coupling_pf=1,
                disturbance_us=95160),
        replace(base, name='ripple-five-rail-aperture', ripple5_v=.1, coupling_pf=1,
                disturbance_us=95501, ripple_phase_deg=90),
        replace(base, name='ripple-five-whole-scan', ripple5_v=.1, coupling_pf=1,
                disturbance_us=95000, ripple_cycles=80, ripple_phase_deg=37),
        replace(base, name='ripple-three-map-aperture', ripple33_v=.05, coupling_pf=1,
                disturbance_us=95160, ripple_hz=970000, ripple_cycles=100),
        replace(base, name='ripple-three-rail-aperture', ripple33_v=.05, coupling_pf=1,
                disturbance_us=95501, ripple_hz=970000, ripple_cycles=100, ripple_phase_deg=90),
        replace(base, name='ripple-three-whole-scan', ripple33_v=.05, coupling_pf=1,
                disturbance_us=95000, ripple_hz=970000, ripple_cycles=1000, ripple_phase_deg=37)]
    for low in (1000, 5000):
        result.append(replace(base, name=f'endpoint-{low}', low_us=low, coupling_pf=1))
    return result


def retain_gzip(path):
    body = path.read_bytes()
    target = path.with_suffix(path.suffix + '.gz')
    with target.open('xb') as file:
        file.write(gzip.compress(body, mtime=0))
    assert gzip.decompress(target.read_bytes()) == body
    path.unlink()  # Only this new generated intermediate; exact bytes remain.
    return target


def window_range(time, values, begin_us, end_us):
    lo, hi = begin_us / 1e6, end_us / 1e6
    assert time[0] <= lo <= hi <= time[-1]
    first, last = np.searchsorted(time, [lo, hi], side='left')
    endpoints = [float(np.interp(lo, time, values)), float(np.interp(hi, time, values))]
    middle = values[first:last]
    return [min(endpoints + ([float(np.min(middle))] if len(middle) else [])),
            max(endpoints + ([float(np.max(middle))] if len(middle) else []))]


def ripple_interval(s):
    if not (s.ripple5_v or s.ripple33_v):return None
    entry_nonzero=abs(math.sin(math.radians(s.ripple_phase_deg)))>1e-12
    start=s.disturbance_us+(0 if entry_nonzero else s.disturbance_rise_us)
    end=s.disturbance_us+s.disturbance_rise_us+s.ripple_cycles*1e6/s.ripple_hz+(s.disturbance_rise_us if entry_nonzero else 0)
    return [start,end]


def scan_queries(s, time, arrays):
    """Authored scan timing and ideal point conversion, not an MCP3208 SAR model."""
    queries = []
    interval = ripple_interval(s)
    def overlaps(begin, end):
        return bool(interval and begin < interval[1] and end > interval[0])
    for start in np.arange(s.adc_phase_us, s.duration_ms*1000 - 503, 5000):
        first_sample = float(start - 7*48 + 3)
        codes, samples = [], []
        for channel in range(8):
            when = first_sample + channel*48
            reference = float(np.interp(when/1e6, time, arrays['adc_ref']))
            if not 2.7 <= reference <= 5.5:
                raise ValueError('Outside the declared ideal ADC reference domain; SPI success is not a rail oracle')
            if channel < 4:
                pin = float(np.interp(when/1e6, time, arrays[['map_adc','tps_adc','clt_adc','iat_adc'][channel]]))
            elif channel == 4:pin = 2.5*.6
            elif channel == 5:pin = 2*.6
            elif channel == 6:pin = 14/13
            else:pin = float(np.interp(when/1e6, time, arrays['adc_hold' if s.sample_enabled else 'adc7']))
            codes.append(int(np.clip(math.floor(4096*pin/reference), 0, 4095)))
            acquisition = [when-3, when]
            conversion = [when, when+24] # Authored12-clock observation window; no SAR charge redistribution.
            ref_range = window_range(time, arrays['adc_ref'], acquisition[0], conversion[1])
            samples.append(dict(channel=channel, acquisition_us=acquisition, conversion_us=conversion,
                pin_v=pin, reference_v=reference, reference_range_v=ref_range,
                reference_span_fullscale_lsb=(ref_range[1]-ref_range[0])/reference*4096,
                reference_in_voltage_domain_for_window=2.7<=ref_range[0]<=ref_range[1]<=5.5,
                source_ripple_overlaps_acquisition=overlaps(*acquisition),
                source_ripple_overlaps_conversion=overlaps(*conversion)))
        queries.append(dict(control_us=float(start+500),sampled_us=first_sample,
            adc_ok=1,adc_reference_v=samples[-1]['reference_v'],raw=codes,samples=samples))
    return queries


def run(s, ngspice, control, output, smoke=False, env=None, ngspice_timeout_s=180):
    folder = output / s.name
    folder.mkdir()
    (folder / 'circuit.cir').write_text(deck(s))
    with (folder / 'ngspice.log').open('xb') as log:
        subprocess.run([str(ngspice), '-n', '-b', 'circuit.cir'], cwd=folder, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=ngspice_timeout_s)
    raw = folder / 'values.txt'
    data = np.loadtxt(raw, skiprows=1, ndmin=2)
    assert data.shape[1] == len(COLUMNS) and np.isfinite(data).all()
    log_text = (folder / 'ngspice.log').read_text()
    assert 'simulation(s) aborted' not in log_text and 'Timestep too small' not in log_text
    t = data[:, 0]
    assert np.all(np.diff(t) > 0) and math.isclose(t[-1], s.duration_ms / 1000, rel_tol=0, abs_tol=1e-12)
    arrays = {name: data[:, index] for index, name in enumerate(COLUMNS)}
    assert np.min(arrays['module33']) > 0
    normalized = arrays['gpio'] / arrays['module33']
    queries = scan_queries(s, t, arrays)
    acquisition_hits = [dict(query=n,channel=x['channel'],window_us=x['acquisition_us'])
        for n,q in enumerate(queries) for x in q['samples'] if x['source_ripple_overlaps_acquisition']]
    conversion_hits = [dict(query=n,channel=x['channel'],window_us=x['conversion_us'])
        for n,q in enumerate(queries) for x in q['samples'] if x['source_ripple_overlaps_conversion']]
    sampling = dict(conversion_model='ideal held-signal/instant-reference point at acquisition end; not physical SAR',
        switching_charge_model_channels=[7],ideal_buffered_channels=[4,5,6],
        spi_success_assumed=True,adc_ok_is_not_reference_or_supply_oracle=True,
        conversion_window_model='Authored12-clock24us observation window, not a SAR bit/charge-redistribution computation',
        source_ripple_interval_us=ripple_interval(s),
        physical_cpu_and_spi_timing_qualified=False,queries=queries,
        source_ripple_acquisition_hits=acquisition_hits,source_ripple_conversion_hits=conversion_hits)
    (folder/'sampling.json').write_text(json.dumps(sampling,indent=2,allow_nan=False)+'\n')
    observations = []
    for rising, falling in ([(.75, .25)] if smoke else THRESHOLDS):
        edges = gpio_edges(t, normalized, rising, falling)
        assert all(edges[i][0] <= edges[i + 1][0] for i in range(len(edges) - 1))
        stimulus = [(when, 0, f'E {when:.12f} {high}') for when, high in edges]
        for query in queries:
            when, sampled = query['control_us'], query['sampled_us']
            stimulus.append((when, 1, f"Q {when:.12f} {sampled:.12f} {query['adc_ok']} {query['adc_reference_v']:.17g} " + ' '.join(map(str, query['raw']))))
        text = '\n'.join(row[2] for row in sorted(stimulus)) + '\n'
        stem = f'gpio-{rising}-{falling}'
        (folder / (stem + '.stimulus.txt')).write_text(text)
        for strategy, basis in itertools.product([0] if smoke else [0, 1, 2], ['absolute', 'ratiometric']):
            label = f'{stem}-strategy{strategy}-{basis}'
            path = folder / (label + '.jsonl')
            with path.open('xb') as stdout, path.with_suffix('.log').open('xb') as stderr:
                subprocess.run([str(control), str(strategy), basis, str(folder / label)],
                               input=text.encode(), stdout=stdout, stderr=stderr, check=True)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            assert rows and all(row['data_source'] == 'synthetic_control_observation' and
                                row['physical_execution'] is False for row in rows)
            assert all(not row['controller_faults'] or row['flags'] & 3072 == 3072 for row in rows), 'controller fault did not cut both proposals'
            archive = retain_gzip(path)
            settled = [row for row in rows if row['circuit_clock_phase_us'] == 0 and int(row['control_us']) >= 86000]
            errors = [row['circuit_map_error_kpa'] for row in settled if row['circuit_map_error_kpa'] is not None]
            observations.append(dict(rising_fraction=rising, falling_fraction=falling,
                strategy=strategy, calibration_basis=basis, rows=len(rows), transcript=str(archive.relative_to(output)),
                transcript_sha256=sha(archive), final=rows[-1],
                settled_valid_map_rows=len(errors), faulted_rows=sum(bool(row['controller_faults']) for row in rows),
                settled_valid_map_error_kpa=[min(errors), max(errors)] if errors else None))
    archive = retain_gzip(raw)
    result = dict(status='complete', scenario=asdict(s), raw_rows=len(data), raw_sha256=sha(archive),
        strict_time_order=True,numeric_end_s=float(t[-1]),sampling_file='sampling.json',
        ripple_acquisition_samples=len(acquisition_hits),ripple_conversion_samples=len(conversion_hits),
        voltage_ranges={name: [float(np.min(arrays[name])), float(np.max(arrays[name]))]
                        for name in ['comp5', 'pull33', 'module33', 'sensor5', 'adc7', 'adc_ref', 'in', 'gpio']},
        observations=observations, scope=__doc__, physical_qualification=False)
    (folder / 'results.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--max-step-us', type=float)
    parser.add_argument('--adc-phase-us', type=float)
    parser.add_argument('--minimum-break-s', type=float)
    parser.add_argument('--solver',choices=['sparse','klu'])
    parser.add_argument('--ngspice-timeout-s',type=float,default=180,
                        help='Wall-clock resource limit per circuit; does not change simulation time or tolerances')
    args = parser.parse_args()
    if not math.isfinite(args.ngspice_timeout_s) or not 1<=args.ngspice_timeout_s<=3600:
        raise ValueError('Use a finite solver wall-clock resource limit of1..3600s')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    bound = bind()
    names = [PROFILE, nominal.FRONTEND, CORE, Path('hardware/a5-idle-interface/net_contract.json'), Path('tools/run_flex_circuit.py'),
             Path('tools/run_flex_nonideal.py'), Path('tools/flex_circuit_control.cpp'),
             Path('firmware/main/app.cpp')]
    names += [path.relative_to(ROOT) for path in sorted((ROOT / 'firmware/include/ecu').glob('*.hpp'))]
    before = {str(name): sha(ROOT / name) for name in names}
    for name in names:
        destination = output / 'sources' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    (output / 'source-hashes.json').write_text(json.dumps(before, indent=2) + '\n')
    selected = scenarios()
    if args.max_step_us is not None:selected=[replace(s,max_step_us=args.max_step_us) for s in selected]
    if args.adc_phase_us is not None:selected=[replace(s,adc_phase_us=args.adc_phase_us) for s in selected]
    if args.minimum_break_s is not None:selected=[replace(s,minimum_break_s=args.minimum_break_s) for s in selected]
    if args.solver is not None:selected=[replace(s,solver=args.solver) for s in selected]
    if args.cases:
        if not set(args.cases) <= {s.name for s in selected}:raise ValueError('Unknown scenario')
        selected = [s for s in selected if s.name in args.cases]
    elif args.smoke:selected=selected[:1]
    assert selected and len({s.name for s in selected}) == len(selected)
    for scenario in selected:validate(scenario)
    plan = dict(schema_version=1,selected_cases=[asdict(s) for s in selected],
        resource_limits=dict(ngspice_wall_timeout_s=args.ngspice_timeout_s),
        source_sha256=before,scope=__doc__,physical_qualification=False)
    (output/'matrix-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    results,active = [],None
    stage = 'preparing_toolchain'
    def state(status,error=None):
        report = dict(schema_version=1,status=status,complete=status=='complete',
            selected_case_names=[s.name for s in selected],
            completed_case_names=[r['scenario']['name'] for r in results],
            active_stage=stage,active_case=active,
            failure=None if error is None else dict(type=type(error).__name__,message=str(error)),
            binding=bound,cases=results,source_sha256=before,scope=__doc__,
            model_validity='Conditional equivalents and ideal point conversion; not a physical SAR/CPU/engine model',
            physical_qualification=False)
        temporary=output/'results.json.pending'
        temporary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        os.replace(temporary,output/'results.json')
    state('running')
    try:
        ngspice,env,tool_inputs=prepare_ngspice(args.ngspice,output)
        stage='building_control';state('running');control=build_control(output)
        for scenario in selected:
            active=scenario.name;stage='circuit_and_control_replay';state('running')
            row=run(scenario,ngspice,control,output,args.smoke,env,args.ngspice_timeout_s)
            results.append(row)
            print(json.dumps(dict(case=scenario.name,raw_rows=row['raw_rows'],control_replays=len(row['observations']),ripple_acquisition_samples=row['ripple_acquisition_samples'])),flush=True)
            state('running')
        stage='checking_inputs';active=None
        assert before == {str(name):sha(ROOT/name) for name in names},'Project source changed during run'
        assert all(sha(Path(name))==value for name,value in tool_inputs.items()),'Tool input changed during run'
        assert len(results)==len(selected)
        stage='finished';state('complete')
    except BaseException as error:
        state('failed',error);raise



if __name__ == '__main__':
    main()
