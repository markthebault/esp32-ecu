"""Pack the compact leaded frontend around fixed U18 on an unrouted A6 copy.

Courtyard and direct-distance screening only; no routing or parasitic bound.
"""
import math
import random
import hashlib
import json
from pathlib import Path
import subprocess
import pcbnew as p
from build_a5_idle_interface import box, overlaps
from pack_a6 import ANTENNA, GAP, expanded, subtract

MOVABLE = {f'R{i}' for i in range(157, 166)} | {'C158', 'C159', 'C160', 'C164', 'D213'}
GOALS = {
    'C160': [('1', 'U18', '8', 4, 60)],
    'R160': [('1', 'U18', '1', 6, 40), ('2', 'U18', '3', 6, 40)],
    'C159': [('1', 'U18', '2', 7, 30)],
    'R158': [('2', 'U18', '3', 7, 20)],
    'R159': [('1', 'U18', '3', 7, 20)],
    'R163': [('2', 'U18', '1', 20, 2)],
    'C164': [('1', 'R163', '1', 4, 80)],
    'R162': [('1', 'U18', '2', 10, 10)],
    'R161': [('2', 'U18', '2', 12, 5)],
    'C158': [('1', 'R158', '1', 8, 5), ('1', 'D213', '1', 6, 2)],
    'D213': [('1', 'R158', '1', 8, 10)],
    'R157': [('2', 'R158', '1', 15, 1)],
    'R164': [('1', 'U18', '1', 25, 2)],
    'R165': [('1', 'R164', '2', 10, 2)],
}


