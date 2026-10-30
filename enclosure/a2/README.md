# A2-R2: screw-mounted PCB and splash-resistant enclosure design

This mechanical revision uses the existing A2 PCB and its four corner holes. The PCB and firmware are unchanged. The new base and lid must be printed together; do not mix them with the older enclosure parts.

The design supports incidental splashes when assembled with the specified gasket, sealed glands and a sealed print surface. It has **not been splash-tested**, carries no IP rating, and is not intended for immersion, pressure washing or engine-bay installation.

## Print these parts

- `base.stl`: integrated PCB supports, blind insert bores, eight lid fasteners and gasket groove.
- `lid.stl`: matching lid with a surrounding rain skirt and internal shield-bond boss.
- `insulating_tray.stl`: revised dielectric liner, relieved around the supports.
- `lid_insulator.stl`: matching cover, relieved around the gasket land and lid-bond boss.
- `insert_fit_coupon.stl`: optional small first print to check insert fit. Left-to-right bores are 4.0, 4.1 and 4.2 mm.

The base remains 218 x 218 x 44 mm. The overhanging lid is **222 x 222 mm**, giving an assembled outer size of 222 x 222 x 47 mm. Allow at least a 222 mm printable area, or 232 mm with a 5 mm brim. Print outside base/lid faces on the bed and the cavities facing up. Print the tray open upward and the lid insulator flat, then orient its boss relief to the matching lid boss.

Start with 0.2 mm layers, six perimeters and enough top/bottom layers for the modeled 3 mm solid floor/lid. Use solid local infill around support bosses and insert holes. Actual slicer paths, extrusion and material matter. Supports may be required at horizontal gland holes; remove them completely. The surface and gasket land must be smooth and continuous.

