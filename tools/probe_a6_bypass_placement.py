#!/usr/bin/env python3
"""Screen compact leaded bypass placement on the back of an A6 draft.

Nominal two-dimensional screening only. No copper, assembled lead/tail, heat,
case fit or physical qualification follows. The input board is never saved.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from place_a6_back import courtyard
from pack_a6 import ANTENNA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pitch', type=float, choices=(2.54, 5.08), required=True)
    parser.add_argument('--grid', type=float, default=.1)
    parser.add_argument('--radius', type=float, default=15)
    parser.add_argument('--target', action='append', help='REF:PIN; repeat for multiple target pads')
    args = parser.parse_args()
    assert .05 <= args.grid <= .5 and args.radius > 0
    board = p.LoadBoard(str(args.board))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    targets = [tuple(value.split(':')) for value in args.target] if args.target else [('U18', '8'), ('R163', '1')]
    assert all(len(value) == 2 for value in targets)
    front_courts, back_courts, tails, supports = [], [], [], []
    for fp in fps.values():
        (back_courts if fp.GetLayer() == p.B_Cu else front_courts).append(courtyard(fp))
        if fp.GetReference().startswith('H'):
            supports.append((fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6))
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            tails.append((bb.GetX() / 1e6 - .5, bb.GetY() / 1e6 - .5,
                          bb.GetRight() / 1e6 + .5, bb.GetBottom() / 1e6 + .5))
    rows = []
    # 0.8mm finished-hole target, 1.4mm copper pads, 0.25mm nominal courtyard.
    local = [(-.95, -1.55), (args.pitch + .95, -1.55),
             (args.pitch + .95, 1.55), (-.95, 1.55)]
    for ref, pin in targets:
        pad = next(q for q in fps[ref].Pads() if q.GetNumber() == pin)
        target = (pad.GetPosition().x / 1e6, pad.GetPosition().y / 1e6)
        xx, yy = np.meshgrid(np.arange(max(11, target[0] - args.radius),
                                      min(129, target[0] + args.radius) + args.grid / 2, args.grid),
                             np.arange(max(11, target[1] - args.radius),
                                      min(129, target[1] + args.radius) + args.grid / 2, args.grid))
        xx, yy = xx.ravel(), yy.ravel()
        candidates = []
        for angle in range(0, 360, 45):
            theta = math.radians(angle)
            u, v = (math.cos(theta), -math.sin(theta)), (math.sin(theta), math.cos(theta))
            polygon = [(a * u[0] + b * v[0], a * u[1] + b * v[1]) for a, b in local]
            rect = (min(q[0] for q in polygon), min(q[1] for q in polygon),
                    max(q[0] for q in polygon), max(q[1] for q in polygon))
            delta = (args.pitch * u[0], args.pitch * u[1])
            valid = ((xx + rect[0] >= 11) & (xx + rect[2] <= 129)
                     & (yy + rect[1] >= 11) & (yy + rect[3] <= 129))
            for other in back_courts + [ANTENNA]:
                valid &= ~((xx + rect[0] < other[2] + .15) & (xx + rect[2] > other[0] - .15)
                           & (yy + rect[1] < other[3] + .15) & (yy + rect[3] > other[1] - .15))
            for other in tails:
                if (other[2] < xx.min() + rect[0] or other[0] > xx.max() + rect[2]
                        or other[3] < yy.min() + rect[1] or other[1] > yy.max() + rect[3]):
                    continue
                inside = np.ones(len(xx), dtype=bool)
                corners = [(other[a], other[b]) for a, b in ((0, 1), (2, 1), (2, 3), (0, 3))]
                for ax, ay in ((1, 0), (0, 1), u, v):
                    projection = [x * ax + y * ay for x, y in polygon]
                    other_projection = [x * ax + y * ay for x, y in corners]
                    shift = xx * ax + yy * ay
                    inside &= ((shift + max(projection) > min(other_projection))
                               & (shift + min(projection) < max(other_projection)))
                valid &= ~inside
            for other in front_courts:
                for dx, dy in ((0, 0), delta):
                    # The new holes and their joints must be accessible from
                    # the front, outside every existing component courtyard.
                    valid &= ~((xx + dx - .4 < other[2] + .25)
                               & (xx + dx + .4 > other[0] - .25)
                               & (yy + dy - .4 < other[3] + .25)
                               & (yy + dy + .4 > other[1] - .25))
            for hx, hy in supports:
                dx = np.maximum(np.maximum(xx + rect[0] - hx, hx - xx - rect[2]), 0)
                dy = np.maximum(np.maximum(yy + rect[1] - hy, hy - yy - rect[3]), 0)
                valid &= dx * dx + dy * dy >= 36
            indexes = np.flatnonzero(valid)
            distance = (xx[indexes] - target[0]) ** 2 + (yy[indexes] - target[1]) ** 2
            for index in indexes[np.argsort(distance)[:25]]:
                candidates.append(dict(pin1_xy_mm=[round(float(xx[index]), 6), round(float(yy[index]), 6)],
                    angle_deg=angle, distance_to_target_mm=math.hypot(xx[index] - target[0], yy[index] - target[1])))
        rows.append(dict(target=[ref, pin], target_xy_mm=target,
                         candidates=sorted(candidates, key=lambda row: row['distance_to_target_mm'])[:50]))
    result = dict(board=str(args.board.resolve()), board_sha256=hashlib.sha256(args.board.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), pitch_mm=args.pitch,
        nominal_body_mm=[3.81, 2.54], courtyard_envelope_mm=[args.pitch + 1.9, 3.1],
        drill_mm=.8, pad_diameter_mm=1.4, front_hole_to_courtyard_margin_mm=.25,
        old_pad_tail_envelope_extra_mm=.5, mounting_support_exclusion_radius_mm=6,
        grid_mm=args.grid, search_radius_mm=args.radius, results=rows, scope=__doc__,
        physical_fit_qualified=False, input_saved=False)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps([dict(target=row['target'], nearest=row['candidates'][:3]) for row in rows]))


if __name__ == '__main__':
    main()
