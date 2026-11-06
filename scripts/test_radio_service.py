#!/usr/bin/env python3
"""Run actual radio peer-slot/handler/policy code in a native SDK API model.

Does not execute ESP-IDF/RTOS, RF, physical LED or a device. No flashing.
"""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(output):
 output=output.resolve();output.mkdir(parents=True,exist_ok=False)
 cjson=Path(os.environ.get('PLATFORMIO_CORE_DIR',Path.home()/'.platformio'))/'packages/framework-espidf/components/json/cJSON'
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
 commands=[['cc',*flags,'-c',str(cjson/'cJSON.c'),'-o',str(output/'cjson.o')],
  [os.environ.get('CXX','g++'),'-std=c++17',*flags,'-Wall','-Wextra','-Werror','-pedantic','-pthread','-DECU_COMPACT_A3=1','-DECU_SELECTED_N16R8=1','-DECU_FLEX_G38_DRAFT=1',
   '-I',str(cjson),'-I',str(ROOT/'firmware/tests/radio_fakes'),'-I',str(ROOT/'firmware/tests/target_fakes'),'-I',str(ROOT/'firmware/include'),str(ROOT/'firmware/tests/radio_service_test.cpp'),str(output/'cjson.o'),'-lcrypto','-o',str(output/'test')],
  [str(output/'test'),str(output)]]
 results=[]
 for n,command in enumerate(commands):
  with (output/(str(n)+'.log')).open('xb') as log:result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  results.append(dict(command=command,returncode=result.returncode));(output/'commands.json').write_text(json.dumps(results,indent=2)+'\n')
  if result.returncode:raise RuntimeError('Native radio check failed: '+str(output/(str(n)+'.log')))
 (output/'summary.json').write_text(json.dumps(dict(passed=True,qualification=__doc__.strip(),test_sha256=hashlib.sha256((output/'test').read_bytes()).hexdigest(),runs=results),indent=2)+'\n')
 print(json.dumps(dict(passed=True,output=str(output))))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output)
