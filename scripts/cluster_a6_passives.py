#!/usr/bin/env python3
"""Improve electrical locality by swapping identical passive footprint slots.

Only a fresh unrouted A6 copy is changed. This preserves occupied courtyard
envelopes and all fixed components. The wire-length objective is a placement
heuristic, not signal-integrity, copper, timing, thermal or physical acceptance.
"""

import argparse
import hashlib
import json
import math
import random
import shutil
from collections import defaultdict
from pathlib import Path

import pcbnew as pcb

from build_a5_idle_interface import box, overlaps
from pack_a6 import ANTENNA, BYPASS
from place_a6_back import courtyard


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=100000)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--initial-swap', action='append', default=[],
                        help='Optional identical-footprint REF,REF slot swap '
                             'before passive optimization; repeat for bypasses')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    assert not output.exists(), 'Choose a fresh output'
    source_hashes = {str(p.relative_to(source)): sha(p) for p in source.rglob('*')
                     if p.is_file() and p.suffix not in ('.kicad_prl', '.lck')}
    contract = json.loads((source / 'net_contract.json').read_text())
    assert contract['revision'] == 'A6-FLEX-RGB-HOLD'
    board = pcb.LoadBoard(str(source / 'esp32-ecu.kicad_pcb'))
    assert not board.GetTracks(), 'Routed work cannot be repacked'
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    groups = defaultdict(list)
    locations, pin_coordinates, nets, membership = {}, {}, defaultdict(list), defaultdict(set)
    for ref, fp in fps.items():
        locations[ref] = (fp.GetPosition().x, fp.GetPosition().y,
                          fp.GetOrientationDegrees())
        pin_coordinates[ref] = {p.GetNumber(): (p.GetPosition().x / 1e6,
                                               p.GetPosition().y / 1e6)
                                for p in fp.Pads() if p.GetNumber()}
        if ref.startswith(('R', 'C', 'D')) and ref not in ('R150', 'D1'):
            groups[str(fp.GetFPID().GetLibItemName())].append(ref)
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not pad.GetNumber() or not net or net.startswith('unconnected-'):
                continue
            nets[net].append((ref, pad.GetNumber()))
            membership[ref].add(net)
    groups = [sorted(groups[k]) for k in sorted(groups) if len(groups[k]) > 1]
    # Only explicit named power/ground nets are excluded. Signal weights make
    # comparator feedback/reference locality more important than generic HPWL.
    rails = {'GND', 'CHASSIS', '+5V', '+3V3', 'SENSOR_5V', 'VBAT_FUSED',
             'VIN_PROT', 'VIN_FILTERED', 'FLEX_12V', 'RUN_5V'}
    nets = {n: nets[n] for n in sorted(nets)
            if n not in rails and len(nets[n]) > 1}
    critical = {'FLEX_IN', 'FLEX_REF', 'FLEX_CMP', 'FLEX_INPUT_MID'}
    assignment = {ref: ref for ref in fps}
    for pair in args.initial_swap:
        a, b = pair.split(',')
        assert a in fps and b in fps
        assert a.startswith(('U', 'C')) and b.startswith(('U', 'C'))
        assert {a, b}.isdisjoint({'U1', 'U2', 'U3'})
        assert str(fps[a].GetFPID().GetLibItemName()) == str(fps[b].GetFPID().GetLibItemName())
        assignment[a], assignment[b] = assignment[b], assignment[a]

    def position(ref, pin):
        return pin_coordinates[assignment[ref]][pin]

    def net_cost(net):
        points = [position(ref, pin) for ref, pin in nets[net]]
        span = sum(max(p[axis] for p in points) - min(p[axis] for p in points)
                   for axis in (0, 1))
        return span * (20 if net in critical else 1)

    def bypass_distance(ref):
        owner, pin = BYPASS[ref]
        return math.dist(position(ref, '1'), position(owner, pin))

    bypass = {ref for ref in BYPASS if ref in fps}
    # Immediate comparator summing/reference connections merit short local
    # loops. These are placement objectives, with resulting distances exposed
    # for review rather than treated as a validated parasitic/timing bound.
    local = {
        'R158': [('2', '3', 2)], 'R159': [('1', '3', 2)],
        'R160': [('1', '1', 6), ('2', '3', 6)],
        'R161': [('2', '2', 3)], 'R162': [('1', '2', 3)],
        'R163': [('2', '1', 1)], 'C159': [('1', '2', 3)],
    }

    def local_cost(ref):
        result = 0
        if ref in bypass:
            result += 2 * bypass_distance(ref) ** 2
        for pin, owner_pin, weight in local.get(ref, []):
            result += weight * math.dist(position(ref, pin), position('U18', owner_pin)) ** 2
        return result

    def local_distances():
        return {ref + ':' + pin + '-U18:' + owner_pin:
                math.dist(position(ref, pin), position('U18', owner_pin))
                for ref, entries in sorted(local.items())
                for pin, owner_pin, _ in entries}

    assert all(bypass_distance(ref) <= 13.000001 for ref in bypass)
    costs = {net: net_cost(net) for net in nets}
    local_costs = {ref: local_cost(ref) for ref in sorted(bypass | local.keys())}
    initial_cost = sum(costs.values()) + sum(local_costs.values())
    initial_distances = {ref: bypass_distance(ref) for ref in sorted(bypass)}
    initial_local_distances = local_distances()
    initial_spans = {n: net_cost(n) / 20 for n in critical if n in nets}
    best_cost, best = initial_cost, dict(assignment)
    rng, accepted = random.Random(args.seed), 0
    for iteration in range(args.iterations):
        group = rng.choice(groups)
        a, b = rng.sample(group, 2)
        affected = sorted((membership[a] | membership[b]) & nets.keys())
        local_affected = sorted({a, b} & local_costs.keys())
        before = sum(costs[n] for n in affected) + sum(local_costs[r] for r in local_affected)
        assignment[a], assignment[b] = assignment[b], assignment[a]
        if any(bypass_distance(ref) > 13.000001 for ref in (a, b) if ref in bypass):
            assignment[a], assignment[b] = assignment[b], assignment[a]
            continue
        updates = {n: net_cost(n) for n in affected}
        local_updates = {r: local_cost(r) for r in local_affected}
        delta = sum(updates.values()) + sum(local_updates.values()) - before
        temperature = .02 + 80 * (1 - iteration / args.iterations) ** 3
        if delta <= 0 or rng.random() < math.exp(-delta / temperature):
            costs.update(updates)
            local_costs.update(local_updates)
            accepted += 1
            current = sum(costs.values()) + sum(local_costs.values())
            if current < best_cost:
                best_cost, best = current, dict(assignment)
        else:
            assignment[a], assignment[b] = assignment[b], assignment[a]
    assignment = best
    assert best_cost <= initial_cost
    for ref, slot in assignment.items():
        x, y, angle = locations[slot]
        fps[ref].SetPosition(pcb.VECTOR2I(x, y))
        fps[ref].SetOrientationDegrees(angle)
    # Exact same envelopes must remain occupied, with no new overlap or entry
    # into the provisional antenna region. Verify against native integer data.
    for ref, slot in assignment.items():
        expected = pin_coordinates[slot]
        actual = {p.GetNumber(): (p.GetPosition().x / 1e6, p.GetPosition().y / 1e6)
                  for p in fps[ref].Pads() if p.GetNumber()}
        assert actual == expected, (ref, slot)
    courts = {ref: courtyard(fp) for ref, fp in fps.items()}
    for ref, bounds in courts.items():
        if assignment[ref] != ref:
            assert not overlaps(bounds, ANTENNA, 0), ref
        for other, ob in courts.items():
            if ref < other and fps[ref].GetLayer() == fps[other].GetLayer():
                assert not overlaps(bounds, ob, 0), (ref, other)
    shutil.copytree(source, output, ignore=shutil.ignore_patterns('*.kicad_prl', '*.lck', '*~'))
    # Plane fills belong to the old pad/net positions. Rebuild them instead
    # of leaving electrically stale copper in the new geometry candidate.
    pcb.ZONE_FILLER(board).Fill(board.Zones())
    pcb.SaveBoard(str(output / 'esp32-ecu.kicad_pcb'), board)
    for row in contract['parts']:
        x, y, angle = locations[assignment[row['ref']]]
        row.update(placed_xy_mm=[x / 1e6, y / 1e6], placed_angle_deg=angle)
    contract['status'] = 'LOCALITY_OPTIMIZED_UNROUTED_DRAFT_NOT_FOR_FABRICATION'
    (output / 'net_contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    evidence = dict(
        source_directory=str(source), source_sha256=source_hashes,
        seed=args.seed, iterations=args.iterations, accepted_swaps=accepted,
        initial_swaps=args.initial_swap,
        objective_before=initial_cost, objective_after=best_cost,
        critical_net_HPWL_mm_before=initial_spans,
        critical_net_HPWL_mm_after={n: net_cost(n) / 20 for n in critical if n in nets},
        local_comparator_pin_distance_mm_before=initial_local_distances,
        local_comparator_pin_distance_mm_after=local_distances(),
        bypass_supply_pin_distance_mm_before=initial_distances,
        bypass_supply_pin_distance_mm_after={r: bypass_distance(r) for r in sorted(bypass)},
        assignment_to_original_slot={r: s for r, s in sorted(assignment.items()) if r != s},
        scope=__doc__, manufacturing_release=False)
    (output / 'locality-optimization.json').write_text(json.dumps(evidence, indent=2) + '\n')
    assert all(sha(source / p) == digest for p, digest in source_hashes.items())
    print(json.dumps({k: evidence[k] for k in (
        'objective_before', 'objective_after', 'critical_net_HPWL_mm_before',
        'critical_net_HPWL_mm_after')}, indent=2))


if __name__ == '__main__':
    main()
