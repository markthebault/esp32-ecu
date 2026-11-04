#!/usr/bin/env python3
"""Prepare router widths, or import a router session into the KiCad PCB.

Run with KiCad's Python. Freerouting is an external Java dependency, not bundled.
"""
import argparse
from pathlib import Path
import re
import math
import pcbnew as pcb

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/esp32-ecu.kicad_pcb"
DSN = ROOT / ".cache/esp32-ecu.dsn"


def ground_fanout(board):
    if any(isinstance(t,pcb.PCB_VIA) for t in board.GetTracks()):
        return
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()]
    holes = [(pad.GetPosition().x/1e6,pad.GetPosition().y/1e6,pad.GetDrillSize().x/2e6)
             for pad in pads if pad.GetDrillSize().x > 0]
    others = []
    for pad in pads:
        if not pad.GetNumber() or not pad.IsOnLayer(pcb.F_Cu): continue
        if pad.GetNetname() == "GND": continue
        b=pad.GetBoundingBox()
        others.append((b.GetX()/1e6,b.GetY()/1e6,b.GetRight()/1e6,b.GetBottom()/1e6))
    def free(x,y,r):
        if x-r<10.4 or x+r>209.6 or y-r<10.4 or y+r>209.6:return False
        # Stock module's all-layer antenna clearance, transformed 90 degrees.
        if x-r<23.25 and x+r>2.25 and y+r>46 and y-r<94:return False
        for l,t,rr,b in others:
            dx=max(l-x,0,x-rr);dy=max(t-y,0,y-b)
            if dx*dx+dy*dy < r*r:return False
        return True
    added=0
    for pad in pads:
        if pad.GetNetname() != "GND" or pad.GetAttribute() != pcb.PAD_ATTRIB_SMD:continue
        x,y=pad.GetPosition().x/1e6,pad.GetPosition().y/1e6
        candidates=[]
        for distance in [.9,1.2,1.5,1.8,2.2,2.8,3.4,0]:
            for direction in range(16):
                angle=direction*math.pi/8
                vx,vy=x+distance*math.cos(angle),y+distance*math.sin(angle)
                if not free(vx,vy,.35+.21):continue
                if any(math.hypot(vx-hx,vy-hy) < .175+hr+.26 for hx,hy,hr in holes):continue
                if all(free(x+(vx-x)*t/30,y+(vy-y)*t/30,.125+.21) for t in range(31)):
                    candidates.append((vx,vy));break
            if candidates:break
        if not candidates:
            raise RuntimeError(f'No clear ground via escape at ({x},{y}), pad {pad.GetNumber()}')
        vx,vy=candidates[0]
        via=pcb.PCB_VIA(board)
        via.SetPosition(pcb.VECTOR2I(pcb.FromMM(vx),pcb.FromMM(vy)))
        via.SetWidth(pcb.FromMM(.7));via.SetDrill(pcb.FromMM(.35))
        via.SetViaType(pcb.VIATYPE_THROUGH);via.SetLayerPair(pcb.F_Cu,pcb.B_Cu);via.SetNet(pad.GetNet())
        board.Add(via)
        holes.append((vx,vy,.175))
        track=pcb.PCB_TRACK(board)
        track.SetStart(pad.GetPosition());track.SetEnd(via.GetPosition())
        track.SetWidth(pcb.FromMM(.25));track.SetLayer(pcb.F_Cu);track.SetNet(pad.GetNet())
        board.Add(track)
        added+=1
    print(f'Added {added} explicit short ground fanouts to the continuous inner plane')


def prepare():
    board = pcb.LoadBoard(str(BOARD))
    ground_fanout(board)
    # Mounting-hole references stay within the board, away from its edge.
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("H"):
            fp.Reference().SetVisible(False)
    pcb.SaveBoard(str(BOARD),board)
    pcb.ExportSpecctraDSN(board,str(DSN))
    s = DSN.read_text()
    via_match = re.search(r'\(via "([^"]+)"',s)
    if not via_match:
        raise RuntimeError("DSN has no through via definition")
    via_name = via_match.group(1)
    start = s.index("    (class kicad_default")
    end = s.index("\n  (wiring",start)
    network_nets = re.findall(r'\n    \(net ("[^"]+"|[^\s()]+)',s[:start])
    groups = {
        "power": (["VBAT_FUSED","VIN_PROT","SW","+5V"],1000),
        "injectors": ([f"INJ{i}_LS" for i in range(1,5)],1000),
        "logic_supply": (["+3V3","SENSOR_5V"],500),
        "ground": (["GND"],500),
    }
    assigned = {n for nets,_ in groups.values() for n in nets}
    groups["signals"] = ([n for n in network_nets if n.strip('"') not in assigned],250)
    classes = []
    for name,(nets,width) in groups.items():
        classes.append(f'    (class {name} '+" ".join(nets)+f' (circuit (use_via "{via_name}")) (rule (width {width}) (clearance 200)))')
    s = s[:start]+"\n".join(classes)+"\n  )\n"+s[end:]
    DSN.write_text(s)
    print("Prepared DSN: 1 mm injector/power routes, 0.5 mm supplies, 0.25 mm signals; inner ground plane")


def import_session(path):
    board = pcb.LoadBoard(str(BOARD))
    if not pcb.ImportSpecctraSES(board,str(Path(path).resolve())):
        raise RuntimeError("Router session import failed")
    # Merge a ground fanout into an existing plated module thermal hole when
    # their drills are too close. This also repairs older generated fanouts.
    ground_holes=[pad for fp in board.GetFootprints() for pad in fp.Pads()
                  if pad.GetNetname()=="GND" and pad.GetDrillSize().x>0]
    for via in list(board.GetTracks()):
        if not isinstance(via,pcb.PCB_VIA) or via.GetNetname()!="GND": continue
        for pad in ground_holes:
            distance=math.hypot(via.GetPosition().x-pad.GetPosition().x,via.GetPosition().y-pad.GetPosition().y)/1e6
            if distance < (via.GetDrillValue()+pad.GetDrillSize().x)/2e6+.25:
                old=via.GetPosition()
                for track in board.GetTracks():
                    if isinstance(track,pcb.PCB_VIA) or track.GetNetname()!="GND":continue
                    if track.GetStart()==old:track.SetStart(pad.GetPosition())
                    if track.GetEnd()==old:track.SetEnd(pad.GetPosition())
                board.Remove(via)
                break
    pcb.SaveBoard(str(BOARD),board)
    print("Imported session; KiCad DRC and parity check are still required")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-session")
    args = parser.parse_args()
    if args.import_session:
        import_session(args.import_session)
    else:
        prepare()
