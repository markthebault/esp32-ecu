from pathlib import Path
import hashlib,json,os,select,shutil,subprocess,sys
from PIL import ImageGrab
ROOT=Path('/home/mark/persospace/esp32-ecu');sys.path.insert(0,str(ROOT/'tools'))
from speeduino_serial_runtime import SpeeduinoPtyEndpoint
task=ROOT/'.cache/engine/tuning-online-009/reference-public-003';task.mkdir(parents=True,exist_ok=False)
app=task/'app';shutil.copytree('/home/mark/.local/opt/efi-analytics/TunerStudioMS-3.3.01/TunerStudioMS',app)
project=task/'SPEEDUINO-PRODUCTION';cfg=project/'projectCfg';cfg.mkdir(parents=True)
shutil.copyfile(ROOT.parent/'speeduino/reference/speeduino.ini',cfg/'mainController.ini')
link=task/'tuner-serial';seed=ROOT/'.cache/engine/tuning-online-009/own009/ESP32ECU-ONLINE-009/projectCfg/project.properties';lines=[]
for line in seed.read_text().splitlines():
 if 'Com\\ Port='in line or line.startswith('commPort='):line=line.split('=',1)[0]+'='+str(link)
 if line.startswith('projectName='):line='projectName=SPEEDUINO-PRODUCTION'
 if line.startswith('tuneFileDir='):line='tuneFileDir='+str(task)
 if line.startswith(('dashBoardFile=','lastDisplayedTuneFile=')):continue
 lines.append(line)
(cfg/'project.properties').write_text('\n'.join(lines)+'\n');home=task/'user';home.mkdir();wire=(task/'wire.log').open('w');used=0
def observe(direction,body):
 global used
 line=direction+' '+str(len(body))+' '+body.hex()+'\n';used+=len(line)
 if used>4194304:raise RuntimeError('Owned wire capture bound reached')
 wire.write(line);wire.flush()
display=None;java=None
try:
 with SpeeduinoPtyEndpoint(link,observe,task/'native')as endpoint:
  read,write=os.pipe();display=subprocess.Popen(['Xvfb','-displayfd',str(write),'-screen','0','1440x1000x24','-nolisten','tcp'],pass_fds=[write],stdout=subprocess.DEVNULL,stderr=(task/'xvfb.log').open('w'));os.close(write)
  if not select.select([read],[],[],5)[0]:raise RuntimeError('Private display failed')
  number=os.read(read,64).decode().strip();os.close(read);env=dict(os.environ,DISPLAY=':'+number)
  java=subprocess.Popen(['java','-Duser.home='+str(home),'-Djava.awt.headless=false','-Djava.library.path=lib/alternateLinuxDrivers/x86_64-linux:lib','-jar','TunerStudioMS.jar',str(project)],cwd=app,env=env,stdout=(task/'application.log').open('w'),stderr=subprocess.STDOUT)
  metadata=dict(display=env['DISPLAY'],java_pid=java.pid,xvfb_pid=display.pid,native_pid=endpoint.runtime.process.pid,project=str(project),pty=str(link),application_sha256=hashlib.sha256((app/'TunerStudioMS.jar').read_bytes()).hexdigest(),ini_sha256=hashlib.sha256((cfg/'mainController.ini').read_bytes()).hexdigest(),sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in('tools/speeduino_serial_sim.cpp','tools/speeduino_serial_runtime.py','scripts/build_speeduino_serial.py')})
  (task/'session.json').write_text(json.dumps(metadata,indent=2)+'\n');(task/'native-build-manifest.json').write_text(json.dumps(endpoint.runtime.manifest,indent=2)+'\n');print(json.dumps(metadata),flush=True)
  for command in sys.stdin:
   if command.strip()=='quit':break
   if command.strip()=='snap':ImageGrab.grab(xdisplay=env['DISPLAY']).save(task/'screen.png');print('Captured public reference display',flush=True)
   if command.strip()=='stats':endpoint.runtime.request_stats();print('bridge_failure',endpoint.failure,endpoint.runtime.failure,flush=True)
   if command.strip()=='windows':
    ids=subprocess.run(['xdotool','search','--onlyvisible','--name','.'],env=env,capture_output=True,text=True)
    for window in ids.stdout.split():print(window,subprocess.run(['xdotool','getwindowname',window],env=env,capture_output=True,text=True).stdout.strip(),flush=True)
  if java.poll()is None:java.terminate();java.wait(timeout=5)
finally:
 for process in(java,display):
  if process and process.poll()is None:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
 wire.close()
