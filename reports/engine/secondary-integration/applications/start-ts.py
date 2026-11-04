from pathlib import Path
import os,select,shutil,subprocess,sys,json
from PIL import ImageGrab
root=Path('/home/mark/persospace/esp32-ecu');task=root/'.cache/engine/secondary-integration/ts';task.mkdir(parents=True,exist_ok=True)
original=Path('/home/mark/.local/opt/efi-analytics/TunerStudioMS-3.3.01/TunerStudioMS');app=task/'app'
if not app.exists():shutil.copytree(original,app)
home=task/'user';home.mkdir(exist_ok=True)
project=task/'ESP32ECU-SECONDARY-009'
if not project.exists():
 shutil.copytree('/home/mark/TunerStudioProjects/ESP32ECU-SIL-20261103',project)
 shutil.copyfile(root/'tuning/esp32-ecu-secondary.ini',project/'projectCfg/mainController.ini')
 sys.path.insert(0,str(root/'tools'))
 from engine_msq import export_msq
 from run_load_scenarios import configuration
 tune=json.loads((root/'.cache/engine/secondary-integration/application-tune.json').read_text())
 (project/'CurrentTune.msq').write_text(export_msq(tune))
 p=project/'projectCfg/project.properties';s=p.read_text().replace('ESP32ECU-SIL-20261103','ESP32ECU-SECONDARY-009').replace('lastDisplayedTuneFile=ts-offline-base-v2.msq','lastDisplayedTuneFile=CurrentTune.msq');s=s.replace('/home/mark/persospace/esp32-ecu/.cache/engine/tuner-serial','/tmp/ecu-secondary-offline-no-device').replace('commPort=COM1','commPort=/tmp/ecu-secondary-offline-no-device').replace('lastDisplayedTuneFile=CurrentTune.msq','lastDisplayedTuneFile=CurrentTune.msq');p.write_text(s)
read,write=os.pipe();display=None;java=None
try:
 display=subprocess.Popen(['Xvfb','-displayfd',str(write),'-screen','0','1440x1000x24','-nolisten','tcp'],pass_fds=[write],stdout=subprocess.DEVNULL,stderr=(task/'xvfb.log').open('w'));os.close(write)
 if not select.select([read],[],[],5)[0]:raise RuntimeError('Own Xvfb did not report display')
 number=os.read(read,64).decode().strip();os.close(read);env=dict(os.environ,DISPLAY=':'+number)
 java=subprocess.Popen(['java','-Duser.home='+str(home),'-Djava.awt.headless=false','-Djava.library.path=lib/alternateLinuxDrivers/x86_64-linux:lib','-jar','TunerStudioMS.jar',str(project)],cwd=app,env=env,stdout=(task/'application.log').open('w'),stderr=subprocess.STDOUT)
 (task/'session.json').write_text(json.dumps(dict(display=env['DISPLAY'],java_pid=java.pid,xvfb_pid=display.pid)))
 print(json.dumps(dict(display=env['DISPLAY'],java_pid=java.pid,xvfb_pid=display.pid)),flush=True)
 for command in sys.stdin:
  if command.strip()=='quit':break
  if command.strip()=='snap':ImageGrab.grab(xdisplay=env['DISPLAY']).save(task/'screen.png');print('Captured own test display',flush=True)
  if command.strip()=='windows':
   ids=subprocess.run(['xdotool','search','--onlyvisible','--name','.'],env=env,capture_output=True,text=True)
   for window in ids.stdout.split():print(window,subprocess.run(['xdotool','getwindowname',window],env=env,capture_output=True,text=True).stdout.strip(),flush=True)
finally:
 for process in (java,display):
  if process and process.poll() is None:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
