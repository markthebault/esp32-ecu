from pathlib import Path
import hashlib,json,os,select,shutil,subprocess,sys
from PIL import ImageGrab
ROOT=Path('/home/mark/persospace/esp32-ecu');sys.path.insert(0,str(ROOT/'tools'))
from engine_runtime import EngineStore
from engine_msq import export_msq
from tuning_server import PtyEndpoint
task=ROOT/'.cache/engine/tuning-online-009/own009';task.mkdir(parents=True,exist_ok=False)
app=task/'app';original=Path('/home/mark/.local/opt/efi-analytics/TunerStudioMS-3.3.01/TunerStudioMS');shutil.copytree(original,app)
seeds=sorted((ROOT/'.cache/engine/secondary-integration').glob('ts-accepted/ESP32ECU*/projectCfg/project.properties'));assert len(seeds)==1,seeds
project=task/'ESP32ECU-ONLINE-009';shutil.copytree(seeds[0].parents[1],project)
shutil.copyfile(ROOT/'tuning/esp32-ecu-secondary.ini',project/'projectCfg/mainController.ini')
store=EngineStore(task/'engine.json');(project/'CurrentTune.msq').write_text(export_msq(store.tune))
link=task/'tuner-serial';properties=project/'projectCfg/project.properties';lines=[]
for line in properties.read_text().splitlines():
 if 'Com\\ Port='in line or line.startswith('commPort='):line=line.split('=',1)[0]+'='+str(link)
 if line.startswith('projectName='):line='projectName=ESP32ECU-ONLINE-009'
 if line.startswith('lastDisplayedTuneFile='):line='lastDisplayedTuneFile=CurrentTune.msq'
 if line.startswith('tuneFileDir='):line='tuneFileDir='+str(task)
 lines.append(line)
properties.write_text('\n'.join(lines)+'\n');home=task/'user';home.mkdir();wire=(task/'wire.log').open('w');original_stdout=sys.stdout
class Trace:
 def __init__(self):self.pending='';self.used=0
 def write(self,value):
  self.pending+=value
  while '\n'in self.pending:
   line,self.pending=self.pending.split('\n',1)
   if self.used+len(line)<524288:wire.write(line+'\n');wire.flush();self.used+=len(line)+1
   if not line.startswith(('RX ','TX ')):original_stdout.write(line+'\n');original_stdout.flush()
 def flush(self):wire.flush()
sys.stdout=Trace();read,write=os.pipe();display=None;java=None
try:
 with PtyEndpoint(store,link,True):
  display=subprocess.Popen(['Xvfb','-displayfd',str(write),'-screen','0','1440x1000x24','-nolisten','tcp'],pass_fds=[write],stdout=subprocess.DEVNULL,stderr=(task/'xvfb.log').open('w'));os.close(write)
  if not select.select([read],[],[],5)[0]:raise RuntimeError('Own display failed')
  number=os.read(read,64).decode().strip();os.close(read);env=dict(os.environ,DISPLAY=':'+number)
  java=subprocess.Popen(['java','-Duser.home='+str(home),'-Djava.awt.headless=false','-Djava.library.path=lib/alternateLinuxDrivers/x86_64-linux:lib','-jar','TunerStudioMS.jar',str(project)],cwd=app,env=env,stdout=(task/'application.log').open('w'),stderr=subprocess.STDOUT)
  metadata=dict(display=env['DISPLAY'],java_pid=java.pid,xvfb_pid=display.pid,project=str(project),pty=str(link),application_sha256=hashlib.sha256((app/'TunerStudioMS.jar').read_bytes()).hexdigest(),ini_sha256=hashlib.sha256((project/'projectCfg/mainController.ini').read_bytes()).hexdigest())
  (task/'session.json').write_text(json.dumps(metadata,indent=2)+'\n');print('OWN_SESSION',json.dumps(metadata),flush=True)
  for command in sys.stdin:
   if command.strip()=='quit':break
   if command.strip()=='snap':ImageGrab.grab(xdisplay=env['DISPLAY']).save(task/'screen.png');print('Captured own display',flush=True)
   if command.strip()=='state':print('STORE',json.dumps(store.timing_status()),flush=True)
   if command.strip()=='windows':
    ids=subprocess.run(['xdotool','search','--onlyvisible','--name','.'],env=env,capture_output=True,text=True)
    for window in ids.stdout.split():print(window,subprocess.run(['xdotool','getwindowname',window],env=env,capture_output=True,text=True).stdout.strip(),flush=True)
finally:
 for process in(java,display):
  if process and process.poll()is None:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
 store.runtime.close();store.data_recorder.close();wire.close();sys.stdout=original_stdout
