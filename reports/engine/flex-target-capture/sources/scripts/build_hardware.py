#!/usr/bin/env python3
"""Generate a self-contained KiCad 10 project. Run with KiCad's Python.

The generated PCB starts with placement and a few deliberately local supply
connections. Route using route_board.py, then run check.sh. Re-running this
script replaces the PCB, so preserve a hand-routed board before regenerating.
"""
import csv
import argparse
import json
import os
from pathlib import Path
import shutil
import uuid

import pcbnew as pcb
from design import PARTS, GPIO, PAGES, NOTES, Part

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware"
LIB = OUT / "lib"
STOCK = Path(os.environ.get("KICAD_STOCK", "/Applications/KiCad/KiCad.app/Contents/SharedSupport"))
NS = uuid.UUID("7fdc6c3d-e17e-49bb-a7ce-383114ce22f3")


def uid(key):
    return str(uuid.uuid5(NS, key))


def q(s):
    return json.dumps(str(s), ensure_ascii=False)


def effects(size=1.0, extra=""):
    return f"(effects (font (size {size} {size})) {extra})"


def property_(name, value, x=0, y=0, hide=False):
    return f"(property {q(name)} {q(value)} (at {x} {y} 0) {effects(1, '(hide yes)' if hide else '')})"


def symbol(p, embedded=False):
    count = len(p.pins)
    # Pins are sorted numerically. Left/right arrangement has a stable physical
    # pin number, regardless of whether a connection is populated.
    keys = sorted(p.pins, key=int)
    split = (count + 1)//2
    height = max(5.08, (split+1)*2.54)
    width = 15.24 if count < 10 else 22.86
    key = "ECU:" + p.ref if embedded else p.ref
    body = [f"(symbol {q(key)} (pin_names (offset 1.016)) (in_bom yes) (on_board yes)",
            property_("Reference", p.ref[0], 0, height/2+5.08),
            property_("Value", p.value, 0, height/2+2.54),
            property_("Footprint", "" if p.ref.startswith("#") else "ECU:"+p.footprint.split(":")[1], hide=True),
            property_("Datasheet", "", hide=True),
            f"(symbol {q(p.ref+'_0_1')} (rectangle (start {-width/2} {height/2}) (end {width/2} {-height/2}) (stroke (width 0.254) (type default)) (fill (type background))))",
            f"(symbol {q(p.ref+'_1_1')}"]
    positions = {}
    for i, n in enumerate(keys):
        left = i < split
        j = i if left else i-split
        x = -width/2-5.08 if left else width/2+5.08
        y = height/2-2.54*(j+1)
        name = p.names.get(n, n)
        typ = p.types.get(n, "passive")
        body.append(f"(pin {typ} line (at {x} {y} {0 if left else 180}) (length 5.08) (name {q(name)} {effects(.9)}) (number {q(n)} {effects(.9)}))")
        positions[n] = (x, y, left)
    body.extend([")", ")"])
    return "\n".join(body), positions, height


def nc_net(p, n):
    name = p.names.get(n, "")
    return f'unconnected-({p.ref}-' + (name+"-" if name else "") + f'Pad{n})'


def net_settings():
    base={"clearance":.2,"track_width":.25,"via_diameter":.7,"via_drill":.35,
          "microvia_diameter":.3,"microvia_drill":.1,"diff_pair_width":.25,
          "diff_pair_gap":.2,"diff_pair_via_gap":.25}
    classes=[]
    for priority,(name,width) in enumerate([("Default",.25),("LogicSupply",.5),("Power",1.0),("Injector",1.0),("SurgeInput",1.5)]):
        classes.append({**base,"name":name,"track_width":width,"priority":priority if priority else -1})
    patterns=[("VBAT_FUSED","SurgeInput"),("VIN_PROT","Power"),("SW","Power"),("+5V","Power"),
              ("+3V3","LogicSupply"),("SENSOR_5V","LogicSupply"),("INJ*_LS","Injector")]
    return {"classes":classes,"version":4,"meta":{"version":5},
            "netclass_patterns":[{"pattern":pattern,"netclass":name} for pattern,name in patterns]}


