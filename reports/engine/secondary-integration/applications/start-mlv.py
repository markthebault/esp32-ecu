from pathlib import Path
import os,select,shutil,subprocess,sys,json
from PIL import ImageGrab
root=Path('/home/mark/persospace/esp32-ecu');task=root/'.cache/engine/secondary-integration/mlv';task.mkdir(parents=True,exist_ok=True)
original=Path('/home/mark/.local/opt/efi-analytics/MegaLogViewerHD-4.6.14/MegaLogViewerHD')
app=task/'app'
if not app.exists():shutil.copytree(original,app)
home=task/'user';home.mkdir(exist_ok=True)
read,write=os.pipe();display=None;java=None
try:
 display=subprocess.Popen(['Xvfb','-displayfd',str(write),'-screen','0','1440x1000x24','-nolisten','tcp'],pass_fds=[write],stdout=subprocess.DEVNULL,stderr=(task/'xvfb.log').open('w'))
 os.close(write)
 if not select.select([read],[],[],5)[0]:raise RuntimeError('Own Xvfb did not report display')
 number=os.read(read,64).decode().strip();os.close(read);env=dict(os.environ,DISPLAY=':'+number)
 java=subprocess.Popen(['java','-Duser.home='+str(home),'-Djava.awt.headless=false','-jar','HogLogViewer.jar',str(root/'.cache/engine/secondary-integration/ui/browser006.msl')],cwd=app,env=env,stdout=(task/'application.log').open('w'),stderr=subprocess.STDOUT)
 (task/'session.json').write_text(json.dumps(dict(display=env['DISPLAY'],java_pid=java.pid,xvfb_pid=display.pid)))
 print(json.dumps(dict(display=env['DISPLAY'],java_pid=java.pid,xvfb_pid=display.pid)),flush=True)
 for command in sys.stdin:
  if command.strip()=='quit':break
  if command.strip()=='snap':
   if java.poll() is not None:raise RuntimeError('Application exited '+str(java.returncode))
   ImageGrab.grab(xdisplay=env['DISPLAY']).save(task/'screen.png');print('Captured own Xvfb screen',flush=True)
  if command.strip()=='windows':
   ids=subprocess.run(['xdotool','search','--onlyvisible','--name','.'],env=env,capture_output=True,text=True)
   for window in ids.stdout.split():
    title=subprocess.run(['xdotool','getwindowname',window],env=env,capture_output=True,text=True).stdout.strip();print(window,title,flush=True)
finally:
 for process in (java,display):
  if process and process.poll() is None:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
