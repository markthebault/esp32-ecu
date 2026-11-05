#!/usr/bin/env python3
"""Finish an explicit A6 draft on fresh copies, accepting only native DRC gains.

The grid is a conservative routing aid. Native checks gate every accepted
addition. These checks do not qualify current, noise, timing, heat or fit.
Run using KiCad's Python environment, with numpy installed.
"""
import argparse
from array import array
import hashlib
import heapq
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import numpy as np
import pcbnew as p

LAYERS = (p.F_Cu, p.In2_Cu, p.In3_Cu, p.B_Cu)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xy(v):
    return v.x / 1e6, v.y / 1e6


def vector(point):
    return p.VECTOR2I(p.FromMM(point[0]), p.FromMM(point[1]))


def pad_state(board):
    return sorted((f.GetReference(), q.m_Uuid.AsString(), q.GetNumber(),
                   q.GetNetname(), xy(q.GetPosition()), xy(q.GetSize()),
                   xy(q.GetDrillSize()), q.GetLayerSet().FmtHex())
                  for f in board.GetFootprints() for q in f.Pads())


def copper_state(board):
    copper_layers = [l for l in board.GetEnabledLayers().Seq() if p.IsCopperLayer(l)]
    result = {}
    for t in board.GetTracks():
        via = isinstance(t, p.PCB_VIA)
        widths = (tuple((layer, t.GetWidth(layer)) for layer in copper_layers
                        if t.IsOnLayer(layer)) if via else t.GetWidth())
        result[t.m_Uuid.AsString()] = (t.GetNetname(), t.GetLayer(),
            xy(t.GetStart()), xy(t.GetEnd()), widths,
            (t.GetDrillValue(), t.TopLayer(), t.BottomLayer(), t.GetViaType()) if via else None)
    return result


def drc_summary(d):
    return dict(unconnected=len(d['unconnected_items']),
        dangling=sum(v['type'] in ('track_dangling', 'via_dangling')
                     for v in d['violations']),
        physical=[v for v in d['violations']
                  if v['type'] not in ('track_dangling', 'via_dangling')],
        parity=len(d['schematic_parity']))


def native_drc(folder):
    with (folder / 'finish-drc.log').open('xb') as log:
        result = subprocess.run(['kicad-cli', 'pcb', 'drc',
            '--exit-code-violations', '--severity-all', '--schematic-parity', '--format', 'json',
            '--output', str(folder / 'finish-drc.json'),
            str(folder / 'esp32-ecu.kicad_pcb')],
            stdout=log, stderr=subprocess.STDOUT)
    assert result.returncode in (0, 5), result.returncode
    return json.loads((folder / 'finish-drc.json').read_text())


def copy_native(source, target):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(
        'native-drc.*', 'finish-drc.*', '*.kicad_prl', '*.lck', '*~'))


def item_points(item):
    if isinstance(item, p.PCB_TRACK) and not isinstance(item, p.PCB_VIA):
        return [(xy(item.GetStart()), (item.GetLayer(),)),
                (xy(item.GetEnd()), (item.GetLayer(),))]
    return [(xy(item.GetPosition()), tuple(l for l in LAYERS if item.IsOnLayer(l)))]


def component(start, items, connectivity):
    """Follow native pad/track adjacency; never invent zone contact points."""
    seen = {start.m_Uuid.AsString()}
    pending = [start]
    result = []
    while pending:
        item = pending.pop()
        result.extend(item_points(item))
        for adjacent in (*connectivity.GetConnectedTracks(item),
                         *connectivity.GetConnectedPads(item)):
            uid = adjacent.m_Uuid.AsString()
            if uid not in seen and uid in items:
                seen.add(uid)
                pending.append(items[uid])
    return sorted(set(result))


