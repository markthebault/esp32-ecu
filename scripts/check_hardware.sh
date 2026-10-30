#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$task_root"
mkdir -p reports
sh scripts/kicad.sh sch export netlist --format kicadxml -o reports/netlist.xml hardware/esp32-ecu.kicad_sch
sh scripts/kicad.sh sch erc --format json --exit-code-violations -o reports/erc.json hardware/esp32-ecu.kicad_sch
sh scripts/kicad.sh pcb drc --refill-zones --save-board --schematic-parity --format json --exit-code-violations -o reports/drc.json hardware/esp32-ecu.kicad_pcb
python3 scripts/verify_contract.py
