#!/usr/bin/env python3
"""Generate A3 assembly and grouped purchasing BOMs from the native net contract.
No stock, price, substitution or automotive qualification claim is made.
"""
import csv,json,re
from collections import defaultdict
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'hardware/a3-compact'
contract=json.loads((O/'net_contract.json').read_text());parts=contract['parts']
def natural(s):return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)',s)]
def esc(s):return str(s).replace('|','\\|').replace('\n',' ')
# Preserve the per-reference assembly contract used by KiCad reviews.
with (O/'bom.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Reference','Value','MPN','Footprint','DNP','Assembly','Note'])
 for p in parts:w.writerow([p['ref'],p['value'],p['mpn'],p['footprint'],p['dnp'],'Purchased assembled module' if p['ref'] in ['U1','U3'] else 'PCB feature' if p['ref'].startswith(('H','TP')) else 'Through hole',p['note']])
def requirements(p):
 value=p['value'];fp=p['footprint'];notes=[]
 if p['ref'].startswith('R'):
  notes.append('Axial DIN0207 body 6.3 x 2.5 mm; '+('10.16 mm horizontal lead pitch; at least 0.5 W' if p['ref']=='R150' else 'upright, 2.54 mm lead pitch; use the stated power/tolerance'))
 elif fp.startswith('Capacitor_THT:CP_'):
  notes.append('Polarized radial electrolytic, body diameter <=8 mm, 3.50 mm lead pitch; check height and exact voltage/temperature/ESR')
 elif 'C_Rect_' in fp:notes.append('Leaded film/boxed capacitor, body <=7.2 x 5.0 mm, lead pitch 5.00 mm; retain stated film type/tolerance')
 elif 'C_Disc_' in fp:notes.append('Leaded ceramic, body <=5.0 x 2.5 mm, lead pitch 5.00 mm; retain stated C0G/rating where specified')
 if p['ref']=='U3':notes.append('Exact 44-pin DevKitC-1 v1.1 / N8R8; two 22-pin rows 22.86 mm apart. Female headers are separate lines below. Prefer a pre-pinned module.')
 if p['ref']=='U1':notes.append('Pololu product #3792. Upright mounting uses an appropriate supplied 1x4 right-angle header; verify SHDN/VIN/GND/VOUT orientation.')
 if p['ref']=='C9':notes.append('Specified ESR target 0.3-1 ohm; exact series must be reviewed for LD1117 stability over temperature')
 if not p['mpn']:notes.append('Select exact manufacturer part to match value, package, lead pitch and operating conditions; unspecified ratings still need engineering selection')
 return '; '.join(notes)
groups=defaultdict(list)
for p in parts:
 if p['ref'].startswith(('H','TP')):continue
 groups[(p['value'],p['mpn'],p['footprint'],p['dnp'])].append(p)
rows=[]
for key,items in sorted(groups.items(),key=lambda pair:natural(min((p['ref'] for p in pair[1]),key=natural))):
 value,mpn,fp,dnp=key;refs=sorted([p['ref'] for p in items],key=natural);notes=list(dict.fromkeys(requirements(p) for p in items));design_notes=list(dict.fromkeys(p['note'] for p in items if p['note']))
 rows.append({'Section':'PCB','Quantity':0 if dnp else len(items),'Optional quantity':len(items) if dnp else 0,'Item':value,'MPN / specification':mpn or 'Select exact part','References / use':', '.join(refs),'Package / fit':fp,'Selection status':'Optional - DNP' if dnp else 'MPN specified; stock not checked' if mpn else 'Exact part selection required','Notes':' | '.join(notes+design_notes)})
def extra(section,qty,item,mpn,use,fit,notes='',optional=0,status='Select exact part for fit'):
 rows.append({'Section':section,'Quantity':qty,'Optional quantity':optional,'Item':item,'MPN / specification':mpn,'References / use':use,'Package / fit':fit,'Selection status':status,'Notes':notes})
extra('Board / modules',1,'Fabricated A3-120 PCB','Use manufacturing/a3 and native KiCad project','Carrier','120 x 120 x 1.6 mm; six copper layers','Prototype; review fabrication notes and generic BOM selections before ordering')
extra('Board / modules',2,'ESP32 female socket strips','1x22, 2.54 mm, through-hole','U3 left/right socket rows','Two strips; row spacing 22.86 mm','Required in addition to the DevKit. No DIP IC sockets are required; check actual mating height.')
extra('Board / modules',0,'DevKit male pin strips if not supplied','1x22, 2.54 mm, through-hole','Only for an unpinned DevKit','Two matching strips','Do not order extra if the DevKit already has the required pins.',optional=2)
# Count each connector once, rather than once per pin in the pinout CSV.
connectors={}
with (O/'connector-pinout.csv').open() as f:
 for r in csv.DictReader(f):
  ref=r['Connector']
  if ref not in connectors:connectors[ref]={'housing':r['Mating housing'],'pins':0}
  connectors[ref]['pins']+=1