def close_points(first, second, count=24):
    a = np.asarray([v[0] for v in first])
    b = np.asarray([v[0] for v in second])
    best_a = np.full(len(a), np.inf)
    best_b = np.full(len(b), np.inf)
    for offset in range(0, len(a), 64):
        distances = np.sum((a[offset:offset + 64, None] - b[None, :]) ** 2, axis=2)
        best_a[offset:offset + 64] = distances.min(axis=1)
        np.minimum(best_b, distances.min(axis=0), out=best_b)
    def choose(points, distances):
        # Nearby track ends can be trapped on one copper layer. Retain every
        # real PTH/via anchor even when it is farther away, so distance pruning
        # cannot hide a usable entrance to the connected component.
        indexes = set(int(i) for i in np.argsort(distances)[:count])
        indexes.update(i for i, point in enumerate(points) if len(point[1]) > 1)
        return [points[i] for i in sorted(indexes)]
    return (choose(first, best_a), choose(second, best_b),
            float(np.sqrt(best_a.min())))


def route(board, net, starts, goals, step, expansion_limit, margin, heuristic_weight,
          width_override=None):
    """Search four signal layers; through-via obstacles cover every Cu layer."""
    # Relay commands retain the explicit 0.5 mm Supply route class used by
    # route_a6.py. This is geometry policy, not an accepted load-current rating.
    width = (1.0 if net in {'GND', 'VBAT_FUSED', 'VIN_PROT', 'VIN_FILTERED'}
             or re.fullmatch(r'INJ[1-4]_LS', net) else
             .5 if net in {'+3V3', '+5V', 'RUN_5V', 'SENSOR_5V', 'FLEX_12V',
                           'MAIN_LS', 'PUMP_LS', 'FAN_LS'} else .25)
    if width_override is not None:
        width = width_override
    via_width, via_drill = ((1.2, .6) if width == 1 else (.7, .35))
    points = [v[0] for v in starts + goals]
    edges = board.GetBoardEdgesBoundingBox()
    bounds = (edges.GetX() / 1e6, edges.GetY() / 1e6,
              edges.GetRight() / 1e6, edges.GetBottom() / 1e6)
    x0 = max(bounds[0], math.floor(min(v[0] for v in points) - margin))
    y0 = max(bounds[1], math.floor(min(v[1] for v in points) - margin))
    x1 = min(bounds[2], math.ceil(max(v[0] for v in points) + margin))
    y1 = min(bounds[3], math.ceil(max(v[1] for v in points) + margin))
    w, h = round((x1 - x0) / step) + 1, round((y1 - y0) / step) + 1
    size = w * h
    xx = x0 + np.arange(w) * step
    yy = y0 + np.arange(h) * step
    occupied = [np.zeros((h, w), dtype=bool) for _ in LAYERS]
    via_blocked = np.zeros((h, w), dtype=bool)
    # Conservative raster/rounding allowance, in addition to 0.2 mm clearance.
    raster = step * math.sqrt(2) / 2 + .015
    track_gap = width / 2 + .2 + raster
    via_gap = via_width / 2 + .2 + raster

    def rect(mask, left, top, right, bottom, grow):
        ax = max(0, math.floor((left - grow - x0) / step))
        ay = max(0, math.floor((top - grow - y0) / step))
        bx = min(w, math.ceil((right + grow - x0) / step) + 1)
        by = min(h, math.ceil((bottom + grow - y0) / step) + 1)
        if bx > ax and by > ay:
            mask[ay:by, ax:bx] = True

    def box(mask, bb, grow):
        rect(mask, bb.GetX() / 1e6, bb.GetY() / 1e6,
             bb.GetRight() / 1e6, bb.GetBottom() / 1e6, grow)

    def capsule(mask, a, b, radius):
        ax = max(0, math.floor((min(a[0], b[0]) - radius - x0) / step))
        ay = max(0, math.floor((min(a[1], b[1]) - radius - y0) / step))
        bx = min(w, math.ceil((max(a[0], b[0]) + radius - x0) / step) + 1)
        by = min(h, math.ceil((max(a[1], b[1]) + radius - y0) / step) + 1)
        if bx <= ax or by <= ay:
            return
        dx, dy = b[0] - a[0], b[1] - a[1]
        vx, vy = xx[ax:bx][None, :] - a[0], yy[ay:by][:, None] - a[1]
        if dx or dy:
            t = np.clip((vx * dx + vy * dy) / (dx * dx + dy * dy), 0, 1)
            inside = (vx - t * dx) ** 2 + (vy - t * dy) ** 2 <= radius ** 2
        else:
            inside = vx * vx + vy * vy <= radius ** 2
        mask[ay:by, ax:bx] |= inside

    for mask, radius in [(o, width / 2 + .4 + raster) for o in occupied] + [
            (via_blocked, via_width / 2 + .4 + raster)]:
        mask |= ((xx[None, :] < bounds[0] + radius) |
                 (xx[None, :] > bounds[2] - radius) |
                 (yy[:, None] < bounds[1] + radius) |
                 (yy[:, None] > bounds[3] - radius))
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            # Both rectangular native RF envelopes are conservatively excluded
            # on every routed layer and for every new through via.
            assert zone.Outline().OutlineCount() == 1
            bb = zone.Outline().BBox()
            if zone.GetDoNotAllowTracks():
                for mask in occupied:
                    box(mask, bb, track_gap)
            if zone.GetDoNotAllowVias():
                box(via_blocked, bb, via_gap)
    for f in board.GetFootprints():
        for pad in f.Pads():
            bb = pad.GetBoundingBox()
            box(via_blocked, bb, max(via_gap, via_drill / 2 + .25 + raster))
            hole = pad.GetAttribute() == p.PAD_ATTRIB_NPTH
            if not hole and pad.GetNetname() == net:
                continue
            for li, layer in enumerate(LAYERS):
                if hole or pad.IsOnLayer(layer):
                    box(occupied[li], bb, max(track_gap, width / 2 + .25 + raster)
                        if hole else track_gap)
    for track in board.GetTracks():
        is_via = isinstance(track, p.PCB_VIA)
        a, b = xy(track.GetStart()), xy(track.GetEnd())
        half = (max(track.GetWidth(l) for l in board.GetEnabledLayers().Seq()
                    if p.IsCopperLayer(l) and track.IsOnLayer(l)) if is_via
                else track.GetWidth()) / 2e6
        if is_via:
            capsule(via_blocked, a, a, half + via_gap)
            if track.GetNetname() != net:
                for mask in occupied:
                    capsule(mask, a, a, half + track_gap)
        elif track.GetNetname() != net:
            # Via clearance sees foreign copper on all six layers.
            capsule(via_blocked, a, b, half + via_gap)
            if track.GetLayer() in LAYERS:
                capsule(occupied[LAYERS.index(track.GetLayer())], a, b, half + track_gap)
    masks = [o.ravel() for o in occupied]
    vias = via_blocked.ravel()

    def node(point, layer):
        x, y = round((point[0] - x0) / step), round((point[1] - y0) / step)
        if not (0 <= x < w and 0 <= y < h):
            return None
        return LAYERS.index(layer) * size + y * w + x

    start_nodes, goal_nodes = {}, {}
    for choices, mapping in ((starts, start_nodes), (goals, goal_nodes)):
        for point, layers in choices:
            for layer in layers:
                if layer not in LAYERS:
                    continue
                i = node(point, layer)
                if i is not None and not masks[i // size][i % size]:
                    mapping[i] = point
    if not start_nodes or not goal_nodes:
        raise RuntimeError('No clear start/goal grid anchors')
    heuristic = np.full((h, w), np.iinfo(np.int32).max, dtype=np.int32)
    gxlist = sorted({(i % size % w, i % size // w) for i in goal_nodes})
    gx = np.arange(w)[None, :]
    gy = np.arange(h)[:, None]
    for x, y in gxlist:
        dx, dy = np.abs(gx - x), np.abs(gy - y)
        np.minimum(heuristic, 10 * np.maximum(dx, dy) + 4 * np.minimum(dx, dy), out=heuristic)
    heuristic = heuristic.ravel()
    costs = array('I', [0xffffffff]) * (size * len(LAYERS))
    parents = array('i', [-1]) * (size * len(LAYERS))
    closed = bytearray(size * len(LAYERS))
    heap = []
    for i in start_nodes:
        costs[i] = 0
        heapq.heappush(heap, (int(heuristic_weight * heuristic[i % size]), i))
    expanded = 0
    end = None

    def push(target, origin, cost):
        if cost < costs[target]:
            costs[target], parents[target] = cost, origin
            heapq.heappush(heap, (cost + int(heuristic_weight * heuristic[target % size]), target))

    while heap:
        _, i = heapq.heappop(heap)
        if closed[i]:
            continue
        closed[i] = 1
        expanded += 1
        if i in goal_nodes:
            end = i
            break
        if expanded >= expansion_limit:
            raise RuntimeError('Search expansion limit reached')
        li, pi = divmod(i, size)
        x, y = pi % w, pi // w
        mask = masks[li]
        for dx, dy, price in ((1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10),
                              (1, 1, 14), (-1, 1, 14), (1, -1, 14), (-1, -1, 14)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            np_ = ny * w + nx
            ni = li * size + np_
            if mask[np_] or closed[ni] or (dx and dy and (mask[y * w + nx] or mask[ny * w + x])):
                continue
            push(ni, i, costs[i] + price)
        if not vias[pi] and all(not mask[pi] for mask in masks):
            for ll in range(len(LAYERS)):
                if ll != li:
                    push(ll * size + pi, i, costs[i] + 300)
    if end is None:
        raise RuntimeError('No multilayer path')
    path = []
    i = end
    while i != -1:
        li, pi = divmod(i, size)
        path.append((x0 + (pi % w) * step, y0 + (pi // w) * step, li))
        origin = i
        i = parents[i]
    path.reverse()
    compact = [(*start_nodes[origin], path[0][2])]
    for j, point in enumerate(path):
        if (j == 0 or j == len(path) - 1 or point[2] != path[j - 1][2]
                or point[2] != path[j + 1][2]
                or (round(point[0] - path[j - 1][0], 6), round(point[1] - path[j - 1][1], 6))
                != (round(path[j + 1][0] - point[0], 6), round(path[j + 1][1] - point[1], 6))):
            compact.append(point)
    compact.append((*goal_nodes[end], path[-1][2]))
    added = []
    used_vias = set()
    length = 0
    for a, b in zip(compact, compact[1:]):
        if a[2] != b[2]:
            key = b[:2]
            if key in used_vias:
                continue
            t = p.PCB_VIA(board)
            t.SetPosition(vector(key))
            t.SetWidth(p.FromMM(via_width))
            t.SetDrill(p.FromMM(via_drill))
            t.SetViaType(p.VIATYPE_THROUGH)
            t.SetLayerPair(p.F_Cu, p.B_Cu)
            used_vias.add(key)
        else:
            distance = math.dist(a[:2], b[:2])
            if distance < .000001:
                continue
            t = p.PCB_TRACK(board)
            t.SetStart(vector(a[:2]))
            t.SetEnd(vector(b[:2]))
            t.SetWidth(p.FromMM(width))
            t.SetLayer(LAYERS[a[2]])
            length += distance
        t.SetNet(board.FindNet(net))
        board.Add(t)
        added.append(t.m_Uuid.AsString())
    return dict(width_mm=width, via_width_mm=via_width, via_drill_mm=via_drill,
                length_mm=length, vias=len(used_vias), expanded=expanded,
                added_uuids=added, grid_step_mm=step, margin_mm=margin,
                heuristic_weight=heuristic_weight, shortest_path_claim=False)


def main():
    global LAYERS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nets', nargs='*')
    parser.add_argument('--limit', type=int, default=16)
    parser.add_argument('--step', type=float, default=.1)
    parser.add_argument('--margin', type=float, default=12)
    parser.add_argument('--expansion-limit', type=int, default=1000000)
    parser.add_argument('--heuristic-weight', type=float, default=1,
                        help='Values >1 prioritize progress over shortest paths; native gates are unchanged.')
    parser.add_argument('--route-width-mm', type=float,
                        help='Explicit single-net experimental override; native minimums remain enforced.')
    layer_names = {'F.Cu': p.F_Cu, 'In2.Cu': p.In2_Cu,
                   'In3.Cu': p.In3_Cu, 'B.Cu': p.B_Cu}
    parser.add_argument('--layers', nargs='+', choices=tuple(layer_names),
                        help='Restrict new routing to these signal layers; plane layers stay excluded.')
    args = parser.parse_args()
    assert .025 <= args.step <= .2 and args.limit > 0 and 1 <= args.heuristic_weight <= 4
    assert args.route_width_mm is None or (
        args.nets and len(args.nets) == 1 and .2 <= args.route_width_mm <= 1)
    if args.layers:
        assert len(args.layers) == len(set(args.layers)), 'Duplicate routing layer'
        LAYERS = tuple(layer_names[name] for name in args.layers)
    source = args.source.resolve()
    assert json.loads((source / 'net_contract.json').read_text())['revision'] == 'A6-FLEX-RGB-HOLD'
    source_hashes = {f.name: sha(f) for f in source.iterdir() if f.is_file()}
    script_bytes = Path(__file__).read_bytes()
    script_hash = hashlib.sha256(script_bytes).hexdigest()
    out = args.output.resolve()
    assert source != out and source not in out.parents
    out.mkdir(parents=True, exist_ok=False)
    (out / 'runner.py').write_bytes(script_bytes)
    selected = out / 'baseline'
    copy_native(source, selected)
    drc = native_drc(selected)
    original = p.LoadBoard(str(source / 'esp32-ecu.kicad_pcb'))
    original_pads, original_copper = pad_state(original), copper_state(original)
    baseline = drc_summary(drc)
    assert not baseline['physical'] and not baseline['parity'], baseline
    attempted = set()
    trials = []
    accepted = 0
    while len(trials) < args.limit:
        board = p.LoadBoard(str(selected / 'esp32-ecu.kicad_pcb'))
        connectivity = board.GetConnectivity()
        connectivity.Build(board)
        items = {q.m_Uuid.AsString(): q for f in board.GetFootprints() for q in f.Pads()}
        items.update({t.m_Uuid.AsString(): t for t in board.GetTracks()})
        options = []
        for finding in drc['unconnected_items']:
            ids = tuple(i['uuid'] for i in finding['items'])
            if len(ids) != 2 or any(i not in items for i in ids) or ids in attempted:
                continue
            a, b = [items[i] for i in ids]
            net = a.GetNetname()
            if args.nets and net not in args.nets:
                continue
            starts, goals, distance = close_points(component(a, items, connectivity),
                                                   component(b, items, connectivity))
            # A small isolated pad component is a better search origin than a
            # large supply tree when the terminal's escape is obstructed.
            if len(starts) > len(goals):
                starts, goals = goals, starts
            options.append((distance, ids, net, starts, goals))
        if not options:
            break
        _, ids, net, starts, goals = min(options)
        attempted.add(ids)
        row = dict(net=net, source=str(selected), endpoint_uuids=ids)
        begin = time.monotonic()
        try:
            row.update(route(board, net, starts, goals, args.step,
                             args.expansion_limit, args.margin, args.heuristic_weight,
                             args.route_width_mm))
        except RuntimeError as error:
            row.update(accepted=False, search_error=str(error))
        else:
            trial = out / ('trial-%03d' % (len(trials) + 1))
            copy_native(selected, trial)
            p.ZONE_FILLER(board).Fill(board.Zones())
            assert pad_state(board) == original_pads
            copper = copper_state(board)
            assert all(copper.get(k) == v for k, v in original_copper.items())
            target = trial / 'esp32-ecu.kicad_pcb'
            p.SaveBoard(str(target), board)
            result = native_drc(trial)
            before, after = drc_summary(drc), drc_summary(result)
            accept = (not after['physical'] and not after['parity']
                      and after['unconnected'] < before['unconnected']
                      and after['dangling'] <= before['dangling'])
            row.update(path=str(target), pcb_sha256=sha(target),
                       unconnected=after['unconnected'], dangling=after['dangling'],
                       physical_findings=len(after['physical']), parity=after['parity'],
                       accepted=accept)
            if accept:
                selected, drc = trial, result
                accepted += 1
        row['elapsed_s'] = round(time.monotonic() - begin, 3)
        trials.append(row)
        print(json.dumps(row), flush=True)
        summary = drc_summary(drc)
        (out / 'results.json').write_text(json.dumps(dict(
            source=str(source), source_hashes=source_hashes,
            script_sha256=script_hash, command=sys.argv,
            kicad_version=p.GetBuildVersion(), selected=str(selected),
            baseline=baseline, current=summary, accepted_count=accepted,
            trials=trials, scope=__doc__, manufacturing_release=False,
            independent_copper_review=False), indent=2) + '\n')
    assert all(sha(source / name) == expected for name, expected in source_hashes.items())
    print('Selected', selected, 'accepted', accepted, drc_summary(drc), flush=True)


if __name__ == '__main__':
    main()
