# A6 protected-flex and ordinary-RGB carrier draft

This separate120 x120mm six-layer native KiCad9 draft adds21 flex-input and22 RGB parts to the A5 logical design. Placement and all copper are new; old A3/A4/A5 sources remain preserved. **No fabrication, sensor connection, module/enclosure fit or physical engine release.**

[Native project](esp32-ecu.kicad_pro) · [Contract](net_contract.json) · [BOM](BOM.md) · [Carrier pinout](connector-pinout.csv) · [Circuit limits](../flex-input/README.md)

U3 pad32/GPIO38 receives only the protected flex candidate. Build compact_n16r8_flex_dev; historical GPIO38 WS2812/RMT firmware is incompatible. Physical engine outputs remain inhibited. MCP23008 at0x21 uses GP0/1/2 for red/green/blue through NPN sinks; GP3..7 stay low and NC. Steady green, blue pairing blink and red problem blink are advisory requests. Retained green does not prove live CPU, current readback or actual light.

J21 PH4 retains isolated idle logic. J22 VH3 carries1 GND,2 FLEX_12V,3 FLEX_RAW; FLEX_12V is not an18V regulator and the AEM external plug drawing remains unresolved. J23 PH5 carries1 LED_5V through R179330R,2 red cathode,3 green cathode,4 blue cathode,5 NC with no contact. All connectors are internal; sealing/optical-window and harness fit are separate work.

R179 is the upright330R MRS16 candidate on its smaller DIN0204 footprint. Match the stated body/rating, formed leads and actual assembly; thermal and case fit remain unqualified.

The compact frontend uses nine MRS16 0.4W P70 resistor candidates, R157 through R165. Their body envelope is a maximum3.6 x1.6mm; lead forming, assembled derating and heat remain unqualified. R155/R156/R166 retain their750R 0.6W selection. C158/C159 use C315 C0G parts; C160 and the added local3V3 bypass C164 use C315 X7R parts. Nominal100nF is not an effective-value or supply-impedance guarantee. The proposed0.8mm holes and2.54mm pitch require checking actual leads and formed pitch; the specified pitch tolerance can require forming. Use the manufacturer hand-solder preheat/thermal-shock guidance. J20 uses B2B-PH-K-S(LF)(SN), PHR-2 and two SPH-002T-P0.5S contacts for the internal CHASSIS shield/lining bond, with no normal load current. H5 remains the chassis lug. These component/package changes do not establish enclosure, module, electrical or physical fit. 

The N16R8 socket spacing, elevated stack, inward10mm antenna allowance and onboard RGB 47/48 conflict remain unverified. The current native routing/check status must be read from the contract and attached evidence; software/circuit/native checks do not qualify physical timing, RF, supply protection, thermal behavior, vehicle operation or splash resistance.
