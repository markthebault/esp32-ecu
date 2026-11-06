#!/usr/bin/env python3
"""Electrical design source. Units: mm. No vehicle pinout is assumed.

Each connection is explicit. build_hardware.py makes native KiCad files from
this source; firmware pin assignments are emitted from GPIO, not copied by hand.
"""
from dataclasses import dataclass


@dataclass
class Part:
    ref: str
    value: str
    footprint: str
    pins: dict
    names: dict
    types: dict
    page: str
    xy: tuple
    angle: float = 0
    mpn: str = ""
    note: str = ""
    dnp: bool = False


PARTS = []
GPIO = {
    "INJ1_CMD": 4, "INJ2_CMD": 5, "INJ3_CMD": 6, "INJ4_CMD": 7,
    "IGN1_CMD": 15, "IGN2_CMD": 16, "IGN3_CMD": 17, "IGN4_CMD": 18,
    "CRANK": 8, "CAM": 9, "ADC_CS": 10, "SPI_MOSI": 11,
    "SPI_CLK": 12, "SPI_MISO": 13, "CAN_TX": 14, "CAN_RX": 21,
    "ARM": 38, "WDI": 39, "SAFE_N_MON": 40,
    "I2C_SDA": 41, "I2C_SCL": 42, "UART_TX": 43, "UART_RX": 44,
    "PUMP_CMD": 2, "FAN_CMD": 1, "INTERLOCK": 48,
}


def add(ref, value, footprint, pins, page, xy, names=None, types=None,
        angle=0, mpn="", note="", dnp=False):
    p = Part(ref, value, footprint, {str(k): v for k, v in pins.items()},
             {str(k): v for k, v in (names or {}).items()},
             {str(k): v for k, v in (types or {}).items()}, page, xy, angle, mpn, note, dnp)
    PARTS.append(p)
    return p


RFP = "Resistor_SMD:R_0805_2012Metric"
CFP = "Capacitor_SMD:C_0805_2012Metric"
DFP = "Diode_SMD:D_SOD-323"
SO8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
SO14 = "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"
SO16 = "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm"


def r(ref, value, a, b, page, xy, **kw):
    return add(ref, value, RFP, {1: a, 2: b}, page, xy, **kw)


def c(ref, value, a, b, page, xy, footprint=CFP, **kw):
    return add(ref, value, footprint, {1: a, 2: b}, page, xy, **kw)


def header(ref, title, nets, page, xy, **kw):
    return add(ref, title, f"Connector_PinHeader_2.54mm:PinHeader_1x{len(nets):02d}_P2.54mm_Vertical",
               dict(enumerate(nets, 1)), page, xy, **kw)


def clamp(ref, net, page, xy):
    x, y = xy
    # BAT54WS-7-F, SOD323, pin 1 cathode, pin 2 anode.
    add(ref + "0", "BAT54WS", DFP, {1: net, 2: "GND"}, page, (x, y),
        names={1: "K", 2: "A"}, mpn="BAT54WS-7-F")
    add(ref + "1", "BAT54WS", DFP, {1: "+3V3", 2: net}, page, (x + 5, y),
        names={1: "K", 2: "A"}, mpn="BAT54WS-7-F")


# Logic supply. External F1 is deliberately not represented by an on-board fuse.
header("J1", "FUSED_KEY_12V", ["VBAT_FUSED", "GND"], "power", (18, 22),
       note="External 1 A fuse at source. Bench header, not a sealed vehicle connector.")
add("D1", "SMCJ24CA", "Diode_SMD:D_SMC", {1: "VBAT_FUSED", 2: "GND"},
    "power", (28, 25), mpn="SMCJ24CA-E3/57T",
    note="Bidirectional TVS. 24 V standoff; 38.9 V specified pulse clamp, not load-dump qualification.")
add("D2", "STPS5H100BY", "Package_TO_SOT_SMD:TO-252-2", {1: "VBAT_FUSED", 2: "VIN_PROT", 3: None},
    "power", (39, 25), names={1: "A", 2: "K"}, mpn="STPS5H100BY",
    note="100 V series reverse-polarity blocking diode; check forward loss and pulse stress.")