housings=defaultdict(list);contact_counts={'XH':0,'VH':0}
for ref,c in connectors.items():
 housing=c['housing']
 if housing.startswith(('XHP-','VHR-')):
  housings[housing].append(ref);contact_counts['XH' if housing.startswith('XHP-') else 'VH']+=c['pins']
for housing,refs in sorted(housings.items()):extra('Harness',len(refs),'Mating crimp housing',housing,', '.join(sorted(refs,key=natural)),'JST '+('XH 2.50 mm' if housing.startswith('XHP') else 'VH 3.96 mm'),'Board headers are already counted in the PCB section. These are the cable-side housings.',status='Manufacturer family identified; stock not checked')
extra('Harness',contact_counts['XH'],'JST XH crimp contacts','SXH-001T-P0.6','All XH mating housings','AWG 28-22; use matching crimp tooling','Maximum all-cavity count, without spares. Populate only the pins used by the actual sensor wiring.',status='Contact family identified; match actual wire')
extra('Harness',contact_counts['VH'],'JST VH crimp contacts','SVH-21T-P1.1 OR SVH-41T-P1.1','All VH mating housings','21T: AWG 22-18; 41T: AWG 20-16','This is one combined quantity across both options, not this quantity of each. Choose by actual wire gauge and load; maximum all-cavity count without spares.',status='Wire-dependent selection required')
extra('Harness',2,'Five-position service plug','1x5 female crimp housing + matching contacts','J2 UART and J4 expansion','2.54 mm single row','Internal service only. J2 uses 3.3 V logic and no adapter power wire.')
extra('Harness',1,'Interlock mating plug','1x2 female crimp housing + matching contacts','J3','2.54 mm single row','Keep open during bench service; optional switch is a normally-open dry contact.')
extra('Harness',0,'Jumper shunt caps','2.54 mm two-pin shunt','JP1 receive enable / JP2 termination','Standard 2.54 mm pitch','Normally open. Fit only as described in the manual.',optional=2)
hardware=list(csv.DictReader((R/'enclosure/a3/hardware.csv').open()))
for r in hardware:
 item=r['Item'];qty=int(r['Quantity'])
 if 'M3 x 5 mm screws with' in item or 'M3 x 6 mm bolt, nut' in item:continue
 extra('Enclosure',qty,item,item,r['Use'],'See enclosure/a3/dimensions.json and assembly manual')
