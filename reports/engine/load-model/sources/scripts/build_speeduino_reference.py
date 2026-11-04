#!/usr/bin/env python3
"""Build a real pinned Speeduino fuel-calculation reference, not a formula clone."""
import argparse,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];PIN='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=R.parent/'speeduino');args=p.parse_args();src=args.source.resolve()
sha=subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()
if sha!=PIN:raise SystemExit('Reference SHA mismatch; audit and update the lock explicitly')
build=src/'.pio/build/native_code_coverage';deps=src/'.pio/libdeps/native_code_coverage';out=R/'.cache/engine';out.mkdir(parents=True,exist_ok=True)
if not (build/'src/fuel_calcs.o').exists():raise SystemExit('Run pio test -e native_code_coverage -f test_fuel -f test_tables in the reference checkout first')
includes=[src/'speeduino',src/'lib/ArduinoFake',deps/'SimpleArduinoFake/src',deps/'SimpleArduinoFake/src/arduino',deps/'ArduinoNativeFake/src',deps/'Unity/src']
includes += [p for library in deps.iterdir() if library.is_dir() for p in [library,library/'src',library/'include'] if p.is_dir()]
command=['c++','-std=c++14','-fshort-enums','-DUNIT_TEST','-DUSE_LIBDIVIDE','-DNATIVE_BOARD','-DEXTERNAL_BOARD_H="board_native.h"','-DARDUINO=101','-DUSBCON','-DINJ_CHANNELS=8','-DIGN_CHANNELS=8']+['-I'+str(p) for p in includes]+[str(R/'tools/speeduino_reference.cpp'),*[str(p) for p in (build/'src').rglob('*.o')],str(build/'test/fake_decoder_status.o'),*[str(p) for p in (build/'unity_config_build').rglob('*.o')]]+['-Wl,--start-group']+[str(p) for p in build.glob('**/*.a')]+['-Wl,--end-group','-lgcov','-o',str(out/'speeduino-reference')]
subprocess.run(command,check=True)
print('Built production Speeduino computePulseWidths reference at '+sha)
