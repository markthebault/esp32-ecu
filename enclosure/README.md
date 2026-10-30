# ECU A1 printable box

Print `base.stl` and `lid.stl` separately, outside faces on the bed. `cable_blank.stl` is optional. Source CAD is `ecu-a1-enclosure.FCStd`; STEP files are provided for other CAD programs. The generator is `../scripts/build_enclosure.py` and uses FreeCAD's Python.

Assembled size 218 x 218 x 47 mm. Allow additional build area for a brim. Four PCB bosses match the A1 200 mm square PCB. Four lid screws and four 16.2 mm cable entries are included. Use measured glands/grommets and strain relief. See `../docs/hand-solder.md` for fasteners, material, printing and assembly details.

The render shows the real enclosure geometry and a green PCB envelope, not installed component models. Valid solids and closed meshes have been checked. Physical fit, heat, vibration and sealing have not been tested. Intended for a protected cabin/bench location, not the engine compartment.
