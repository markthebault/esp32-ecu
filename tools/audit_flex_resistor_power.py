#!/usr/bin/env python3
"""Forecast compact resistor stress from an existing conditional circuit matrix.

Reads exact deck resistances and retained raw voltage rows. The new package
power references are P70 values, not an assembled derating or surge rating.
An old matrix does not verify the added bypass or a new physical layout.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import numpy as np

COLUMNS = {'0': None, 'flex_raw': 2, 'flex_in': 3, 'flex_ref': 4, 'flex_cmp': 5,
           'gpio': 6, 'rail33': 7, 'rail5': 8, 'flex_bias': 9,
           'flex_pull_mid': 10, 'flex_input_mid': 11, 'flex_pull_mid2': 15}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, ('Duplicate JSON key', key)
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profile = read_json(args.profile)
    old_path = args.matrix / 'sources/hardware/flex-input/frontend.json'
    old = read_json(old_path)
    assert profile['parent_revision']['source_sha256'] == sha(old_path)
    resistors = {row['ref']: row for row in profile['parts'] if 'ohm' in row}
    old_parts = {row['ref']: row for row in old['parts']}
    parts = {row['ref']: row for row in profile['parts']}
    assert len(parts) == len(profile['parts']) and set(parts) == set(old_parts) | {'C164'}
    for ref, part in old_parts.items():
        assert parts[ref]['pins'] == part['pins'], ('Changed literal graph', ref)
        if 'farad' in part:
            assert parts[ref]['farad'] == part['farad'], ref
    assert parts['C164']['pins'] == {'1': '+3V3', '2': 'GND'} and parts['C164']['farad'] == 1e-7
    assert {ref: row['ohm'] for ref, row in resistors.items()} == {
        row['ref']: row['ohm'] for row in old['parts'] if 'ohm' in row}
    ratings = {ref: .4 if 157 <= int(ref[1:]) <= 165 else .6 for ref in resistors}
    for ref, row in resistors.items():
        assert row['value'] == f"{row['ohm']:g}R 1% {ratings[ref]:.1f}W", ('Unsupported rating label', ref)
        if ratings[ref] == .4:
            assert row['mounting']['series'] == 'Vishay MRS16'
            assert row['mounting']['footprint'] == 'R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical'
    peaks = {ref: dict(power_w=-1, voltage_v=-1, current_a=-1) for ref in resistors}
    sources, rows = {}, 0
    for data_path in sorted(args.matrix.glob('*/values.txt.gz')):
        folder = data_path.parent
        deck_path = folder / 'circuit.cir'
        deck = deck_path.read_text()
        values = np.loadtxt(gzip.open(data_path, 'rt'), skiprows=1, ndmin=2)
        assert values.shape[1] == 16 and np.isfinite(values).all()
        rows += len(values)
        records = {match[1]: (match[2], match[3], float(match[4])) for match in re.finditer(
            r'^(R1\d\d)\s+(\w+)\s+(\w+)\s+([-+0-9.eE]+)\s*$', deck, re.M)}
        assert resistors.keys() <= records.keys()
        for ref in resistors:
            a, b, resistance = records[ref]
            assert resistance > 0 and a in COLUMNS and b in COLUMNS
            va = 0 if COLUMNS[a] is None else values[:, COLUMNS[a]]
            vb = 0 if COLUMNS[b] is None else values[:, COLUMNS[b]]
            voltage = np.abs(va - vb)
            peak = float(np.max(voltage))
            power = peak * peak / resistance
            if power > peaks[ref]['power_w']:
                peaks[ref] = dict(power_w=power, voltage_v=peak, current_a=peak / resistance,
                                  case=folder.name, actual_resistance_ohm=resistance)
        sources[folder.name] = dict(deck_sha256=sha(deck_path), raw_sha256=sha(data_path))
    assert len(sources) == 62
    for ref, result in peaks.items():
        reference = ratings[ref]
        result.update(nominal_P70_reference_w=reference,
                      fraction_of_nominal_P70= result['power_w'] / reference,
                      below_nominal_P70_reference=result['power_w'] < reference)
    result = dict(matrix=str(args.matrix.resolve()), profile_sha256=sha(args.profile),
        parent_profile_sha256=sha(old_path), script_sha256=sha(Path(__file__)),
        raw_rows=rows, case_count=len(sources), case_source_hashes=sources, peaks=peaks,
        all_below_nominal_P70_reference=all(row['below_nominal_P70_reference'] for row in peaks.values()),
        scope=__doc__, complete_new_profile_verified=False,
        assembled_derating_pulse_I2t_or_thermal_qualified=False, manufacturing_release=False)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(dict(cases=len(sources), raw_rows=rows,
        compact_peak_w=max(peaks['R%d' % i]['power_w'] for i in range(157, 166)),
        all_below_nominal_P70_reference=result['all_below_nominal_P70_reference'])))
    if not result['all_below_nominal_P70_reference']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
