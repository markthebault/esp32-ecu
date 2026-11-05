#!/usr/bin/env python3
"""Constrained placement for compact leaded A6 analog parts, not Cu or fit.

Consumes the native integer-geometry problem exported by pack_a6_analog.py.
NoOverlap2D, explicit fixed obstacles and squared pin distances are hard
constraints. Every result must be rechecked with native KiCad geometry.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import ortools
from ortools.sat.python import cp_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('problem', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--grid-um', type=int, default=1)
    parser.add_argument('--first', action='store_true')
    parser.add_argument('--explain', action='store_true', help='Return an infeasible goal core, retaining every geometric constraint')
    parser.add_argument('--minimize-core', action='store_true')
    args = parser.parse_args()
    assert not args.output.exists() and args.grid_um in (1, 5, 10, 25, 50)
    raw = args.problem.read_bytes()
    data = json.loads(raw)
    assert data['schema'] == 2
    scale = 1000 / args.grid_um
    integer = lambda value: round(value * scale)
    half_gap = data['gap_mm'] / 2
    model = cp_model.CpModel()
    xs, ys, variables, costs = [], [], {}, []
    left, top, right, bottom = [integer(v) for v in data['bounds_mm']]
    obstacles = [row['court_mm'] for row in data['fixed'].values()] + [data['antenna_mm']]

    def padded(bounds):
        a = math.floor((bounds[0] - half_gap) * scale + 1e-7)
        b = math.floor((bounds[1] - half_gap) * scale + 1e-7)
        c = math.ceil((bounds[2] + half_gap) * scale - 1e-7)
        d = math.ceil((bounds[3] + half_gap) * scale - 1e-7)
        return a, b, c - a, d - b

    for ref, row in data['movable'].items():
        x = model.new_int_var(left, right, ref + '_x')
        y = model.new_int_var(top, bottom, ref + '_y')
        variants = []
        for angle in (0, 90, 180, 270):
            a, b, width, height = padded(row['rotated_courts_mm'][str(angle)])
            present = model.new_bool_var(ref + '_' + str(angle))
            xs.append(model.new_optional_fixed_size_interval_var(x, width, present, ref + str(angle) + '_x'))
            ys.append(model.new_optional_fixed_size_interval_var(y, height, present, ref + str(angle) + '_y'))
            model.add(x + width <= right).only_enforce_if(present)
            model.add(y + height <= bottom).only_enforce_if(present)
            for index, obstacle in enumerate(obstacles):
                ox, oy, ow, oh = padded(obstacle)
                # Do not compare fixed obstacles with each other: their source
                # geometry is unchanged; integer padding can overlap by1um.
                choices = [model.new_bool_var(f'{ref}_{angle}_avoid_{index}_{i}') for i in range(4)]
                model.add(x + width <= ox).only_enforce_if(choices[0])
                model.add(x >= ox + ow).only_enforce_if(choices[1])
                model.add(y + height <= oy).only_enforce_if(choices[2])
                model.add(y >= oy + oh).only_enforce_if(choices[3])
                model.add_bool_or([present.Not(), *choices])
            variants.append(dict(angle=angle, present=present, offset=(a, b), shape=(width, height)))
        model.add_exactly_one(v['present'] for v in variants)
        variables[ref] = (x, y, variants)
    model.add_no_overlap_2d(xs, ys)

    def pad_expression(ref, pin):
        if ref in data['fixed']:
            return tuple(integer(v) for v in data['fixed'][ref]['absolute_pads_mm'][pin])
        x, y, variants = variables[ref]
        values = []
        for variant in variants:
            point = data['movable'][ref]['rotated_pads_mm'][str(variant['angle'])][pin]
            values.append((integer(point[0]) - variant['offset'][0],
                           integer(point[1]) - variant['offset'][1], variant['present']))
        return (x + sum(dx * present for dx, _, present in values),
                y + sum(dy * present for _, dy, present in values))

    assumptions, assumption_vars = {}, {}
    for ref, goals in data['goals'].items():
        for index, (pin, owner, owner_pin, maximum, weight) in enumerate(goals):
            a, b = pad_expression(ref, pin), pad_expression(owner, owner_pin)
            limit = integer(maximum) - 2
            domain = integer(260) if args.explain else limit
            dx = model.new_int_var(-domain, domain, f'{ref}_goal{index}_dx')
            dy = model.new_int_var(-domain, domain, f'{ref}_goal{index}_dy')
            model.add(dx == a[0] - b[0])
            model.add(dy == a[1] - b[1])
            dx2 = model.new_int_var(0, domain * domain, f'{ref}_goal{index}_dx2')
            dy2 = model.new_int_var(0, domain * domain, f'{ref}_goal{index}_dy2')
            model.add_multiplication_equality(dx2, [dx, dx])
            model.add_multiplication_equality(dy2, [dy, dy])
            constraint = model.add(dx2 + dy2 <= limit * limit)
            if args.explain:
                enabled = model.new_bool_var(f'{ref}.{pin}_to_{owner}.{owner_pin}')
                assumptions[enabled.index] = dict(from_pin=[ref, pin], to_pin=[owner, owner_pin], maximum_mm=maximum)
                assumption_vars[enabled.index] = enabled
                model.add_assumption(enabled)
                constraint.only_enforce_if(enabled)
                for value in (dx, dy):
                    model.add(value >= -limit).only_enforce_if(enabled)
                    model.add(value <= limit).only_enforce_if(enabled)
            costs.extend((int(weight) * dx2, int(weight) * dy2))
    if not args.explain:
        model.minimize(sum(costs))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.seconds
    solver.parameters.num_search_workers = 1 if args.explain else 4
    solver.parameters.random_seed = 1
    solver.parameters.log_search_progress = True
    solver.parameters.stop_after_first_solution = args.first
    status = solver.solve(model)
    assert args.problem.read_bytes() == raw
    report = dict(status=solver.status_name(status), ortools_version=ortools.__version__,
        problem_sha256=hashlib.sha256(raw).hexdigest(), grid_um=args.grid_um,
        wall_seconds=solver.wall_time, positions={}, scope=__doc__,
        manufacturing_release=False, physical_fit_qualified=False)
    if args.explain and status == cp_model.INFEASIBLE:
        core = list(solver.sufficient_assumptions_for_infeasibility())
        probes = []
        if args.minimize_core:
            for item in list(core):
                trial = [i for i in core if i != item]
                model.clear_assumptions()
                model.add_assumptions(assumption_vars[i] for i in trial)
                solver.parameters.max_time_in_seconds = min(args.seconds, 10)
                probe_status = solver.solve(model)
                probes.append(dict(omitted=assumptions[item], status=solver.status_name(probe_status)))
                if probe_status == cp_model.INFEASIBLE:
                    core = trial
        report['infeasible_goal_core'] = [assumptions[i] for i in core]
        report['core_reduction_probes'] = probes
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        report['objective'] = solver.objective_value
        for ref, (x, y, variants) in variables.items():
            variant = next(v for v in variants if solver.boolean_value(v['present']))
            report['positions'][ref] = dict(xy_mm=[(solver.value(x) - variant['offset'][0]) / scale,
                                                  (solver.value(y) - variant['offset'][1]) / scale],
                                           angle_deg=variant['angle'])
    with args.output.open('x') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps(dict(status=report['status'], placed=len(report['positions']))), flush=True)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
