#!/usr/bin/env python3
"""Export a CVODE FMI2 air-path model using the pinned cached research library.

Run scripts/probe_engine_modelica.py first to fetch and check prerequisites.
No upstream files are changed, and the generated FMU stays in the task cache.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from verify_modelica_sources import verify

R=Path(__file__).resolve().parents[1]
IMAGE='openmodelica/openmodelica@sha256:ac9a0223e69b8055d444b42f58ccb9680342b56848c68b81385bf83d7c0ba824'
MSL='72bc91df9d48f91525651ed8d1fc7bceeec67661'
PIN='57c7aa394d70bffe6106afb2703b92bc532a05d1'
cache=R/'.cache/engine/modelica-mvem'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profiles',action='store_true',help='Build the separate parameterized1..8 cylinder adapter')
args=parser.parse_args()
name='EngineProfileAirPath' if args.profiles else 'EngineAirPath'
build=cache/('airpath-profiles' if args.profiles else 'airpath');build.mkdir(parents=True,exist_ok=True)
source=cache/'source';libraries=cache/'libraries'
metadata=json.loads((libraries/'libraries/Modelica 3.2.3+maint.om/openmodelica.metadata.json').read_text())
if metadata['sha']!=MSL:raise RuntimeError('Modelica standard library pin differs')
verified_sources=verify()
model=R/('simulation/modelica/'+name+'.mo')
script='''getVersion();
loadModel(Modelica, {"3.2.3"});
loadFile("/model/MVEMLib/package.mo");
loadFile("/adapter/EngineAirPath.mo");
getErrorString();
checkModel(EngineAirPath);
getErrorString();
setCommandLineOptions("--fmiFlags=s:cvode --fmuRuntimeDepends=modelica");
buildModelFMU(EngineAirPath, version="2.0", fmuType="cs", platforms={"static"});
getErrorString();
'''
if args.profiles:
 script=script.replace('loadFile("/adapter/EngineAirPath.mo");','loadFile("/adapter/EngineAirPath.mo");\nloadFile("/adapter/EngineProfileAirPath.mo");')
 script=script.replace('checkModel(EngineAirPath)','checkModel(EngineProfileAirPath)').replace('buildModelFMU(EngineAirPath','buildModelFMU(EngineProfileAirPath')
(build/'build.mos').write_text(script)
mounts=['--mount',f'type=bind,src={build},dst=/work',
        '--mount',f'type=bind,src={source},dst=/model,readonly',
        '--mount',f'type=bind,src={libraries},dst=/root/.openmodelica,readonly',
        '--mount',f'type=bind,src={model.parent},dst=/adapter,readonly']
try:
 with (build/'build.log').open('w') as log:
  subprocess.run(['docker','run','--rm','--cpus=2','--memory=2g','--network','none',*mounts,
                  '--workdir','/work',IMAGE,'omc','build.mos'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
finally:
 subprocess.run(['docker','run','--rm','--network','none','--mount',f'type=bind,src={build},dst=/build',IMAGE,
                 'chown','-R',f'{os.getuid()}:{os.getgid()}','/build'],check=True)
fmu=build/(name+'.fmu')
if not fmu.exists() or 'Error:' in (build/'build.log').read_text():raise RuntimeError('FMU export failed; inspect '+str(build/'build.log'))
manifest=dict(source_commit=PIN,modelica_commit=MSL,openmodelica_image=IMAGE,
              verified_sources=verified_sources,
              adapter_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
              fmu_sha256=hashlib.sha256(fmu.read_bytes()).hexdigest(),solver='CVODE',fmi='2.0 co-simulation',
              scope='NA manifold/air flow only; external free shaft and empirical pulse-driven combustion',
              documentation='https://openmodelica.org/doc/OpenModelicaUsersGuide/1.25/fmitlm.html')
if args.profiles:
 manifest.update(base_adapter_sha256=hashlib.sha256((model.parent/'EngineAirPath.mo').read_bytes()).hexdigest(),
                 model_name=name,parameters='Explicit cylinder count1..8 and total displacement25..12000cc; read back after initialization')
(build/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(fmu)
