"""Find exact vacant rectangle corners on an explicitly unrouted new copy.

Only nominal courtyard placement is checked here. Native DRC, copper and
physical assembly/thermal/fit checks remain separate.
"""

import math

import pcbnew as pcb

from build_a5_idle_interface import box, overlaps
from pack_a6 import ANTENNA, GAP, expanded, subtract


def place_corner(board, fp, preferred):
    assert not board.GetTracks(), 'Corner placement requires an unrouted copy'
    assert fp.GetLayer() == pcb.F_Cu
    occupied = [box(f) for f in board.GetFootprints()]
    free = [(11, 11, 129, 129)]
    for bounds in occupied + [ANTENNA]:
        free = subtract(free, expanded(bounds))
    candidates = []
    for angle in (0, 90, 180, 270):
        fp.SetPosition(pcb.VECTOR2I(0, 0))
        fp.SetOrientationDegrees(angle)
        offset = box(fp)
        width, height = offset[2]-offset[0]+GAP, offset[3]-offset[1]+GAP
        for r in free:
            if width > r[2]-r[0]+1e-8 or height > r[3]-r[1]+1e-8:
                continue
            for x, y in ((r[0], r[1]), (r[2]-width, r[1]),
                         (r[0], r[3]-height), (r[2]-width, r[3]-height)):
                px, py = x+GAP/2-offset[0], y+GAP/2-offset[1]
                fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(px), pcb.FromMM(py)))
                fp.SetOrientationDegrees(angle)
                bounds = box(fp)
                if any(overlaps(bounds, old, GAP-1e-6) for old in occupied+[ANTENNA]):
                    continue
                candidates.append((math.dist((px, py), preferred), px, py, angle, bounds))
    assert candidates, 'No exact corner candidate for this footprint'
    _, x, y, angle, bounds = min(candidates)
    fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y)))
    fp.SetOrientationDegrees(angle)
    assert box(fp) == bounds
    board.Add(fp)
    return [x, y], angle