An FDM print is not automatically watertight. Inspect and seal the printed body and lid using a compatible coating/sealant according to its manufacturer's directions. Do not fill the gasket groove or threads, and do not assume that a thicker or “100% infill” print has been leak-tested. PETG can be used for a cool first bench build; thermal suitability and sealing must be established on the actual assembly. [Prusa's watertight-print guidance](https://help.prusa3d.com/article/watertight-prints_112324)

## Screw the PCB onto the four supports

The supports are **10 mm diameter, 6 mm above the floor**, with flared roots. Centers in case coordinates are (13,13), (205,13), (13,205), (205,205) mm. They match H1-H4 of the actual KiCad board. The complete 3 mm exterior floor remains intact below their blind bores.

Use four **ruthex RX-M3Sx4.0 short M3 inserts**, four **M3 x 6 mm screws**, and four **0.8 mm nylon washers, about 6 mm OD**, under the screw heads. The nominal insert bore is 4.0 mm diameter and 4.9 mm deep. Use the coupon to check your printer/material, then adjust the bore parameter if required. Different insert products need their own bore geometry. [Insert manufacturer and installation information](https://www.ruthex.de/en/products/ruthex-gewindeeinsatz-m3s-100stuck-rx-m3x4-0-short-messing-gewindebuchsen-fur-3d-druck)

Install inserts **before** the electronics or lining. Recess their top faces 0.4 mm below the printed support tops so the PCB rests on plastic. Allow the plastic to cool completely. Install the lining, then the insulating tray, then place the PCB on the supports. Fit the nylon washers and M3 x 6 screws and tighten gently. Do not use a longer screw that bottoms out and cracks the boss. The nominal thread engagement is about 3.2 mm with the specified board and washer thickness.

Trim and inspect the underside leads. The PCB underside is at z=9 mm and the tray floor top is z=4.2 mm, leaving 4.8 mm before protruding solder joints or shield-lug hardware. The separate H5 shield lug still needs its own M3 bolt/nut and braid; it is not a fifth mechanical PCB support.

## Seal the lid

The water seal is a single closed ring cut from **2.0 mm soft closed-cell silicone gasket sheet**, 3.0 mm wide. Use `gasket-cut-template.svg` at **100% scale**; do not fit it to a smaller page. Use A3 paper or carefully tiled templates if necessary. `gasket-sheet-reference.step` is reference CAD. The gasket is **not** a filament-print part. Prefer a soft water-sealing grade with low closure force, approximately 20 kPa or less at 25% compression; confirm suitability with the material supplier. Hard rubber needs substantially more clamping force and is not a direct substitute. [Rogers enclosure-seal design guidance](https://www.rogerscorp.com/blog/2025/the-mechanics-of-enclosure-seal-design-gap-spacing-cfd-and-compressibility)

The groove is 3.4 mm wide and 1.5 mm deep, giving **25% nominal gasket compression** when the lid seats on the printed lands. Keep the gasket continuous, clean and untwisted. A splice or poor cut can leak. Check the printed groove depth and lid flatness; printer tolerances determine actual compression.

Fit **eight short M3 inserts**, eight **M3 x 8 mm lid screws**, and eight **0.8 mm flat washers**. The screws are outside the water-seal loop and enter blind bores. Tighten in a crossing pattern in small increments until the lid seats evenly. Do not force the lid to compensate for a warped print or an unsuitable hard gasket. The surrounding skirt sheds water away from the joint.

## Seal the cable entries

The four rear openings are 16.2 mm diameter, with centers x=40/85/130/175 mm, z=27 mm. Use **M16 cable glands with panel sealing washers**, matched to the actual cable-jacket diameter, or **gasketed M16 blanking plugs** for unused openings. The gland/flange envelope must be no larger than **24 mm OD** to clear the rain skirt. Follow the gland maker's panel thickness, hole and tightening requirements.

A normal single-hole gland seals around **one intact round cable jacket**. Do not push several loose wires through it and assume the gaps are sealed. Use jacketed multicore loom cables, or an appropriate multi-hole sealing insert designed for the individual wires. Provide strain relief and a drip loop outside. The internal XH/VH connectors remain unsealed and must stay dry inside the box.

## Keep the shield bond inside the sealed box

There is no exterior shield-stud hole in R2. An internal M3 insert boss at (210,157,14) mm, with a horizontal blind bore bonds the base lining, and a matching blind boss in the lid bonds its lining. Pre-fit the base bond and braid before installing the PCB; its screw is accessed horizontally from the empty cavity. Use short flexible braid and ring terminals. Two M3 x 5 screws with star washers/terminals are included in the hardware list; provide at least 1 mm of terminal/washer stack and check that the screws do not bottom out.

Connect H5 to the internal base bond, and connect the lid lining with a flexible internal braid that can be disconnected for servicing. A chassis-reference wire, if required by the installation, must pass through a sealed cable entry. Conductive cable-shield clamps/glands must also bond to the lining as appropriate.

The conductive lining and dielectric covers stop **inside** the water seal. Use the revised shield templates; trim wall lining at posts and keep it below the upper gasket land. Never run foil, braid or seam tape across the water gasket or through the lid joint. The lid template is viewed from its inside/print orientation and includes the boss relief. The dielectric cover must fully cover foil edges near the electronics. A DC braid connection does not establish RF shielding attenuation; EMI performance remains unmeasured.

## First fit and splash check

`hardware.csv` lists the physical fasteners, inserts, gasket and glands to purchase. CAD checks report closed meshes, aligned mounting holes, an intact floor, a continuous seal, and no nominal collisions. These checks establish geometry only; they do not prove screw retention, printed fit, gasket pressure or water resistance.

Test the **empty, unpowered** box before installing electronics. Install the actual gasket, lid screws, glands with representative jacketed cables, and blanking plugs. Place dry absorbent paper inside. Apply gentle splashes from above and the sides, without a pressure jet or submersion. Dry the exterior before opening and inspect the paper, gland entrances, screw regions and floor. Any moisture means the assembly needs correction and another test. Recheck after repeated lid opening and after exposure to the intended operating temperature. This procedure is a practical first check, not a certified ingress test.