extra('Enclosure',2,'Internal bond screws','M3 x 5 mm pan-head','Base and lid shield-bond bosses','Use the specified terminal/washer stack')
extra('Enclosure',1,'PCB shield-lug bolt','M3 x 6 mm','H5','Check underside nut clearance')
extra('Enclosure',1,'PCB shield-lug nut','M3 nut','H5','Check underside clearance')
extra('Enclosure',3,'Shield-bond ring terminals','M3 hole; match the selected bond conductor','H5, internal base and lid bonds','Use the specified stack thickness')
extra('Enclosure',3,'Shield-bond star washers','M3','H5, internal base and lid bonds','Ensure electrical contact without an unsealed wall penetration')
extra('Enclosure',1,'Conductive lining and bond set','Conductive foil/coating + conductive seam bonds + insulated braid','Base/lid lining, J20/H5 and internal bonds','Cut/fit to supplied templates','Quantity is one build set; select actual material and wire length after checking fit. Keep clear of gasket and electronics.')
extra('Enclosure',1,'Print-material allowance','Suitable filament for actual temperature, fluids and printer','Base, lid, tray, lid insulator and coupon','Use enclosure/a3 STL/STEP','Quantity is one print set, not one kilogram; slicer determines mass. Gasket and conductive lining are separate materials.')
extra('External / bench',1,'External logic-supply fuse and holder','1 A fuse + compatible inline holder','J1 fused 12 V input','Off-board','Fuse characteristic/voltage/interruption rating and wire protection need actual installation review.')
extra('External / bench',1,'Bench programming / diagnostic adapter','3.3 V logic USB-UART, 115200 baud','J2','Off-board equipment','Do not connect adapter power; remove carrier-powered DevKit before powering its USB port.')
extra('External / bench',1,'Bench supply and measurement tools','Current-limited 12 V supply, multimeter and suitably referenced oscilloscope','Commissioning','Off-board equipment','Equipment allowance only, not per-board installed parts.')
fields=list(rows[0])
with (O/'bom-shopping.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
counts={'footprints':len(parts),'pcb_component_references':sum(len(g) for g in groups.values()),'fitted_pcb_component_references':sum(len(g) for k,g in groups.items() if not k[-1]),'dnp_references':sorted([p['ref'] for p in parts if p['dnp']],key=natural),'fabricated_features_not_purchase_parts':[p['ref'] for p in parts if p['ref'].startswith(('H','TP'))],'pcb_purchase_groups':len(groups),'XH_contact_positions':contact_counts['XH'],'VH_contact_positions':contact_counts['VH']}
# Every physical component reference must occur exactly once in the grouped PCB section.
actual=[ref for row in rows if row['Section']=='PCB' for ref in row['References / use'].split(', ')];expected=[p['ref'] for p in parts if not p['ref'].startswith(('H','TP'))]
assert len(actual)==len(set(actual)) and set(actual)==set(expected)
assert all(row['Quantity']==0 for row in rows if row['Selection status']=='Optional - DNP')
(R/'reports/a3/bom-summary.json').write_text(json.dumps(counts,indent=2))
def package(fp):
 if 'DIN0207' in fp:return 'DIN0207 axial / '+('10.16 mm horizontal' if 'Horizontal' in fp else '2.54 mm upright')
 if ':DIP-' in fp:return fp.split(':')[1].replace('_W',' / W').replace('_LongPads','')
 if 'CP_Radial_' in fp:return 'Radial electrolytic / D8 / P3.50 mm'
 if 'C_Disc_' in fp:return 'Ceramic disc / D5 / P5.00 mm'
 if 'C_Rect_' in fp:return 'Boxed film / 7.2 x 5 / P5.00 mm'
 if 'TO-220' in fp:return 'TO-220-3 vertical'
 if 'TO-92' in fp:return 'TO-92, wide inline'
 if 'DevKitC' in fp:return 'Plug-in DevKit / 2x22'
 if 'Pololu' in fp:return 'Upright purchased module'
 return fp.split(':')[-1].replace('_',' ')
lines=['# A3-120 bill of materials','',f'Quantities are for **one board and one enclosure**. The design has {counts["fitted_pcb_component_references"]} fitted electronic component references and four optional DNP resistors. The two ESP32 female socket strips are additional purchases.','', '[Download grouped shopping CSV](bom-shopping.csv) · [Per-reference assembly CSV](bom.csv) · [Connector pinout](connector-pinout.csv)','', 'Rows marked **Exact part selection required** are specification lines, not fully sourced parts. Select the actual manufacturer part and confirm lead pitch, body size, ratings, ESR and temperature range. Prices and stock are not validated by this BOM. The design remains a bench prototype with outputs disabled.','', 'H1-H4 mounting holes, H5 plated shield lug and TP1-TP6 test pads are fabricated PCB features, not extra electronic parts. H5 hardware is counted with the enclosure hardware. The ESP32 uses sockets; the other DIP chips solder directly to the carrier.','', 'C5/C6 are 22 uF, 16 V radial electrolytics on the 5 V rail. Their stale X7R wording has been corrected to match the existing footprint. C9 still requires an exact electrolytic series with the stated ESR target and regulator stability review.','']
for section in dict.fromkeys(row['Section'] for row in rows):
 lines+=['## '+section,'','| Qty | Optional | Item | MPN / specification | References / use | Package | Selection |','| ---: | ---: | --- | --- | --- | --- | --- |']
 for row in rows:
  if row['Section']==section:lines.append('| '+' | '.join(esc(package(row[k]) if k=='Package / fit' and section=='PCB' else row[k]) for k in ['Quantity','Optional quantity','Item','MPN / specification','References / use','Package / fit','Selection status'])+' |')
 lines+=['']
lines+=['## Selection and assembly notes','', '- Ordinary axial resistors mount upright on 2.54 mm pitch; R150 remains horizontal and needs the stated power rating in the selected body size. Match specified resistor/capacitor tolerance and C0G/film requirements.','- Radial electrolytics use 3.50 mm lead pitch and an 8 mm diameter envelope. Boxed film and disc ceramic footprints use 5.00 mm lead pitch. Confirm height and actual lead dimensions.','- The mating-housing list counts one plug per connector. The contact list is the maximum all-cavity count: 28 XH and 23 VH positions before spares. Leave unused cavities empty, including the supply cavity on passive NTC and externally powered controller interfaces.','- The two VH contact options share one combined quantity. Select the correct terminal for each wire; do not buy the total quantity of both options by mistake. Check actual wire lengths, shields, branches and crimp tooling separately.','- Vehicle-side sensor plugs, sensors, external wideband controller, VR conditioner, relays, coils, injectors and actuator branch fuses are installation-dependent and are not specified by this generic carrier BOM.','- Printed base/lid, insulating tray, lid insulator and coupon come from the supplied files. Gasket sheet, conductive lining, glands and metal hardware are separate purchases. Select actual gland/blank parts for the cable jackets and the stated 24 mm flange envelope.','', 'Manufacturer references: [Pololu D36V6F5 / #3792](https://www.pololu.com/product/3792), [JST XH housings and contacts](https://www.jst-mfg.com/product/pdf/eng/eXH.pdf), [JST VH housings and contacts](https://www.jst-mfg.com/product/pdf/eng/eVH.pdf).','', 'Regenerate with `python3 scripts/build_bom.py`. The native `net_contract.json`, connector pinout and enclosure hardware CSV are the inputs.','']
(O/'BOM.md').write_text('\n'.join(lines));print(json.dumps(counts,indent=2));print('Wrote BOM.md, bom-shopping.csv and refreshed per-reference bom.csv')
