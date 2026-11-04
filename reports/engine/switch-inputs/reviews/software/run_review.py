#!/usr/bin/env python3
"""Independent review replay; --freeze binds current scope before replay.

This compiles immutable copies of project software against digital fixtures.
It cannot establish peripheral, circuit, physical or automotive qualification.
"""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def bind():
    paths=list((ROOT/'firmware/include/ecu').glob('*.hpp'))
    paths += [ROOT/p for p in [
        'firmware/main/app.cpp','firmware/main/engine_service.cpp','firmware/main/switch_service.cpp',
        'firmware/main/CMakeLists.txt','firmware/main/web_assets.hpp','firmware/platformio.ini',
        'firmware/tests/switch_acquisition_test.cpp','firmware/tests/switch_transport_test.cpp','firmware/tests/switch_service_test.cpp',
        'scripts/test_firmware.sh','scripts/generate_secondary_ui.py','web/secondary_tables.js','web/secondary_tables_logic.js',
        'tools/engine_runtime.py','tools/secondary_config.py','config/engine/defaults.json','docs/engine-secondary-tables.md','docs/engine-usb-tuning.md']]
    paths+=list((ROOT/'firmware/tests/switch_fakes').rglob('*.h'))
    records=[]
    for src in sorted(set(paths)):
        rel=src.relative_to(ROOT);dst=BASE/'sources'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        records.append(dict(path=str(rel),bytes=src.stat().st_size,sha256=digest(src)))
    sdk=Path.home()/'.platformio/packages/framework-espidf/components'
    externals=[]
    for src in [sdk/'json/cJSON/cJSON.c',sdk/'json/cJSON/cJSON.h',sdk/'esp_driver_i2c/i2c_master.c',sdk/'esp_driver_i2c/include/driver/i2c_master.h']:
        rel=src.relative_to(sdk);dst=BASE/'external'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        externals.append(dict(sdk_path=str(src),path=str(Path('external')/rel),bytes=src.stat().st_size,sha256=digest(src)))
    doc=dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),scope='Protected switch software integration review only',sources=records,external_sources=externals)
    (BASE/'source-bindings.json').write_text(json.dumps(doc,indent=2)+'\n')
def command(argv):
    p=subprocess.run([str(x) for x in argv],cwd=BASE,text=True,capture_output=True)
    row=dict(argv=[str(x) for x in argv],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
    commands.append(row)
    if p.returncode:
        (BASE/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        raise RuntimeError(json.dumps(row))
    return p.stdout
ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');args=ap.parse_args()
if args.freeze:bind()
bindings=json.loads((BASE/'source-bindings.json').read_text())
for row in bindings['sources']:
    assert digest(BASE/'sources'/row['path'])==row['sha256'],row['path']
for row in bindings['external_sources']:
    assert digest(BASE/row['path'])==row['sha256'],row['path']
commands=[]
sources=BASE/'sources';inc=sources/'firmware/include';fakes=sources/'firmware/tests/switch_fakes';cjson=BASE/'external/json/cJSON'
flags=['-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer']
command(['cc','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-c',cjson/'cJSON.c','-o',BASE/'review-cjson.o'])
command(['g++',*flags,'-I'+str(inc),BASE/'adversarial_probe.cpp','-o',BASE/'review-adversarial'])
portable=json.loads(command([BASE/'review-adversarial']))
command(['g++',*flags,'-I'+str(fakes),'-I'+str(inc),'-I'+str(cjson),BASE/'service_probe.cpp',sources/'firmware/main/switch_service.cpp',BASE/'review-cjson.o','-o',BASE/'review-service'])
rows=[]
for argv in [[],['race'],['fatal']]+[['omit',str(i)] for i in range(12)]:
    row=json.loads(command([BASE/'review-service',*argv]));row['args']=argv;rows.append(row)
service=dict(passed=True,scenarios=len(rows),assertions=sum(r['assertions'] for r in rows),results=rows)
command(['g++',*flags,'-I'+str(BASE/'integration-fakes'),'-I'+str(fakes),'-I'+str(inc),'-I'+str(cjson),BASE/'engine_integration_probe.cpp',sources/'firmware/main/switch_service.cpp',sources/'firmware/main/engine_service.cpp',BASE/'review-cjson.o','-o',BASE/'review-integration'])
integration=json.loads(command([BASE/'review-integration']))
ui=json.loads(command(['node',BASE/'ui_probe.cjs']))
for name,row in [('probe-result.json',portable),('service-probe-result.json',service),('engine-integration-result.json',integration),('ui-probe-result.json',ui)]:
    (BASE/name).write_text(json.dumps(row,indent=2)+'\n')
result=dict(passed=True,portable_assertions=portable['assertions'],actual_service_assertions=service['assertions'],actual_engine_integration_assertions=integration['assertions'],native_assertions=portable['assertions']+service['assertions']+integration['assertions'],ui_assertions=ui['ui_assertions'],assertions=portable['assertions']+service['assertions']+integration['assertions']+ui['ui_assertions'],physical_qualification=False)
(BASE/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
(BASE/'replay-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
