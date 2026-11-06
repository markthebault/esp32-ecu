#!/usr/bin/env python3
"""Run upstream MVEM examples in pinned OpenModelica, without an ECU adapter.

Uses the already running Docker daemon. Never starts/restarts a host service.
The research library is external GPL source, cached without modification.
"""
import csv
import io
import json
import math
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

R=Path(__file__).resolve().parents[1]
PIN='57c7aa394d70bffe6106afb2703b92bc532a05d1'
MSL='72bc91df9d48f91525651ed8d1fc7bceeec67661'
IMAGE='openmodelica/openmodelica@sha256:ac9a0223e69b8055d444b42f58ccb9680342b56848c68b81385bf83d7c0ba824'
cache=R/'.cache/engine/modelica-mvem';cache.mkdir(parents=True,exist_ok=True)
source=cache/'source';build=cache/'build';libraries=cache/'libraries'
build.mkdir(exist_ok=True);libraries.mkdir(exist_ok=True)
if not source.exists():
 data=urllib.request.urlopen('https://api.github.com/repos/modelica-3rdparty/Modelica-MVEM/tarball/'+PIN,timeout=60).read()
 with tarfile.open(fileobj=io.BytesIO(data)) as archive:
  root=archive.getnames()[0].split('/')[0];archive.extractall(cache,filter='data')
 (cache/root).rename(source)
subprocess.run(['docker','image','inspect',IMAGE],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
mounts=['--mount',f'type=bind,src={build},dst=/work','--mount',f'type=bind,src={source},dst=/model,readonly','--mount',f'type=bind,src={libraries},dst=/root/.openmodelica']
docker=['docker','run','--rm','--cpus=2','--memory=2g',*mounts,'--workdir','/work']
bootstrap='''getVersion();
updatePackageIndex();
installPackage(Modelica, "3.2.3", exactMatch=true);
getErrorString();
'''
if not (libraries/'libraries/Modelica 3.2.3+maint.om/openmodelica.metadata.json').exists():
 (build/'bootstrap.mos').write_text(bootstrap)
 with (cache/'bootstrap.log').open('w') as log:subprocess.run([*docker,IMAGE,'omc','bootstrap.mos'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
 # Restrict ownership repair to this script's cache, not host user directories.
 subprocess.run(['docker','run','--rm','--network','none','--mount',f'type=bind,src={libraries},dst=/libraries',IMAGE,'chown','-R',f'{os.getuid()}:{os.getgid()}','/libraries'],check=True)
metadata=json.loads((libraries/'libraries/Modelica 3.2.3+maint.om/openmodelica.metadata.json').read_text())
if metadata['sha']!=MSL:raise RuntimeError('Modelica library SHA differs from audited reference')
jobs=[('si1500','SIEngineTest',15,''),('si2500','SIEngineTest',15,'-override=EngineSpeed.k=2500'),('energy','energyPreservationTest',2,''),('throttle','throttleSanityCheck',2,'')]
script='getVersion();\nloadModel(Modelica, {"3.2.3"});\nloadFile("/model/MVEMLib/package.mo");\ngetErrorString();\n'
for prefix,model,stop,flags in jobs:
 script+=f'checkModel(MVEMLib.Examples.{model});\ngetErrorString();\nsimulate(MVEMLib.Examples.{model}, stopTime={stop}, tolerance=1e-7, numberOfIntervals={stop*100}, outputFormat="csv", fileNamePrefix="{prefix}", simflags="{flags}");\ngetErrorString();\n'
(build/'examples.mos').write_text(script)
try:
 with (cache/'examples.log').open('w') as log:subprocess.run([*docker,'--network','none',IMAGE,'omc','examples.mos'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
finally:
 subprocess.run(['docker','run','--rm','--network','none','--mount',f'type=bind,src={build},dst=/build',IMAGE,'chown','-R',f'{os.getuid()}:{os.getgid()}','/build'],check=True)
rows=[]
for prefix,model,stop,flags in jobs:
 path=build/f'{prefix}_res.csv'
 if not path.exists():raise RuntimeError('Upstream example failed; inspect '+str(cache/'examples.log'))
 with path.open() as f:data=list(csv.DictReader(f))
 if not data or abs(float(data[-1]['time'])-stop)>1e-6:raise RuntimeError('Incomplete upstream simulation')
 result=dict(example=model,case=prefix,stop_s=stop,samples=len(data),completed=True)
 if model=='SIEngineTest':
  key='sIEngine.speedSensor.w';rpm=[float(p[key])*30/math.pi for p in data]
  result.update(forced_rpm=2500 if prefix=='si2500' else 1500,min_rpm=min(rpm),max_rpm=max(rpm),final_manifold_kpa=float(data[-1]['sIEngine.intakeManifold.gas.p'])/1000)
 if prefix=='energy':
  for key in ('totalMass','totalEnergy'):
   values=[float(p[key]) for p in data];result[key+'_relative_span']=(max(values)-min(values))/abs(values[0])
 rows.append(result)
log=(cache/'examples.log').read_text()
report=dict(scope='Unmodified upstream research-model feasibility and conservation examples only. Fuel internally commanded; engine speed forced. Neither our ECU nor Speeduino controls these runs.',source='https://github.com/modelica-3rdparty/Modelica-MVEM',source_commit=PIN,openmodelica_image=IMAGE,modelica_library_commit=MSL,license_note='Repository root LICENSE says GPL-2.0; Modelica source headers say GPL-3.0-or-later. Do not redistribute derived source without resolving this upstream inconsistency.',completed_with_warnings=True,log_warning_count=log.count('Warning:'),numerical_assertion_messages=log.count('assertion has been violated'),limitations=['Stock SIEngine computes fuel from air flow and has no ignition-angle/pulse interface.','Needs a reviewed actuation/FMI adapter before ECU closed-loop comparisons.','Initialization, unit annotations and small negative species-mass assertions need investigation.','No calibration for the intended engine, no hardware timing or physical qualification.'],rows=rows)
out=R/'reports/engine/modelica-feasibility.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
