#!/usr/bin/env python3
"""Create a separate provisional module-fit revision, retaining routed A3 sources.
No A4 Gerbers are released: row spacing and real module dimensions remain unmeasured.
The electrical routing is unchanged; status LED is wired to unused socket pad 32.
"""
import json, shutil, re, subprocess, sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
O=R/'hardware/a4-n16r8'
if O.exists():
    raise SystemExit('A4 already exists; review changes explicitly rather than overwriting it.')
shutil.copytree(R/'hardware/a3-compact',O)
c=json.loads((O/'net_contract.json').read_text())
c.update(revision='A4-N16R8-PROVISIONAL',status='HOLD_FOR_MODULE_FIT_AND_RF_CHECK',physical_fit_tested=False)
u=next(p for p in c['parts'] if p['ref']=='U3')
old=u['value'];u['value']='ESP32-S3 44-pin Type-C N16R8';u['mpn']='AliExpress 1005006418608267 / S3-N16R8'
u['note']='User-selected 16MB flash / 8MB PSRAM. 44-pin order from saved supplier pinout. Socket row spacing 22.86mm PROVISIONAL. Inward antenna extension 10mm; module PCB underside +8.5mm above carrier top is an assumed socket stack. Internal RGB pin is disputed (47 pinout / 48 schematic). Use separate RGB LED on GPIO38, socket pad32; no engine pulses. Verify actual board fit and RF performance before fabrication/use.'
c['selected_module']={'variant':'N16R8','flash_bytes':16777216,'psram_bytes':8388608,'header_rows':2,'pins_per_row':22,'pin_pitch_mm':2.54,'row_spacing_mm':22.86,'row_spacing_verified':False,'antenna_orientation':'inward over carrier','antenna_extension_from_first_header_mm':10,'module_underside_above_carrier_mm':8.5,'socket_stack_verified':False,'supplier_rgb_pin_conflict':[47,48],'status_led':'Separate WS2812 on GPIO38 (U3 pad32); built-in RGB unused','reference_pdf':'../references/esp32-s3-44pin-aliexpress.pdf','reference_pinout':'../references/esp32-s3-44pin-pinout.png','manufacturing_release':False}
(O/'net_contract.json').write_text(json.dumps(c,indent=2)+'\n')
# Preserve all pad numbers/nets and routing. Only purchase/fit metadata changes.
for p in list(O.glob('*.kicad_sch'))+[O/'lib/ecu.kicad_sym',O/'esp32-ecu.kicad_pcb']:
    s=p.read_text().replace(old,u['value'])
    # Replace old module identification in human-visible fields.
    s=s.replace('ESP32-S3-DevKitC-1-N8R8','ESP32-S3 44-pin Type-C N16R8')
    s=s.replace('A3 COMPACT 120mm','A4 N16R8 FIT HOLD').replace('A3-120','A4-N16R8 PROVISIONAL')
    p.write_text(s)
# Board file has a future KiCad 10 format. A textual change to metadata does not
# claim fresh native ERC/DRC; inherited A3 reports are deliberately not copied here.
for p in [O/'bom.csv',O/'bom-shopping.csv',O/'BOM.md']:
    if p.exists():
        s=p.read_text().replace(old,u['value']).replace('ESP32-S3-DevKitC-1-N8R8','ESP32-S3 44-pin Type-C N16R8')
        s=s.replace('Exact 44-pin DevKitC-1 v1.1 / N8R8; two 22-pin rows 22.86 mm apart.','Selected AliExpress N16R8; 44-pin order matches. Row spacing 22.86 mm and socket stack are PROVISIONAL, not measured.')
        s=s.replace('Use manufacturing/a3 and native KiCad project','HOLD: no manufacturing release for A4; module fit and antenna checks pending')
        s=s.replace('A3-120','A4-N16R8 provisional')
        p.write_text(s)
# Standalone footprint and placed footprint envelope: extend the antenna end
# inward by 10 mm from the first header. Copper/routing remains inherited.
fp=O/'lib/ecu.pretty/ESP32_S3_DevKitC_1_socket.kicad_mod'
s=fp.read_text().replace('-6.4','-10.0')
fp.write_text(s)
(O/'module-fit.json').write_text(json.dumps(c['selected_module'],indent=2)+'\n')
(O/'README.md').write_text("# A4 N16R8 module-fit draft\n\nSelected module: **AliExpress 44-pin dual Type-C ESP32-S3 N16R8**, 16 MB flash and 8 MB PSRAM. The unchanged supplier PDF and pinout image are in `../references/`. The PDF's selected cart option says N8R2; Mark explicitly selected **N16R8** in this conversation.\n\nThis is a separate copy of A3 with the selected module recorded. The 120 × 120 mm outline, routed nets, 2 × 22 sockets and all engine-output inhibition remain inherited. Existing A3 manufacturing files and packaged firmware target the earlier module and have not been relabelled as A4 releases.\n\n**Fabrication hold:** 44 pins do not define row spacing, module width or socket stack height. The 22.86 mm row spacing and 8.5 mm raised underside are provisional. A 10 mm antenna extension is reserved inward from the first header row. The placed module model uses a new provisional raised envelope with the 10 mm inward extension; it is not a fit-qualified model of the selected board. Do not use it to establish the new module's clearance.\n\nThe antenna points toward the PCB interior. Elevating the module does not eliminate antenna detuning from carrier copper, tall components, foil lining or lid metal. The inherited rule area is an A3 provision; the new 10 mm antenna envelope and RF clearance need review against actual module geometry. Do not place other parts under the radiating portion based on elevation alone. The conductive case lining may prevent closed-box ESP-NOW reception. A dielectric antenna window/lining exclusion needs prototype range tests before release.\n\nThe pinout image labels the onboard RGB at GPIO47; the listing schematic labels it GPIO48. Both are used by A3 (ARM / interlock). **Do not drive either as an LED.** The selected firmware uses a separate WS2812 status LED on unused GPIO38, accessible at U3 socket pad 32. Use a short internal signal wire and matching GND/supply. GPIO38 must remain disconnected from every other accessory. The module's onboard RGB is unused. No bench pulse firmware is permitted for this module selection.\n\nPAIR/BOOT and RESET dry contacts connect to the existing J2 service header. See [wireless setup and sealed button wiring](../../docs/espnow.md). Native KiCad files retain the same electrical nets; no fresh A4 ERC/DRC or mechanical-fit pass is claimed. KiCad 10 is required for these inherited sources.\n")
subprocess.run([sys.executable,str(R/'scripts/update_n16r8_envelope.py')],check=True)
subprocess.run([sys.executable,str(R/'scripts/update_n16r8_bom.py')],check=True)
print(O)
