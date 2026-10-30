# A3-120 splash-resistant case prototype

PCB: 120 × 120 mm. Printed base: 138 × 150 × 44 mm. Lid: 142 × 154 mm. Nominal assembly: 47 mm high, excluding rear glands and harness bends.

Print `base.stl`, `lid.stl`, `insulating_tray.stl`, `lid_insulator.stl` and the insert coupon. STEP and native FreeCAD sources are supplied. Choose a print material and process based on measured installation temperature, fluids and vibration. No material/ingress qualification is implied.

Use the supplied hardware CSV. Four PCB supports, eight lid bosses and two internal shield-bond bosses take short RX-M3Sx4.0 M3 inserts; trial the coupon first. PCB screws are M3 × 6 with 0.8 mm nylon washers. Lid screws are M3 × 8 with 0.8 mm washers. The blind bores preserve the exterior floor/walls.

The H4 support has reliefs matching R35 and D210 solder tails. Trim tails to at most 3 mm below the board. Dry fit and check all clearances before applying power.

Cut the continuous gasket from 2 mm soft closed-cell silicone sheet, using `gasket-cut-template.svg` at 1:1 scale. The reference STEP is not a rigid-filament print part. The 3 mm wide ring sits in a 3.4 mm wide, 1.5 mm deep groove for nominal 25% compression. All eight lid screws lie outside this seal. The lid has an external drip skirt.

Four rear 16.2 mm holes accept suitable M16 glands or gasketed blanks. Maximum flange envelope is 24 mm diameter. Match the gland to the actual round cable jacket and use its panel sealing washer. A single-hole gland cannot seal loose individual wires. Use jacketed harness groups, external sealed branches, strain relief and drip loops.

Fit conductive lining using the templates. Bond lining seams and connect the internal base/lid bonds and PCB CHASSIS lug with short appropriate conductors. Do not create an unsealed external stud hole. Keep foil away from the gasket land. Fit the insulating tray and lid cover to protect electronics from the foil. The water gasket is not an electrical bond.

Nominal CAD collision, blind-floor, screw access, gasket layout and closed-mesh checks are in `fit-check.json` and `validation.json`. They do not prove physical fit, heat-insert strength, print porosity, splash resistance or EMI immunity. Test the empty assembled case with absorbent paper under controlled light splashes before installing electronics. No IP rating, submersion or pressure-wash capability is claimed.

For dry service Wi-Fi, open the lid; conductive lining can block RF. Opening the enclosure removes the splash barrier. Full instructions are in the PDF manual.
