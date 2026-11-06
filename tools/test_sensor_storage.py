"""Exercise the actual sensor storage helper/parser with a native NVS API model."""
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
         '-I'+str(R/'firmware/tests/fakes'),'-I'+str(R/'firmware/include'),'-I'+str(R/'firmware/main'),
         str(R/'tools/sensor_storage_test.cpp'),str(output/'cJSON.o'),'-o',str(output/'test')],
        [str(output/'test'),str(R/'tools/fixtures/sensor-profile1-nvs-boundary.json')]]
    names=['firmware/include/ecu/config_storage.hpp','firmware/include/ecu/config.hpp','firmware/include/ecu/json.hpp',
        'firmware/main/config_json.hpp','firmware/main/web_config.cpp','tools/sensor_storage_test.cpp',
        'tools/test_sensor_storage.py','tools/fixtures/sensor-profile1-nvs-boundary.json','firmware/tests/fakes/nvs.h']
    hashes={name:hashlib.sha256((R/name).read_bytes()).hexdigest() for name in names}
    for name in names:
        p=output/'sources'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/name).read_bytes())
    for i,command in enumerate(commands):
        with (output/f'{i}.log').open('xb') as log:subprocess.run(command,cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
    assert hashes=={name:hashlib.sha256((R/name).read_bytes()).hexdigest() for name in names}
    (output/'result.json').write_text(json.dumps(dict(passed=True,commands=commands,source_sha256=hashes,
        scope=__doc__,physical_flash_qualification=False),indent=2)+'\n');print((output/'2.log').read_text())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
