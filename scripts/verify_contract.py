#!/usr/bin/env python3
"""Check KiCad-exported nets against firmware pins and electrical invariants.

No external Python packages. This is independent of the CAD generator's
schematic serialization and catches mismatched net labels and physical pins.
"""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
design = ET.parse(ROOT / "reports/netlist.xml").getroot()
net_by_pin = {}
for net in design.findall("./nets/net"):
    for node in net.findall("node"):
        net_by_pin[(node.get("ref"), node.get("pin"))] = net.get("name")


def net(ref,pin,expected):
    actual = net_by_pin.get((ref,str(pin)))
    assert actual == expected, f"{ref}:{pin}: {actual!r} != {expected!r}"


# Module pad numbers from Espressif's module data sheet, not GPIO numbers.
physical_gpio = {4:4,5:5,6:6,7:7,8:15,9:16,10:17,11:18,12:8,
                 17:9,18:10,19:11,20:12,21:13,22:14,23:21,25:48,
                 31:38,32:39,33:40,34:41,35:42,36:44,37:43,38:2,39:1}
pins_text = (ROOT / "firmware/include/ecu/pins.hpp").read_text()
gpio = {name:int(value) for name,value in re.findall(r"int (\w+) = (\d+);",pins_text)}
assert len(set(gpio.values())) == len(gpio), "Duplicate MCU GPIO assignment"
assert set(gpio.values()).isdisjoint({0,3,19,20,26,27,28,29,30,31,32,33,34,35,36,37,45,46}), "Reserved/strap/USB/flash pin used"
inverse = {v:k.upper() for k,v in gpio.items()}
for pad,g in physical_gpio.items():
    net("U3",pad,inverse[g])
for pad in [1,40,41]: net("U3",pad,"GND")
net("U3",2,"+3V3")
for channel in range(1,5):
    net(f"Q{channel}",1,f"INJ{channel}_IN")
    net(f"Q{channel}",2,f"INJ{channel}_LS")
    net(f"Q{channel}",3,"GND")
    net("J9",channel,f"INJ{channel}_LS")
    net("J10",channel,f"IGN{channel}_5V")
for kind,refs in [("INJ",["U12","U13"]),("IGN",["U14","U15"])]:
    for pair,ref in enumerate(refs):
        a,b=pair*2+1,pair*2+2
        for pin,expected in [(2,f"{kind}{a}_CMD"),(3,f"{kind}{a}_RESET_N"),
                             (13,f"{kind}{a}_WINDOW"),(10,f"{kind}{b}_CMD"),
                             (11,f"{kind}{b}_RESET_N"),(5,f"{kind}{b}_WINDOW"),
                             (6,"GND"),(14,"GND"),(8,"GND"),(16,"+5V")]:
            net(ref,pin,expected)
net("U9",3,"ARM_SAFE");net("U9",5,"INTERLOCK");net("U9",6,"RUN_5V")
for ref,pin in [("U1",6),("U4",7),("U4",8),("U5",2)]: net(ref,pin,"SAFE_N")
net("D3",1,"SAFE_N");net("D3",2,"EN")
net("U8",3,"+5V");net("U8",5,"+3V3");net("U8",8,"CAN_SILENT")
for pin in range(1,9): net("U6",pin,f"ADC{pin-1}")

# Nominal design arithmetic, explicitly not transient/thermal qualification.
vout=1.2*(1+316000/100000)
fsw=vout*2500/41.2*1000
inductance_min=33e-6*.8
ripple_max=vout/(fsw*inductance_min)*(1-vout/38.9)
assert .4+ripple_max/2 < 1.25, "Buck peak exceeds minimum current limit at target load"
assert 5.25*(33330/(21780+33330)) < 3.235, "Analog divider exceeds low 3.3V rail with resistor tolerances"
analysis = {
    "kind": "nominal_calculations_not_measurements",
    "buck_vout_v": round(vout,4), "buck_frequency_hz": round(fsw),
    "buck_target_load_a": .4,
    "buck_inductor_ripple_a_at_38_9v_and_minus20percent_L": round(ripple_max,4),
    "buck_peak_a_at_target_load": round(.4+ripple_max/2,4),
    "ldo_loss_w_at_200ma": round((vout-3.3)*.2,3),
    "rail_bleed_w": round(3.3**2/100,4),
    "injector_nominal_max_window_ms": .7*100000*270e-9*1000,
    "ignition_nominal_max_window_ms": .7*100000*68e-9*1000,
    "limits": "No load-dump energy, EMC, repetitive injector avalanche, clamp tolerance, temperature, or current capacity is established by these calculations."
}
(ROOT / "reports/design-calculations.json").write_text(json.dumps(analysis,indent=2)+"\n")
print(f"PASS: {len(gpio)} GPIO assignments; physical module/driver/limiter/ADC/supervisor nets; nominal design arithmetic")