c("C1", "47u 63V", "VIN_PROT", "GND", "power", (42, 36),
  footprint="Capacitor_SMD:CP_Elec_8x10", note="Electrolytic, exact series must be qualified.")
c("C2", "2.2u 100V X7R", "VIN_PROT", "GND", "power", (48, 24),
  footprint="Capacitor_SMD:C_1210_3225Metric")
c("C3", "100n 100V", "VIN_PROT", "GND", "power", (48, 28))
add("U1", "LM5164QDDARQ1", "Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm",
    {1: "GND", 2: "VIN_PROT", 3: "UVLO", 4: "RON", 5: "FB", 6: "SAFE_N", 7: "BST", 8: "SW", 9: "GND"},
    "power", (57, 28), names={1: "GND", 2: "VIN", 3: "EN_UVLO", 4: "RON", 5: "FB", 6: "PGOOD", 7: "BST", 8: "SW", 9: "EP"},
    types={1: "power_in", 2: "power_in", 6: "open_collector", 8: "output", 9: "power_in"}, mpn="LM5164QDDARQ1")
r("R1", "316k 1%", "VIN_PROT", "UVLO", "power", (50, 35))
r("R2", "100k 1%", "UVLO", "GND", "power", (50, 39))
r("R3", "41.2k 1%", "RON", "GND", "power", (54, 39))
c("C4", "2.2n 50V C0G", "BST", "SW", "power", (61, 24))
add("L1", "33uH 2.5A Isat", "Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm", {1: "SW", 2: "+5V"},
    "power", (69, 28), mpn="SRP7028A-330M", note="2.5 A saturation and 2 A RMS ratings at stated vendor test conditions. Verify derating at temperature.")
c("C5", "22u 16V X7R", "+5V", "GND", "power", (78, 25), footprint="Capacitor_SMD:C_1210_3225Metric")
c("C6", "22u 16V X7R", "+5V", "GND", "power", (78, 31), footprint="Capacitor_SMD:C_1210_3225Metric")
r("R4", "316k 1%", "+5V", "FB", "power", (63, 37))
r("R5", "100k 1%", "FB", "GND", "power", (63, 41))
r("R6", "100k 1%", "SW", "RIPPLE", "power", (69, 39))
c("C7", "3.3n C0G", "RIPPLE", "+5V", "power", (74, 39))
c("C8", "100p C0G", "RIPPLE", "FB", "power", (69, 44))
add("U2", "NCV1117ST33T3G", "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
    {1: "GND", 2: "+3V3", 3: "+5V"}, "power", (91, 27),
    names={1: "GND", 2: "OUT", 3: "IN"}, types={1: "power_in", 2: "power_out", 3: "power_in"},
    mpn="NCV1117ST33T3G", note="Thermal budget <=200 mA continuous pending measurement. Requires output ESR review.")
c("C9", "22u 10V ESR 0.3-1R", "+3V3", "GND", "power", (101, 27),
  footprint="Capacitor_SMD:CP_Elec_6.3x5.8", note="Select exact electrolytic series to satisfy LDO stability over temperature.")
c("C10", "100n", "+3V3", "GND", "power", (96, 35))
r("R7", "100R 0.25W", "+3V3", "GND", "power", (104, 35),
  note="33 mA rail bleed provides a sink for fault clamp current. Must validate unpowered injection.")
add("F2", "PTC 100mA", "Fuse:Fuse_1812_4532Metric", {1: "+5V", 2: "SENSOR_5V"},
    "power", (81, 43), mpn="MF-MSMF010-2", note="Resettable fuse, slow thermal response; no precision current limit.")
c("C11", "1u", "SENSOR_5V", "GND", "power", (88, 43))

