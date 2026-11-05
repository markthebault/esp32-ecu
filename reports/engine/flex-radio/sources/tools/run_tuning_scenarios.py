#!/usr/bin/env python3
"""Prepare actual closed-loop benchmark tunes via shared own004 staging/burn.

This is before-start configuration validation, not a hot-tuning timing claim.
The existing independent unequal-cylinder plant and pinned Speeduino profiles
retain their distinct fuel/deadtime policies and negative mapping controls.
"""
import argparse,hashlib,json,struct,tempfile
from pathlib import Path
import run_cylinder_scenarios as cases
from engine_protocol import Session,pages
from engine_runtime import EngineStore,R
from run_target_scenarios import TargetController


def validate(output):
 attest=[];original=cases.TargetController
 class Configured(TargetController):
  def __init__(self,tune=None):
   with tempfile.TemporaryDirectory() as directory:
    store=EngineStore(Path(directory)/'tune.json');session=Session(store)
    try:
     body=pages(tune or cases.benchmark.benchmark_tune())[1]
     for offset in range(0,len(body),256):
      chunk=body[offset:offset+256]
      if session.command(b'M'+struct.pack('<BBHH',0,1,offset,len(chunk))+chunk)!=b'\0':raise RuntimeError('Whole-tune staging rejected')
     crc=session.command(b'd\0\1')
     if session.command(b'b\0\1')!=b'\4':raise RuntimeError('Whole-tune burn rejected')
     if session.command(b'd\0\1')!=crc or session.buffers[1]!=body:raise RuntimeError('Burn mutated mapped tune bytes')
     active=store.tune
     attest.append(dict(session=session.diagnostics(),mapped_sha256=hashlib.sha256(body).hexdigest(),persisted_sha256=hashlib.sha256(store.path.read_bytes()).hexdigest(),revision=active['revision']))
     super().__init__(active)
    finally:session.close()
 cases.TargetController=Configured
 try:result=cases.validate(output)
 finally:cases.TargetController=original
 library=R/'.cache/engine/tuning-native/libtuning.so'
 result['configuration_path']=dict(scope='Four project tunes staged and burned before simulation start via target-shared C++ own004 codec and host atomic file backend. Target NVS/configuration fences are separately tested with service fakes; no USB hardware or hot-running commit is modeled here.',sessions=attest,native_library_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
 for name in ['tools/run_tuning_scenarios.py','tools/tuning_runtime.py','tools/tuning_bridge.cpp','tools/engine_protocol.py']:
  result['source_hashes'][name]=hashlib.sha256((R/name).read_bytes()).hexdigest()
 (output/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/tuning-scenarios');a=p.parse_args();r=validate(a.report_dir);print(json.dumps(dict(passed=r['passed'],failures=r['failures']),indent=2));raise SystemExit(0 if r['passed'] else 1)