def write_sheet(page):
    root_uuid, page_uuid = uid("root"), uid(page)
    parts = [p for p in PARTS if p.page == page and p.pins]
    flags = []
    if page == "power":
        for i, net in enumerate(["GND", "VIN_PROT", "+5V"] + globals().get("EXTRA_POWER_FLAGS", []), 1):
            if not any(net == p.pins.get(n) and t == "power_out" for p in parts for n,t in p.types.items()):
                flags.append(Part(f"#FLG0{i}", "PWR_FLAG", "ECU:unused", {"1": net}, {}, {"1": "power_out"}, page, (0,0)))
        parts += flags
    # Core has a tall module. Give it its own column instead of allowing
    # overlapping cells or unreadable scaled text.
    placements = {}
    if page == "core":
        placements["U3"] = (86.36, 104.14)
        others = [p for p in parts if p.ref != "U3"]
        columns, x0 = 5, 208.28
    else:
        others, columns, x0 = parts, 7, 63.5
    row_y = [50.8] * columns
    for i, p in enumerate(others):
        col = i % columns
        _, _, h = symbol(p)
        cy = row_y[col]+h/2+7.62
        placements[p.ref] = (x0 + col*99.06, cy)
        row_y[col] += h+25.4
    symbols = [symbol(p, True)[0] for p in parts]
    content = [f'(kicad_sch (version 20250114) (generator "esp32_ecu") (uuid {page_uuid}) (paper "A1")',
               f'(title_block (title {q("ESP32 ECU A0 / "+page)}) (date "2026-10-30") (rev "A0 BENCH") (company "Engineering prototype"))',
               "(lib_symbols", *symbols, ")",
               f'(text {q(NOTES[page])} (at 25.4 20.32 0) {effects(1.8, "(justify left)")} (uuid {uid(page+"note")}))']
    for p in parts:
        x, y = placements[p.ref]
        _, pos, h = symbol(p)
        board_yes = "no" if p in flags else "yes"
        body = [f'(symbol (lib_id {q("ECU:"+p.ref)}) (at {x} {y} 0) (unit 1) (in_bom {board_yes}) (on_board {board_yes}) (dnp {"yes" if p.dnp else "no"}) (uuid {uid(p.ref)})',
                property_("Reference", p.ref, x, y-h/2-5.08),
                property_("Value", p.value, x, y-h/2-2.54),
                property_("Footprint", "" if p in flags else "ECU:"+p.footprint.split(":")[1], x, y, True),
                property_("MPN", p.mpn, x, y, True),
                property_("DesignNote", p.note, x, y, True)]
        for n in p.pins:
            body.append(f'(pin {q(n)} (uuid {uid(p.ref+":"+n)}))')
        body.append(f'(instances (project "esp32-ecu" (path "/{root_uuid}/{page_uuid}" (reference {q(p.ref)}) (unit 1)))))')
        content.extend(body)
        for n, net in p.pins.items():
            px, py, left = pos[n]
            px, py = round(x+px,5), round(y-py,5)
            key = p.ref+"_"+n
            if net is None:
                content.append(f'(no_connect (at {px} {py}) (uuid {uid(key+"nc")}))')
                continue
            lx = round(px+(-5.08 if left else 5.08),5)
            content.append(f'(wire (pts (xy {px} {py}) (xy {lx} {py})) (stroke (width 0) (type default)) (uuid {uid(key+"wire")}))')
            content.append(f'(global_label {q(net)} (shape bidirectional) (at {lx} {py} {0 if left else 180}) {effects(.9, "(justify "+("right" if left else "left")+")")} (uuid {uid(key+"label")}))')
    content.append(")")
    (OUT / (page+".kicad_sch")).write_text("\n".join(content))