# Processor module and supervised reset. No radio is enabled by the firmware.
module_pins = {1: "GND", 2: "+3V3", 3: "EN", 40: "GND", 41: "GND"}
module_names = {1: "GND", 2: "3V3", 3: "EN", 40: "GND", 41: "EP"}
module_gpio = {4: 4, 5: 5, 6: 6, 7: 7, 8: 15, 9: 16, 10: 17, 11: 18,
               12: 8, 13: 19, 14: 20, 15: 3, 16: 46, 17: 9, 18: 10, 19: 11,
               20: 12, 21: 13, 22: 14, 23: 21, 24: 47, 25: 48, 26: 45, 27: 0,
               28: 35, 29: 36, 30: 37, 31: 38, 32: 39, 33: 40, 34: 41, 35: 42,
               36: 44, 37: 43, 38: 2, 39: 1}
reverse_gpio = {v: k for k, v in GPIO.items()}
for pin, gpio in module_gpio.items():
    module_pins[pin] = reverse_gpio.get(gpio, "BOOT_N" if gpio == 0 else None)
    module_names[pin] = "IO" + str(gpio)
module_types = {k: "bidirectional" for k in module_gpio}
module_types.update({1: "power_in", 2: "power_in", 3: "input", 40: "power_in", 41: "power_in"})
add("U3", "ESP32-S3-WROOM-1-N8", "RF_Module:ESP32-S3-WROOM-1", module_pins,
    "core", (39, 65), names=module_names, types=module_types, mpn="ESP32-S3-WROOM-1-N8",
    note="Industrial radio module, no automotive or functional safety qualification. Antenna faces left board edge.")
r("R8", "10k", "+3V3", "EN", "core", (24, 51))
c("C12", "1u", "EN", "GND", "core", (29, 51))
add("D3", "BAT54WS", DFP, {1: "SAFE_N", 2: "EN"}, "core", (34, 51),
    names={1: "K", 2: "A"}, mpn="BAT54WS-7-F", note="SAFE_N low discharges EN without EN capacitor delaying hardware inhibit.")
c("C13", "10u", "+3V3", "GND", "core", (33, 78))
c("C14", "100n", "+3V3", "GND", "core", (38, 78))
r("R9", "10k", "+3V3", "BOOT_N", "core", (24, 81))
header("J2", "UART_FLASH_3V3_ONLY", ["GND", "UART_TX", "UART_RX", "EN", "BOOT_N"], "core", (17, 86),
       note="External USB UART, 3.3 V logic. Supply board via J1; no USB backfeed.")
add("U4", "TPS3431SDRBRQ1", "Package_SON:VSON-8-1EP_3x3mm_P0.65mm_EP1.65x2.4mm",
    {1: "+3V3", 2: "WDT_SELECT", 3: "+3V3", 4: "GND", 5: "+3V3", 6: "WDI", 7: "SAFE_N", 8: "SAFE_N", 9: "GND"},
    "core", (56, 54), names={1: "VDD", 2: "CWD", 3: "EN", 4: "GND", 5: "SET1", 6: "WDI", 7: "WDO_N", 8: "ENOUT", 9: "EP"},
    types={1: "power_in", 4: "power_in", 7: "open_collector", 8: "open_collector", 9: "power_in"},
    mpn="TPS3431SDRBRQ1", note="1.6 s nominal watchdog with CWD floating. ENOUT and WDO wired AND. Pulse limiters provide shorter actuator ceilings.")
r("R10", "10k OPTIONAL 200ms", "+3V3", "WDT_SELECT", "core", (51, 47), dnp=True,
  note="DNP for 1.6 s boot allowance. Populate only after worst-case boot timing is measured.")
r("R11", "10k", "+3V3", "SAFE_N", "core", (58, 47))
r("R12", "100k", "WDI", "GND", "core", (65, 49))
c("C15", "100n", "+3V3", "GND", "core", (56, 61))
add("U5", "TLV803EA30DBZR", "Package_TO_SOT_SMD:SOT-23",
    {1: "GND", 2: "SAFE_N", 3: "+3V3"}, "core", (68, 55),
    names={1: "GND", 2: "RESET_N", 3: "VDD"}, types={1: "power_in", 2: "open_collector", 3: "power_in"}, mpn="TLV803EA30DBZR")