def pack_analog_greedy(board, preferred, attempts=64):
    assert not board.GetTracks()
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    assert MOVABLE <= fps.keys()
    fixed = set(fps) - MOVABLE
    anchors = {ref: (f.GetPosition().x, f.GetPosition().y, f.GetOrientationDegrees())
               for ref, f in fps.items() if ref in fixed}
    assert not any(overlaps(box(fps['U18']), box(fps[ref]), GAP - 1e-5)
                   for ref in fixed if ref != 'U18'), 'Revised U18 overlaps a fixed device'
    base = [(11, 11, 129, 129)]
    for ref in sorted(fixed):
        base = subtract(base, expanded(box(fps[ref])))
    base = subtract(base, expanded(ANTENNA))
    offsets, pad_offsets = {}, {}
    for ref in sorted(MOVABLE):
        fp = fps[ref]
        offsets[ref], pad_offsets[ref] = {}, {}
        for angle in (0, 90, 180, 270):
            fp.SetPosition(p.VECTOR2I(0, 0))
            fp.SetOrientationDegrees(angle)
            offsets[ref][angle] = box(fp)
            pad_offsets[ref][angle] = {q.GetNumber(): (q.GetPosition().x / 1e6,
                                                       q.GetPosition().y / 1e6) for q in fp.Pads()}

    def pin_xy(ref, pin):
        q = next(q for q in fps[ref].Pads() if q.GetNumber() == pin)
        return q.GetPosition().x / 1e6, q.GetPosition().y / 1e6

    def set_position(ref, candidate):
        _, x, y, angle, _ = candidate
        fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x), p.FromMM(y)))
        fps[ref].SetOrientationDegrees(angle)

    failures = []
    for seed in range(attempts):
        rng, free, placed = random.Random(seed), list(base), {}

        def candidates(ref, rectangles):
            result = []
            goals = [(pin, pin_xy(owner, owner_pin), maximum, weight)
                     for pin, owner, owner_pin, maximum, weight in GOALS[ref]]
            for angle, offset in offsets[ref].items():
                width, height = offset[2] - offset[0] + GAP, offset[3] - offset[1] + GAP
                wishes = [(preferred[ref][0], preferred[ref][1])]
                for pin, target, _, _ in goals:
                    dx, dy = pad_offsets[ref][angle][pin]
                    wishes.append((target[0] - dx, target[1] - dy))
                weight_sum = sum(g[3] for g in goals)
                wishes.append((sum((target[0] - pad_offsets[ref][angle][pin][0]) * weight
                                   for pin, target, _, weight in goals) / weight_sum,
                               sum((target[1] - pad_offsets[ref][angle][pin][1]) * weight
                                   for pin, target, _, weight in goals) / weight_sum))
                for rect in rectangles:
                    if width > rect[2] - rect[0] + 1e-8 or height > rect[3] - rect[1] + 1e-8:
                        continue
                    points = {(rect[0], rect[1]), (rect[2] - width, rect[1]),
                              (rect[0], rect[3] - height), (rect[2] - width, rect[3] - height)}
                    for wx, wy in wishes:
                        x = min(max(wx + offset[0] - GAP / 2, rect[0]), rect[2] - width)
                        y = min(max(wy + offset[1] - GAP / 2, rect[1]), rect[3] - height)
                        points.add((x, y))
                        points.update(((x, rect[1]), (x, rect[3] - height),
                                       (rect[0], y), (rect[2] - width, y)))
                    for left, top in points:
                        x, y = left + GAP / 2 - offset[0], top + GAP / 2 - offset[1]
                        distances = [math.dist((x + pad_offsets[ref][angle][pin][0],
                                               y + pad_offsets[ref][angle][pin][1]), target)
                                     for pin, target, _, _ in goals]
                        if any(d > goal[2] + 1e-8 for d, goal in zip(distances, goals)):
                            continue
                        score = sum(weight * d * d for d, (_, _, _, weight) in zip(distances, goals))
                        score += .08 * math.dist((x, y), preferred[ref]) ** 2
                        # Vary tight packing and near-equivalent placements,
                        # keeping the hard locality and clearance limits.
                        score += rng.uniform(0, (seed % 8) * 2)
                        result.append((score, x, y, angle,
                                       (left, top, left + width, top + height)))
            result.sort()
            return result

        order = ['C160', 'R160', 'C159', 'R159', 'R158', 'R163', 'C164',
                 'R162', 'R161', 'D213', 'C158', 'R157', 'R164', 'R165']
        if seed % 3 == 1:
            order[3:5] = ['R158', 'R159']
        if seed % 3 == 2:
            order[:3] = ['R160', 'C160', 'C159']
        failed = None
        for ref in order:
            if ref in placed:
                continue
            options = candidates(ref, free)
            if not options:
                failed = ref
                break
            chosen = options[min(seed // 16, len(options) - 1)]
            if ref == 'R163':
                paired = []
                for possibility in options[:24]:
                    set_position(ref, possibility)
                    second = candidates('C164', subtract(free, possibility[4]))
                    if second:
                        paired.append((possibility[0] + second[0][0], possibility, second[0]))
                if not paired:
                    failed = 'R163/C164'
                    break
                _, chosen, cap = min(paired)
                set_position('C164', cap)
                placed['C164'] = cap
                free = subtract(free, cap[4])
            set_position(ref, chosen)
            placed[ref] = chosen
            free = subtract(free, chosen[4])
        if failed:
            failures.append(dict(seed=seed, failed=failed, placed=len(placed)))
            print('Compact packing', failures[-1], flush=True)
            continue
        for ref, (x, y, angle) in anchors.items():
            fp = fps[ref]
            assert (fp.GetPosition().x, fp.GetPosition().y, fp.GetOrientationDegrees()) == (x, y, angle)
        bounds = {ref: box(fp) for ref, fp in fps.items()}
        for ref in MOVABLE:
            assert not overlaps(bounds[ref], ANTENNA, 0)
            assert min(bounds[ref][:2]) >= 11 and max(bounds[ref][2:]) <= 129
            assert not any(overlaps(bounds[ref], bb, GAP - 1e-5)
                           for other, bb in bounds.items() if other != ref), ref
        distances = {f'{ref}.{pin}_to_{owner}.{target_pin}':
                     math.dist(pin_xy(ref, pin), pin_xy(owner, target_pin))
                     for ref in sorted(MOVABLE)
                     for pin, owner, target_pin, _, _ in GOALS[ref]}
        return dict(seed=seed, failures=failures, positions={ref: dict(
            xy_mm=[fps[ref].GetPosition().x / 1e6, fps[ref].GetPosition().y / 1e6],
            angle_deg=fps[ref].GetOrientationDegrees()) for ref in sorted(MOVABLE)},
            direct_pin_distances_mm=distances, fixed_references_unchanged=sorted(fixed),
            courtyard_gap_mm=GAP, full_antenna_rectangle_mm=ANTENNA,
            scope=__doc__, routing_required=True, physical_fit_qualified=False)
    raise RuntimeError('No compact frontend candidate: ' + str(failures[-8:]))


def pack_analog(board, preferred, attempts=64, problem_path=None, solver_seconds=120):
    """Use a complete constraint model for mutually competing local parts."""
    assert not board.GetTracks() and problem_path is not None
    problem_path = Path(problem_path)
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    fixed = set(fps) - MOVABLE
    assert not any(overlaps(box(fps['U18']), box(fps[ref]), GAP - 1e-5)
                   for ref in fixed if ref != 'U18')
    anchors = {ref: (fp.GetPosition().x, fp.GetPosition().y, fp.GetOrientationDegrees())
               for ref, fp in fps.items() if ref in fixed}
    problem = dict(schema=2, bounds_mm=[11, 11, 129, 129], gap_mm=GAP,
        antenna_mm=ANTENNA, fixed={ref: dict(court_mm=box(fps[ref]),
            absolute_pads_mm={q.GetNumber(): [q.GetPosition().x / 1e6, q.GetPosition().y / 1e6]
                              for q in fps[ref].Pads()}) for ref in sorted(fixed)},
        movable={}, goals=GOALS, qualification=__doc__)
    for ref in sorted(MOVABLE):
        fp = fps[ref]
        courts, pads = {}, {}
        for angle in (0, 90, 180, 270):
            fp.SetPosition(p.VECTOR2I(0, 0))
            fp.SetOrientationDegrees(angle)
            courts[angle] = box(fp)
            pads[angle] = {q.GetNumber(): [q.GetPosition().x / 1e6, q.GetPosition().y / 1e6]
                           for q in fp.Pads()}
        problem['movable'][ref] = dict(rotated_courts_mm=courts, rotated_pads_mm=pads,
                                      preferred_origin_mm=preferred[ref])
    problem_path.write_text(json.dumps(problem, indent=2) + '\n')
    solution = problem_path.with_name('compact-placement-solution.json')
    solver = Path(__file__).resolve().parents[1] / 'tools/solve_a6_analog_placement.py'
    command = ['uv', 'run', '--offline', '--python', '3.12', '--with', 'ortools==9.14.6206',
               'python', str(solver), str(problem_path), str(solution),
               '--seconds', str(solver_seconds), '--grid-um', '1', '--first']
    with problem_path.with_name('compact-placement-solver.log').open('xb') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                timeout=solver_seconds + 60)
    if result.returncode or not solution.exists():
        raise RuntimeError('Constraint placement failed; inspect compact-placement-solver.log')
    answer = json.loads(solution.read_text())
    assert answer['status'] in ('OPTIMAL', 'FEASIBLE') and set(answer['positions']) == MOVABLE
    assert answer['problem_sha256'] == hashlib.sha256(problem_path.read_bytes()).hexdigest()
    for ref, row in answer['positions'].items():
        fps[ref].SetPosition(p.VECTOR2I(p.FromMM(row['xy_mm'][0]), p.FromMM(row['xy_mm'][1])))
        fps[ref].SetOrientationDegrees(row['angle_deg'])
    for ref, (x, y, angle) in anchors.items():
        fp = fps[ref]
        assert (fp.GetPosition().x, fp.GetPosition().y, fp.GetOrientationDegrees()) == (x, y, angle)
    boxes = {ref: box(fp) for ref, fp in fps.items()}
    for ref in MOVABLE:
        assert min(boxes[ref][:2]) >= 11 and max(boxes[ref][2:]) <= 129
        assert not overlaps(boxes[ref], ANTENNA, GAP - 1e-5)
        assert not any(overlaps(boxes[ref], bb, GAP - 1e-5)
                       for other, bb in boxes.items() if other != ref), ref
    def pin_xy(ref, pin):
        q = next(q for q in fps[ref].Pads() if q.GetNumber() == pin)
        return q.GetPosition().x / 1e6, q.GetPosition().y / 1e6
    distances = {}
    for ref, rows in GOALS.items():
        for pin, owner, owner_pin, maximum, _ in rows:
            distance = math.dist(pin_xy(ref, pin), pin_xy(owner, owner_pin))
            assert distance <= maximum, (ref, pin, owner, owner_pin, distance, maximum)
            distances[f'{ref}.{pin}_to_{owner}.{owner_pin}'] = distance
    return dict(method='OR-Tools hard courtyard and pin-distance constraints, native recheck',
        positions=answer['positions'], direct_pin_distances_mm=distances,
        fixed_references_unchanged=sorted(fixed), courtyard_gap_mm=GAP,
        full_antenna_rectangle_mm=ANTENNA, solver_command=command,
        problem_sha256=hashlib.sha256(problem_path.read_bytes()).hexdigest(),
        solver_sha256=hashlib.sha256(solver.read_bytes()).hexdigest(),
        solution_sha256=hashlib.sha256(solution.read_bytes()).hexdigest(),
        scope=__doc__, routing_required=True, physical_fit_qualified=False)