def schematic():
    content = [f'(kicad_sch (version 20250114) (generator "esp32_ecu") (uuid {uid("root")}) (paper "A3")',
               '(title_block (title "ESP32 ECU A0 - bench development") (date "2026-10-30") (rev "A0") (company "Not vehicle qualified"))',
               '(lib_symbols)',
               f'(text "A0 ENGINE CONTROL DEVELOPMENT BOARD" (at 25.4 22.86 0) {effects(2.54,"(justify left)")} (uuid {uid("title")}))',
               f'(text {q("12 V / 4-cylinder PFI / smart coils / Hall triggers. Vehicle adapter and calibration are not defined. Outputs default OFF. External fuses and relays required.")} (at 25.4 35.56 0) {effects(1.5,"(justify left)")} (uuid {uid("overview")}))']
    for i, page in enumerate(PAGES):
        x, y = 25.4+(i%3)*114.3, 66.04+(i//3)*63.5
        content.append(f'(sheet (at {x} {y}) (size 96.52 45.72) (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid {uid(page)}) '
                       +property_("Sheetname", page, x, y-2.54)+property_("Sheetfile", page+".kicad_sch", x, y+48.26)
                       +f'(instances (project "esp32-ecu" (path "/{uid("root")}" (page "{i+2}")))))')
        write_sheet(page)
    content.append('(sheet_instances (path "/" (page "1"))))')
    (OUT / "esp32-ecu.kicad_sch").write_text("\n".join(content))
    flag_parts = [Part(f"#FLG0{i}", "PWR_FLAG", "ECU:unused", {"1": net}, {}, {"1": "power_out"}, "power", (0,0))
                  for i,net in enumerate(["GND", "VIN_PROT", "+5V"],1)]
    all_symbols = [p for p in PARTS if p.pins]+flag_parts
    (LIB / "ecu.kicad_sym").write_text('(kicad_symbol_lib (version 20250114) (generator "esp32_ecu")\n'+"\n".join(symbol(p)[0] for p in all_symbols)+")")


def add_power_returns(board):
    # Short, broad top-layer TVS return directly to the input return. A single
    # logic-width ground fanout via must not carry the entire suppression pulse.
    paths = [("GND",2.5,[(28.4,25),(28.4,31),(18,31),(18,24.54)]),
             ("VBAT_FUSED",1.5,[(18,22),(21.6,22),(21.6,25)])]
    for net,width,points in paths:
        for a,b in zip(points,points[1:]):
            start=pcb.VECTOR2I(pcb.FromMM(a[0]),pcb.FromMM(a[1]))
            end=pcb.VECTOR2I(pcb.FromMM(b[0]),pcb.FromMM(b[1]))
            if any(not isinstance(t,pcb.PCB_VIA) and t.GetLayer()==pcb.F_Cu and
                   t.GetWidth()==pcb.FromMM(width) and t.GetStart()==start and t.GetEnd()==end
                   for t in board.GetTracks()):continue
            track=pcb.PCB_TRACK(board);track.SetStart(start);track.SetEnd(end)
            track.SetWidth(pcb.FromMM(width));track.SetLayer(pcb.F_Cu);track.SetNet(board.FindNet(net));board.Add(track)


def pcb_board():
    board = pcb.BOARD()
    board.SetCopperLayerCount(4)
    board.SetLayerType(pcb.In1_Cu, pcb.LT_POWER)
    settings = board.GetDesignSettings()
    settings.SetBoardThickness(pcb.FromMM(1.6))
    nets = {}
    for net in sorted({net if net is not None else nc_net(p,n) for p in PARTS for n,net in p.pins.items()}):
        item = pcb.NETINFO_ITEM(board, net)
        board.Add(item)
        nets[net] = item
    for p in PARTS:
        fp = pcb.FootprintLoad(str(LIB / "ecu.pretty"), p.footprint.split(":")[1])
        if fp is None:
            raise RuntimeError("Missing footprint: "+p.footprint)
        fp.SetReference(p.ref)
        fp.SetValue(p.value)
        for name, value in [("MPN", p.mpn), ("DesignNote", p.note)]:
            fp.SetField(name, value)
            fp.GetField(name).SetVisible(False)
            fp.GetField(name).SetLayer(pcb.F_Fab)
        fp.SetFPID(pcb.LIB_ID("ECU", p.footprint.split(":")[1]))
        fp.SetPath(pcb.KIID_PATH(f'/{uid("root")}/{uid(p.page)}/{uid(p.ref)}'))
        x, y = p.xy
        angle = p.angle
        if p.ref == "U3":
            x, y, angle = 30, 70, 90
        elif p.page == "core" and not p.ref.startswith(("TP", "H")):
            x, y = x+30, y+10
        elif p.page == "trigger_can":
            y += 60
        elif p.page == "analog":
            y += 50
        elif p.page == "outputs":
            y += 17
        if p.ref == "D1": x = 25
        if p.ref in ("H3", "H4"): y = 206
        fp.SetPosition(pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y)))
        fp.SetOrientationDegrees(angle)
        if p.dnp:
            fp.SetAttributes(fp.GetAttributes() | pcb.FP_DNP)
        if p.ref.startswith("TP"):
            fp.SetAttributes(fp.GetAttributes() & ~pcb.FP_EXCLUDE_FROM_BOM)
        if p.ref.startswith("H"):
            fp.SetAttributes(fp.GetAttributes() | pcb.FP_BOARD_ONLY)
        fp.Value().SetVisible(False)
        fp.Reference().SetTextSize(pcb.VECTOR2I(pcb.FromMM(.9), pcb.FromMM(.9)))
        fp.Reference().SetTextThickness(pcb.FromMM(.15))
        board.Add(fp)
        present = set()
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue
            present.add(num)
            if num not in p.pins:
                raise RuntimeError(f'{p.ref}: footprint has undefined pad {num}')
            net = p.pins[num]
            pad.SetNet(nets[net if net is not None else nc_net(p,num)])
        if present != set(p.pins):
            raise RuntimeError(f'{p.ref}: symbol/footprint pads differ: {present ^ set(p.pins)}')
    # Outline 200 x 200 mm. This is a spacious development board.
    for a, b in [((10,10),(210,10)), ((210,10),(210,210)), ((210,210),(10,210)), ((10,210),(10,10))]:
        edge = pcb.PCB_SHAPE()
        edge.SetShape(pcb.SHAPE_T_SEGMENT)
        edge.SetStart(pcb.VECTOR2I(pcb.FromMM(a[0]), pcb.FromMM(a[1])))
        edge.SetEnd(pcb.VECTOR2I(pcb.FromMM(b[0]), pcb.FromMM(b[1])))
        edge.SetLayer(pcb.Edge_Cuts)
        edge.SetWidth(pcb.FromMM(.05))
        board.Add(edge)
    # Module antenna keepout from the stock footprint is retained on all layers.
    def text(label, x, y, size=1.2, layer=pcb.F_SilkS):
        item = pcb.PCB_TEXT(board)
        item.SetText(label)
        item.SetPosition(pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y)))
        item.SetTextSize(pcb.VECTOR2I(pcb.FromMM(size),pcb.FromMM(size)))
        item.SetTextThickness(pcb.FromMM(.18))
        item.SetLayer(layer)
        board.Add(item)
    text("ESP32 ECU A0 | BENCH PROTOTYPE", 119, 15, 1.7)
    text("NOT VEHICLE QUALIFIED | 12V PFI / SMART COILS", 117, 204, 1.3)
    text("EXTERNAL F1 1A", 31, 17)
    text("J3 OPEN = OUTPUTS OFF", 143, 165)
    text("NO DIRECT COIL PRIMARIES", 162, 158)
    # A continuous inner ground plane. No split sensor/power ground domains.
    zone = pcb.ZONE(board)
    zone.SetLayer(pcb.In1_Cu)
    zone.SetNet(nets["GND"])
    zone.SetLocalClearance(pcb.FromMM(.3))
    zone.SetThermalReliefGap(pcb.FromMM(.3))
    zone.SetThermalReliefSpokeWidth(pcb.FromMM(.4))
    zone.SetPadConnection(pcb.ZONE_CONNECTION_FULL)
    zone.Outline().NewOutline()
    for x,y in [(10.5,10.5),(209.5,10.5),(209.5,209.5),(10.5,209.5)]:
        zone.Outline().Append(pcb.FromMM(x),pcb.FromMM(y))
    board.Add(zone)
    add_power_returns(board)
    pcb.SaveBoard(str(OUT / "esp32-ecu.kicad_pcb"), board)
    pcb.ExportSpecctraDSN(board, str(ROOT / ".cache" / "esp32-ecu.dsn"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-metadata", action="store_true",
                        help="Preserve copper/placement; reject any net or footprint change")
    args = parser.parse_args()
    LIB.mkdir(parents=True, exist_ok=True)
    (ROOT / ".cache").mkdir(exist_ok=True)
    (LIB / "ecu.pretty").mkdir(exist_ok=True)
    refs = [p.ref for p in PARTS]
    if len(refs) != len(set(refs)):
        raise RuntimeError("Duplicate references")
    for name in {p.footprint for p in PARTS}:
        group, stem = name.split(":")
        src = STOCK / "footprints" / (group+".pretty") / (stem+".kicad_mod")
        if not src.exists():
            raise RuntimeError("Missing stock footprint: "+str(src))
        shutil.copyfile(src, LIB / "ecu.pretty" / src.name)
    (OUT / "sym-lib-table").write_text('(sym_lib_table (version 7) (lib (name "ECU") (type "KiCad") (uri "${KIPRJMOD}/lib/ecu.kicad_sym") (options "") (descr "Project-local symbols")))')
    (OUT / "fp-lib-table").write_text('(fp_lib_table (version 7) (lib (name "ECU") (type "KiCad") (uri "${KIPRJMOD}/lib/ecu.pretty") (options "") (descr "Vendored KiCad footprints")))')
    project = {
        "meta": {"filename": "esp32-ecu.kicad_pro", "version": 1},
        "board": {"design_settings": {"rules": {"min_clearance": .2, "min_track_width": .2, "min_via_diameter": .6,
                   "min_through_hole_diameter": .2, "min_copper_edge_clearance": .4}}},
        "net_settings": net_settings(),
    }
    schematic()
    if args.update_metadata:
        board = pcb.LoadBoard(str(OUT / "esp32-ecu.kicad_pcb"))
        for p in PARTS:
            fp = board.FindFootprintByReference(p.ref)
            if fp is None or str(fp.GetFPID().GetLibItemName()) != p.footprint.split(":")[1]:
                raise RuntimeError("Metadata update changes footprint: "+p.ref)
            for pad in fp.Pads():
                n = pad.GetNumber()
                if not n: continue
                expected = p.pins[n] if p.pins[n] is not None else nc_net(p,n)
                if pad.GetNetname() != expected:
                    raise RuntimeError(f"Metadata update changes net: {p.ref}:{n}")
            fp.SetValue(p.value)
            fp.SetField("MPN",p.mpn)
            fp.SetField("DesignNote",p.note)
        pcb.SaveBoard(str(OUT / "esp32-ecu.kicad_pcb"),board)
    else:
        pcb_board()
        (OUT / "esp32-ecu.kicad_pro").write_text(json.dumps(project, indent=2))
    with (OUT / "bom.csv").open("w") as f:
        w = csv.writer(f)
        w.writerow(["Reference", "Value", "MPN", "Footprint", "DNP", "Design_note"])
        for p in PARTS:
            w.writerow([p.ref,p.value,p.mpn,"ECU:"+p.footprint.split(":")[1],p.dnp,p.note])
    manifest = {"revision": "A0", "status": "bench_prototype_not_vehicle_qualified", "gpio": GPIO,
                "parts": [vars(p) for p in PARTS]}
    (OUT / "net_contract.json").write_text(json.dumps(manifest, indent=2))
    lines = ["#pragma once", "// Generated by scripts/build_hardware.py from scripts/design.py.", "namespace ecu::pins {"]
    lines += [("#if defined(ECU_HAND_SOLDER_A1) || defined(ECU_THROUGH_HOLE_A2)\ninline constexpr int arm = 47;\n#else\ninline constexpr int arm = 38;\n#endif" if k == "ARM" else f"inline constexpr int {k.lower()} = {v};") for k,v in GPIO.items()]
    lines += ["}"]
    (ROOT / "firmware/include/ecu/pins.hpp").write_text("\n".join(lines)+"\n")
    print(f"Generated {len(PARTS)} parts, {len(PAGES)+1} schematic pages, 200 x 200 mm PCB")


if __name__ == "__main__":
    main()