c("C16", "100n", "+3V3", "GND", "core", (68, 61))
r("R13", "1k", "SAFE_N", "SAFE_N_MON", "core", (64, 66))
header("J3", "NORMALLY_OPEN_INTERLOCK", ["+3V3", "INTERLOCK"], "core", (77, 56),
       note="Fit only on supervised dummy-load bench. Open contact forces output inhibit independent of MCU.")
r("R14", "10k", "INTERLOCK", "GND", "core", (77, 63))
r("R15", "10k", "ARM", "GND", "core", (77, 68))
header("J4", "EXPANSION_3V3", ["GND", "+3V3", "I2C_SDA", "I2C_SCL", "SAFE_N"], "core", (83, 87))
r("R16", "4.7k", "+3V3", "I2C_SDA", "core", (75, 84))
r("R17", "4.7k", "+3V3", "I2C_SCL", "core", (75, 89))

# Eight analog channels, six external signals plus battery and supply monitoring.
analog_signals = ["MAP", "TPS", "CLT", "IAT", "LAMBDA_WB", "POSTCAT_BUF"]
header("J5", "SENSOR_LOOM", ["SENSOR_5V", "GND"] + analog_signals + ["GND", "GND"], "analog", (18, 126))
for i, signal in enumerate(analog_signals):
    x, y = 33 + (i % 3) * 19, 109 + (i // 3) * 20
    net = f"ADC{i}"
    r(f"R{20+i*2}", "22k 1%", signal, net, "analog", (x, y))
    r(f"R{21+i*2}", "33k 1%", net, "GND", "analog", (x, y+4))
    c(f"C{20+i}", "10n", net, "GND", "analog", (x, y+8))
    clamp(f"D{10+i}", net, "analog", (x-2, y+12))
for i, signal in enumerate(["CLT", "IAT"]):
    r(f"R{32+i}", "2.49k 1% NTC", "SENSOR_5V", signal, "analog", (80+i*6, 113),
      note="Populate only for passive NTC sensor; transfer curve must match selected sensor.", dnp=True)
r("R34", "120k 1%", "VIN_PROT", "ADC6", "analog", (93, 108))
r("R35", "10k 1%", "ADC6", "GND", "analog", (93, 112))
c("C26", "10n", "ADC6", "GND", "analog", (93, 116))
clamp("D16", "ADC6", "analog", (90, 120))
r("R36", "22k 1%", "SENSOR_5V", "ADC7", "analog", (105, 108))
r("R37", "33k 1%", "ADC7", "GND", "analog", (105, 112))
c("C27", "10n", "ADC7", "GND", "analog", (105, 116))
clamp("D17", "ADC7", "analog", (102, 120))
add("U6", "MCP3208-CI/SL", SO16,
    {**{i+1: f"ADC{i}" for i in range(8)}, 9: "GND", 10: "ADC_CS", 11: "SPI_MOSI", 12: "SPI_MISO", 13: "SPI_CLK", 14: "GND", 15: "+3V3", 16: "+3V3"},
    "analog", (93, 135), names={**{i+1: f"CH{i}" for i in range(8)}, 9: "DGND", 10: "CS_N", 11: "DIN", 12: "DOUT", 13: "CLK", 14: "AGND", 15: "VREF", 16: "VDD"},
    types={9: "power_in", 12: "tri_state", 14: "power_in", 15: "power_in", 16: "power_in"}, mpn="MCP3208-CI/SL")
c("C28", "100n", "+3V3", "GND", "analog", (99, 128))
c("C29", "1u", "+3V3", "GND", "analog", (104, 128))
r("R38", "10k", "+3V3", "ADC_CS", "analog", (88, 144))

# Hall crank/cam only. VR requires a separate differential conditioner.
header("J6", "HALL_TRIGGERS", ["SENSOR_5V", "GND", "CRANK_RAW", "CAM_RAW"], "trigger_can", (18, 55))
for i, signal in enumerate(["CRANK", "CAM"]):
    x, y = 25, 56 + 11*i
    r(f"R{40+i*2}", "33k", signal+"_RAW", signal+"_FILT", "trigger_can", (x, y))
    c(f"C{30+i}", "100p C0G", signal+"_FILT", "GND", "trigger_can", (x+5, y))
    clamp(f"D{20+i}", signal+"_FILT", "trigger_can", (x+3, y+4))
    r(f"R{41+i*2}", "2.2k HALL PULLUP", "SENSOR_5V", signal+"_RAW", "trigger_can", (x-3, y+6), dnp=True)
add("U7", "SN74LVC2G17DBVR", "Package_TO_SOT_SMD:SOT-23-6",
    {1: "CRANK_FILT", 2: "GND", 3: "CAM_FILT", 4: "CAM", 5: "+3V3", 6: "CRANK"},
    "trigger_can", (34, 86), names={1: "1A", 2: "GND", 3: "2A", 4: "2Y", 5: "VCC", 6: "1Y"},
    types={2: "power_in", 4: "output", 5: "power_in", 6: "output"}, mpn="SN74LVC2G17DBVR")
c("C32", "100n", "+3V3", "GND", "trigger_can", (39, 86))

add("U8", "TCAN1051VDRQ1", SO8,
    {1: "CAN_TX", 2: "GND", 3: "+5V", 4: "CAN_RX", 5: "+3V3", 6: "CANL", 7: "CANH", 8: "CAN_SILENT"},
    "trigger_can", (66, 81), names={1: "TXD", 2: "GND", 3: "VCC", 4: "RXD", 5: "VIO", 6: "CANL", 7: "CANH", 8: "S"},
    types={2: "power_in", 3: "power_in", 4: "output", 5: "power_in", 6: "bidirectional", 7: "bidirectional"}, mpn="TCAN1051VDRQ1")
c("C33", "100n", "+5V", "GND", "trigger_can", (60, 77))
c("C34", "100n", "+3V3", "GND", "trigger_can", (60, 85))
r("R44", "10k", "+3V3", "CAN_SILENT", "trigger_can", (72, 74))
r("R45", "10k", "+3V3", "CAN_TX", "trigger_can", (66, 71))
header("JP1", "CAN_TX_ENABLE_OPEN", ["CAN_SILENT", "GND"], "trigger_can", (80, 74), note="Open by default. Silent hardware plus software listen-only.")
header("J7", "CAN_BUS", ["CANH", "CANL", "GND"], "trigger_can", (91, 77))
add("D22", "PESD2CAN", "Package_TO_SOT_SMD:SOT-23", {1: "CANH", 2: "CANL", 3: "GND"},
    "trigger_can", (84, 82), mpn="PESD2CAN,215")
r("R46", "120R", "CANH", "CAN_TERM", "trigger_can", (87, 91))
header("JP2", "CAN_TERMINATION_OPEN", ["CAN_TERM", "CANL"], "trigger_can", (94, 91))

# Global inhibit and relay outputs. HCT inputs accept 3.3 V at 5 V supply.
def and_gate(ref, groups, page, xy):
    pins = {7: "GND", 14: "+5V"}
    names = {7: "GND", 14: "VCC"}
    types = {7: "power_in", 14: "power_in"}
    for i, ((a, b, out), nums) in enumerate(zip(groups, [(1,2,3), (4,5,6), (9,10,8), (12,13,11)]), 1):
        for n, name, net in zip(nums, [f"{i}A", f"{i}B", f"{i}Y"], [a,b,out]):
            pins[n], names[n] = net, name
            types[n] = "output" if name.endswith("Y") else "input"
    return add(ref, "74HCT08D-Q100", SO14, pins, page, xy, names=names, types=types, mpn="74HCT08D-Q100,118")


and_gate("U9", [("ARM", "SAFE_N", "ARM_SAFE"), ("ARM_SAFE", "INTERLOCK", "RUN_5V"),
                ("PUMP_CMD", "RUN_5V", "PUMP_GATE"), ("FAN_CMD", "RUN_5V", "FAN_GATE")], "outputs", (124, 77))
c("C35", "100n", "+5V", "GND", "outputs", (118, 77))
r("R47", "10k", "RUN_5V", "GND", "outputs", (123, 88))
for i, signal in enumerate(["PUMP", "FAN", "MAIN"]):
    x, y = 144 + i*16, 82
    gate = "RUN_5V" if signal == "MAIN" else signal + "_GATE"
    r(f"R{48+i}", "1k", gate, signal+"_IN", "outputs", (x, y-10))
    r(f"R{51+i}", "10k", signal+"_IN", "GND", "outputs", (x+5, y-10))
    add(f"Q{5+i}", "VNL5050N3TR-E", "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        {1: signal+"_IN", 2: signal+"_LS", 3: "GND"}, "outputs", (x, y),
        names={1: "INPUT_5V", 2: "DRAIN", 3: "SOURCE"}, mpn="VNL5050N3TR-E",
        note="External fused relay coil only, <=150 mA. External coil flyback diode required.")
    if signal != "MAIN":
        r(f"R{54+i}", "10k", signal+"_CMD", "GND", "outputs", (x, y+10))
header("J8", "EXTERNAL_RELAYS", ["MAIN_LS", "PUMP_LS", "FAN_LS", "GND"], "outputs", (194, 77))

# Non-retriggerable pulse windows and command AND gates. No direct coil primaries.
for kind, base_y, gates_ref, monos, rc, cp in [
    ("INJ", 30, "U10", ["U12", "U13"], "100k 1%", "270n 5% FILM"),
    ("IGN", 121, "U11", ["U14", "U15"], "100k 1%", "68n 5% C0G")]:
    and_gate(gates_ref, [(f"{kind}{i}_CMD", f"{kind}{i}_WINDOW", f"{kind}{i}_LIMITED") for i in range(1,5)],
             "injectors" if kind == "INJ" else "ignition", (130, base_y))
    page = "injectors" if kind == "INJ" else "ignition"
    c("C36" if kind == "INJ" else "C37", "100n", "+5V", "GND", page, (123, base_y))
    # Reset the timing window as soon as the command ends. Without this,
    # a 19 ms non-retriggerable injector window would skip pulses at high RPM.
    and_gate("U16" if kind == "INJ" else "U17",
             [(f"{kind}{i}_CMD", "RUN_5V", f"{kind}{i}_RESET_N") for i in range(1,5)],
             page, (130,base_y+22))
    c("C42" if kind == "INJ" else "C43", "100n", "+5V", "GND", page, (123,base_y+22))
    for pair in range(2):
        nums = [1+pair*2, 2+pair*2]
        x = 151 + pair*26
        pins = {1: "GND", 2: f"{kind}{nums[0]}_CMD", 3: f"{kind}{nums[0]}_RESET_N", 4: None,
                5: f"{kind}{nums[1]}_WINDOW", 6: "GND", 7: f"{kind}{nums[1]}_RC", 8: "GND",
                9: "GND", 10: f"{kind}{nums[1]}_CMD", 11: f"{kind}{nums[1]}_RESET_N", 12: None,
                13: f"{kind}{nums[0]}_WINDOW", 14: "GND", 15: f"{kind}{nums[0]}_RC", 16: "+5V"}
        names = {1: "1A", 2: "1B", 3: "1RD_N", 4: "1Q_N", 5: "2Q", 6: "2CEXT", 7: "2REXT_CEXT", 8: "GND",
                 9: "2A", 10: "2B", 11: "2RD_N", 12: "2Q_N", 13: "1Q", 14: "1CEXT", 15: "1REXT_CEXT", 16: "VCC"}
        add(monos[pair], "74HCT221D", SO16, pins, page, (x, base_y), names=names,
            types={4: "output", 5: "output", 8: "power_in", 12: "output", 13: "output", 16: "power_in"}, mpn="74HCT221D,118",
            note="Industrial part. Non-retriggerable. Pulse cutoff is an independent ceiling, not a qualified safety mechanism.")
        c(f"C{38+(0 if kind=='INJ' else 2)+pair}", "100n", "+5V", "GND", page, (x, base_y-9))
        for j, num in enumerate(nums):
            px, py = x-6+j*12, base_y+12
            suffix = str((60 if kind == "INJ" else 80)+num)
            r("R"+suffix, rc, "+5V", f"{kind}{num}_RC", page, (px, py))
            c("C"+suffix, cp, f"{kind}{num}_RC", "GND", page, (px, py+5),
              footprint="Capacitor_SMD:C_1206_3216Metric")
            r("R"+str(int(suffix)+4), "10k", f"{kind}{num}_CMD", "GND", page, (px, py+10))
    for num in range(1,5):
        x, y = 124+(num-1)*20, base_y+30
        r(f"R{100+(0 if kind=='INJ' else 10)+num}", "1k" if kind == "INJ" else "220R",
          f"{kind}{num}_LIMITED", f"{kind}{num}_IN" if kind == "INJ" else f"{kind}{num}_5V", page, (x, y))
        r(f"R{104+(0 if kind=='INJ' else 10)+num}", "10k",
          f"{kind}{num}_IN" if kind == "INJ" else f"{kind}{num}_5V", "GND", page, (x+5, y))
        if kind == "INJ":
            add(f"Q{num}", "VNL5050N3TR-E", "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                {1: f"INJ{num}_IN", 2: f"INJ{num}_LS", 3: "GND"}, page, (x, y+10),
                names={1: "INPUT_5V", 2: "DRAIN", 3: "SOURCE"}, mpn="VNL5050N3TR-E",
                note="High impedance injector only. <=1.2 A/channel design target pending thermal and repetitive clamp tests.")
    nets = [f"{kind}{i}_LS" if kind == "INJ" else f"{kind}{i}_5V" for i in range(1,5)]
    nets += ["GND", "GND", "GND", "GND"] if kind == "INJ" else ["GND"]
    header("J9" if kind == "INJ" else "J10", "INJECTOR_LOW_SIDES" if kind == "INJ" else "SMART_COIL_5V_LOGIC",
           nets, page, (199, base_y-5), note="External fused, relay-switched actuator 12V. Header is bench-only.")

# Probe points and grounded mounting holes.
for i, (net, xy) in enumerate([("GND", (112,21)), ("VIN_PROT", (112,28)), ("+5V", (112,35)),
                              ("+3V3", (112,42)), ("SAFE_N", (112,55)), ("RUN_5V", (112,64))], 1):
    add(f"TP{i}", net, "TestPoint:TestPoint_Pad_D2.0mm", {1: net}, "core", xy)
for i, xy in enumerate([(14,14), (206,14), (14,156), (206,156)], 1):
    add(f"H{i}", "M3 NPTH", "MountingHole:MountingHole_3.2mm_M3", {}, "core", xy)

PAGES = ["power", "core", "analog", "trigger_can", "outputs", "injectors", "ignition"]
NOTES = {
    "power": "External F1 1 A at source. 12 V system only. Surge ratings require measured ISO/OEM pulse qualification. No cold-crank ride-through claim.",
    "core": "BENCH PROTOTYPE. Default firmware never asserts ARM. Interlock J3 open. SAFE_N asynchronously inhibits outputs and resets MCU.",
    "analog": "0-5 V conditioned signals only. J5 lambda must come from an external wideband controller. NTC pullups DNP until sensor curves are known.",
    "trigger_can": "Hall crank/cam only. VR sensors require a conditioner. CAN transmit and termination jumpers open by default. No OEM messages implemented.",
    "outputs": "External fused main/pump/fan relays required. MAIN relay contact supplies injector and coil 12 V. Add external coil flyback diodes.",
    "injectors": "Four saturated high-impedance PFI injectors. No GDI or peak-and-hold. 18.9 ms nominal hardware window; validate full tolerance range.",
    "ignition": "Active-high 5 V smart coils only, <=4 mA input. No direct coil primary drive. 4.76 ms nominal window; abort can cause a spark.",
}
