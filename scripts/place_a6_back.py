"""Nominal placement of one back resistor, clear of through-hole pad/tail areas.

This is two-dimensional screening on an unrouted board. Back clearance, formed
leads, trim, solder access, insulation, heat and case fit require physical checks.
"""

import math

import pcbnew as pcb

from build_a5_idle_interface import overlaps
from pack_a6 import ANTENNA


def courtyard(fp):
    layer = pcb.B_CrtYd if fp.GetLayer() == pcb.B_Cu else pcb.F_CrtYd
    boxes = [x.GetBoundingBox() for x in fp.GraphicalItems() if x.GetLayer() == layer]
    assert boxes, fp.GetReference()
    return (min(x.GetX() for x in boxes)/1e6, min(x.GetY() for x in boxes)/1e6,
            max(x.GetRight() for x in boxes)/1e6, max(x.GetBottom() for x in boxes)/1e6)


def intersects(poly, rectangle, u, v):
    corners = [(rectangle[x], rectangle[y]) for x, y in ((0, 1), (2, 1), (2, 3), (0, 3))]
    for ax, ay in ((1, 0), (0, 1), u, v):
        first = [x*ax+y*ay for x, y in poly]
        second = [x*ax+y*ay for x, y in corners]
        if max(first) <= min(second) or max(second) <= min(first):
            return False
    return True


def place_back(board, fp, preferred, already_added=False):
    assert not board.GetTracks(), 'Back-placement screening requires an unrouted copy'
    assert fp.GetLayer() == pcb.B_Cu
    others = [f for f in board.GetFootprints() if f.GetReference() != fp.GetReference()]
    tail_boxes, back_courts, front_courts, supports = [], [], [], []
    for other in others:
        if other.GetLayer() == pcb.B_Cu:
            back_courts.append(courtyard(other))
        else:
            front_courts.append(courtyard(other))
        if other.GetReference().startswith('H'):
            supports.append((other.GetPosition().x/1e6, other.GetPosition().y/1e6))
        for pad in other.Pads():
            b = pad.GetBoundingBox()
            tail_boxes.append((b.GetX()/1e6-.5, b.GetY()/1e6-.5,
                               b.GetRight()/1e6+.5, b.GetBottom()/1e6+.5))
    offsets = {}
    for angle in range(0, 360, 45):
        fp.SetPosition(pcb.VECTOR2I(0, 0))
        fp.SetOrientationDegrees(angle)
        pad1 = next(p for p in fp.Pads() if p.GetNumber() == '1')
        pad = next(p for p in fp.Pads() if p.GetNumber() == '2')
        origin = (pad1.GetPosition().x/1e6, pad1.GetPosition().y/1e6)
        delta = ((pad.GetPosition().x-pad1.GetPosition().x)/1e6,
                 (pad.GetPosition().y-pad1.GetPosition().y)/1e6)
        pitch = math.hypot(*delta)
        u = (delta[0]/pitch, delta[1]/pitch)
        v = (-u[1], u[0])
        poly = [(origin[0]+u[0]*x+v[0]*y, origin[1]+u[1]*x+v[1]*y)
                for x, y in ((-1.275, -1.675), (pitch+1.275, -1.675),
                             (pitch+1.275, 1.675), (-1.275, 1.675))]
        # KiCad's opposite-side PTH/courtyard rule concerns the drill/joint
        # location. Copper-pad clearances are checked separately by native DRC.
        holes = [(p.GetPosition().x/1e6-p.GetDrillSize().x/2e6,
                  p.GetPosition().y/1e6-p.GetDrillSize().y/2e6,
                  p.GetPosition().x/1e6+p.GetDrillSize().x/2e6,
                  p.GetPosition().y/1e6+p.GetDrillSize().y/2e6) for p in fp.Pads()]
        offsets[angle] = (courtyard(fp), (pad.GetPosition().x/1e6, pad.GetPosition().y/1e6), holes, poly, u, v)
    candidates = []
    for angle, (court, pad2, holes, poly, u, v) in offsets.items():
        for ix in range(22, 259):
            x = ix / 2
            for iy in range(22, 259):
                y = iy / 2
                b = (x+court[0], y+court[1], x+court[2], y+court[3])
                if min(b[:2]) < 11 or max(b[2:]) > 129 or overlaps(b, ANTENNA, .15):
                    continue
                if any(overlaps(b, old, .15) for old in back_courts):
                    continue
                translated = [(x+px, y+py) for px, py in poly]
                nearby = [old for old in tail_boxes if overlaps(b, old, 0)]
                if any(intersects(translated, old, u, v) for old in nearby):
                    continue
                # Back body may occupy a front component's opposite side, but
                # the new PTH joints must remain accessible outside its court.
                pad_bounds = [(x+h[0], y+h[1], x+h[2], y+h[3]) for h in holes]
                if any(overlaps(hole, old, .25) for hole in pad_bounds for old in front_courts):
                    continue
                if any(math.hypot(max(b[0]-hx, 0, hx-b[2]), max(b[1]-hy, 0, hy-b[3])) < 6
                       for hx, hy in supports):
                    continue
                distance = math.dist((x+pad2[0], y+pad2[1]), preferred)
                candidates.append((distance, x, y, angle, b))
    assert candidates, 'No back placement clear of nominal pads/tails, supports and antenna'
    distance, x, y, angle, bounds = min(candidates)
    fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y)))
    fp.SetOrientationDegrees(angle)
    if not already_added:
        board.Add(fp)
    assert all(abs(a-b) < 1e-5 for a, b in zip(courtyard(fp), bounds))
    return [x, y], angle, dict(courtyard_mm=bounds, nearest_connector_pad_mm=distance,
                              old_pad_tail_envelope_extra_mm=.5, mounting_support_radius_mm=6,
                              new_pth_hole_to_front_courtyard_margin_mm=.25,
                              required_back_clearance_mm=4,
                              physical_fit_qualified=False, scope=__doc__)
