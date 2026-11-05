"""ASan/UBSan checks of real calibration, parsing, binding and controller code."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from web_server import R


def run(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    cjson=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    commands=[['cc',*flags,'-c',str(cjson/'cJSON.c'),'-o',str(output/'cJSON.o')],
        ['g++','-std=c++17',*flags,'-Wall','-Wextra','-Werror','-pedantic','-I'+str(cjson),
         '-I'+str(R/'firmware/include'),'-I'+str(R/'firmware/main'),
         str(R/'firmware/tests/ratiometric_test.cpp'),str(output/'cJSON.o'),'-o',str(output/'test')],
        [str(output/'test'),str(R/'config/defaults.json')]]
    names=['firmware/tests/ratiometric_test.cpp','firmware/main/config_json.hpp',
        'config/defaults.json','tools/test_sensor_native.py']
    names += [str(p.relative_to(R)) for p in sorted((R/'firmware/include/ecu').glob('*.hpp'))]
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    hashes={name:digest(R/name) for name in names}
    for name in names:
        p=output/'sources'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/name).read_bytes())
    for i,command in enumerate(commands):
        with (output/f'{i}.log').open('xb') as log:subprocess.run(command,cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
    assert hashes=={name:digest(R/name) for name in names}
    (output/'result.json').write_text(json.dumps(dict(passed=True,commands=commands,snapshot_sha256=hashes,
        cjson_sha256=digest(cjson/'cJSON.c'),binary_sha256=digest(output/'test'),
        scope=__doc__,physical_qualification=False),indent=2)+'\n');print((output/'2.log').read_text())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
