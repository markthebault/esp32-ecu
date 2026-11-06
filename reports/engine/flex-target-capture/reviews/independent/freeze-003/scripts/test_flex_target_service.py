#!/usr/bin/env python3
"""Compile actual target/control services against a deterministic native API model.

No ESP-IDF or target execution, flashing, physical I/O or service restarts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def run(output):
 output=output.resolve();output.mkdir(parents=True,exist_ok=False)
 cjson=Path(os.environ.get('PLATFORMIO_CORE_DIR',Path.home()/'.platformio'))/'packages/framework-espidf/components/json/cJSON'
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
 commands=[['cc',*flags,'-c',str(cjson/'cJSON.c'),'-o',str(output/'cjson.o')],
  [os.environ.get('CXX','g++'),'-std=c++17',*flags,'-Wall','-Wextra','-Werror','-pedantic','-pthread',
   '-DECU_COMPACT_A3=1','-DECU_SELECTED_N16R8=1','-DECU_FLEX_G38_DRAFT=1',
   '-I',str(cjson),'-I',str(ROOT/'firmware/tests/target_fakes'),'-I',str(ROOT/'firmware/include'),
   str(ROOT/'firmware/tests/flex_target_service_test.cpp'),str(output/'cjson.o'),'-o',str(output/'test')]]
 results=[]
 def execute(command,name):
  with (output/(name+'.log')).open('xb') as log:
   result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  results.append(dict(name=name,command=command,returncode=result.returncode))
  (output/'commands.json').write_text(json.dumps(results,indent=2)+'\n')
  if result.returncode:raise RuntimeError(name+' failed; inspect '+str(output/(name+'.log')))
 for n,command in enumerate(commands):execute(command,'compile-'+str(n))
 for mode in range(4):
  directory=output/('fixtures-'+str(mode));directory.mkdir()
  execute([str(output/'test'),str(directory),str(mode)],'run-'+str(mode))
 summary=dict(passed=True,qualification=__doc__.strip(),test_sha256=hashlib.sha256((output/'test').read_bytes()).hexdigest(),runs=results)
 (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(dict(passed=True,output=str(output),runs=4)))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output)
