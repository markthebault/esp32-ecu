#!/usr/bin/env python3
"""Conservative 2D body/pad projection audit, not a physical-fit certificate.

Back-side Fab bodies must not overlap another front-side solder pad. Separately
report back-component lead ends projected beneath front bodies, requiring the
documented trim/inspection order and actual lead/body/standoff measurements.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import pcbnew as pcb

ROOT=Path(__file__).resolve().parents[1]


def bounds(box):
    return [box.GetX()/1e6,box.GetY()/1e6,box.GetRight()/1e6,box.GetBottom()/1e6]


def distance(a,b):
    return math.hypot(max(a[0]-b[2],b[0]-a[2],0),max(a[1]-b[3],b[1]-a[3],0))


def bodies(fp,layer):
    # Text/polarity markers are not component volume. Use body rectangles,
    # circles and polygons; bound each separately rather than unioning leads.
    result=[bounds(x.GetBoundingBox()) for x in fp.GraphicalItems()
            if isinstance(x,pcb.PCB_SHAPE) and x.GetLayer()==layer
            and x.GetShape() in (pcb.SHAPE_T_RECT,pcb.SHAPE_T_CIRCLE,pcb.SHAPE_T_POLY)]
    if not result:
        lines=[bounds(x.GetBoundingBox()) for x in fp.GraphicalItems()
               if isinstance(x,pcb.PCB_SHAPE) and x.GetLayer()==layer]
        if lines:result=[[min(x[0] for x in lines),min(x[1] for x in lines),
                          max(x[2] for x in lines),max(x[3] for x in lines)]]
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
    file=ROOT/'hardware/idle-isolated/isolated.kicad_pcb';board=pcb.LoadBoard(str(file))
    front=[f for f in board.GetFootprints() if f.GetLayer()==pcb.F_Cu]
    back=[f for f in board.GetFootprints() if f.GetLayer()==pcb.B_Cu]
    closest=[];under=[]
    for f in back:
        shape=bodies(f,pcb.B_Fab);assert shape,f.GetReference()
        pairs=[]
        for g in front:
            for pad in g.Pads():
                if pad.GetAttribute()!=pcb.PAD_ATTRIB_PTH:continue
                gap=min(distance(body,bounds(pad.GetBoundingBox())) for body in shape)
                pairs.append(dict(back=f.GetReference(),front_pad=g.GetReference()+'.'+pad.GetNumber(),
                                  fab_body_to_pad_box_mm=gap))
        closest.append(min(pairs,key=lambda x:x['fab_body_to_pad_box_mm']))
        for pad in f.Pads():
            for g in front:
                if any(distance(body,bounds(pad.GetBoundingBox()))==0 for body in bodies(g,pcb.F_Fab)):
                    under.append(dict(back_lead=f.GetReference()+'.'+pad.GetNumber(),front_body=g.GetReference()))
    report=dict(scope=__doc__,board_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                closest_front_solder_pad_per_back_body=closest,lead_ends_under_front_body_projection=under,
                back_body_overlaps_front_pad=any(x['fab_body_to_pad_box_mm']==0 for x in closest),
                qualification='Nominal library2D projections only. Fab bodies are not exact selected part envelopes; solder bulge, lead trim, body stand-off, height and case clearance remain unmeasured.')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    assert not report['back_body_overlaps_front_pad'],report
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
