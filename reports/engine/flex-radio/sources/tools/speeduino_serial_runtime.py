"""Raw serial bridge to actual pinned Speeduino in a stopped native fixture.

This never supplies ECU protocol replies. Every received byte is queued to the
production parser; every transmitted byte comes from production Serial/Print.
No physical serial/GPIO device or numerical engine plant is attached.
"""
from contextlib import AbstractContextManager
import errno,hashlib,json,os,pty,select,subprocess,threading,time,tty,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SpeeduinoSerialRuntime(AbstractContextManager):
 def __init__(self,on_bytes,on_wire=None,record_dir=None):
  self.on_bytes=on_bytes;self.on_wire=on_wire or(lambda direction,body:None);self.failure='';self.closing=False;self.write_lock=threading.Lock();self.wire_lock=threading.Lock();self.ready=threading.Event();self.stats={}
  cache=ROOT/'.cache/engine/speeduino-serial-sim';manifest=cache/'build-manifest.json';binary=cache/'speeduino-serial-sim'
  if not manifest.exists():raise RuntimeError('Build scripts/build_speeduino_serial.py first')
  self.manifest=json.loads(manifest.read_text())
  if self.manifest['unit_test']or self.manifest['scope']!='stopped_engine_serial_positive_control'or self.manifest['speeduino_sha']!='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'or self.manifest.get('numerical_relink_sha256')!=self.manifest['base_binary_sha256']or hashlib.sha256(binary.read_bytes()).hexdigest()!=self.manifest['binary_sha256']:raise RuntimeError('Serial reference executable attestation failed')
  for name,digest in self.manifest['fixture_sources'].items():
   if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Rebuild serial reference after fixture source changes')
  self.record_dir=Path(record_dir)if record_dir else cache/'sessions'/str(uuid.uuid4());self.record_dir.mkdir(parents=True,exist_ok=False)
  self.stderr=(self.record_dir/'native-stderr.log').open('wb');self.events=(self.record_dir/'native-events.log').open('w');self.event_bytes=0
  try:self.process=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,bufsize=0)
  except BaseException:self.events.close();self.stderr.close();raise
  os.set_blocking(self.process.stdin.fileno(),False)
  self.reader=threading.Thread(target=self._read,daemon=True,name='Production Speeduino serial TX');self.reader.start()
  if not self.ready.wait(5):
   self.close();raise RuntimeError('Native reference startup timed out: '+self.failure)
  if self.failure:
   self.close();raise RuntimeError(self.failure)
 def _read(self):
  try:
   while True:
    line=self.process.stdout.readline(65536)
    if not line:
     if not self.closing:raise RuntimeError('Native reference ended before closure')
     break
    if not line.endswith(b'\n'):raise RuntimeError('Oversized native reference event')
    self.event_bytes+=len(line)
    if self.event_bytes>16777216:raise RuntimeError('Owned native event capture limit reached')
    text=line.decode().rstrip('\n');self.events.write(text+'\n');self.events.flush()
    if text.startswith('ready '):self.ready.set()
    elif text.startswith('tx '):
     fields=text.split();body=bytes.fromhex(fields[2]);self._wire('TX',body);self.on_bytes(body)
    elif text.startswith('stats '):
     values=list(map(int,text.split()[1:]));self.stats=dict(zip(('loops','received','transmitted'),values))
    elif text.startswith('error '):raise RuntimeError(text)
    else:raise RuntimeError('Unknown native reference event')
  except Exception as error:
   if not self.closing:self.failure=str(error)
   self.ready.set()
   if not self.closing and self.process.poll()is None:self.process.terminate()
 def _command(self,line,rx_body=None):
  deadline=time.monotonic()+2
  with self.write_lock:
   if rx_body is not None:self._wire('RX',rx_body)
   while line:
    if not select.select([],[self.process.stdin],[],max(0,deadline-time.monotonic()))[1]:raise TimeoutError('Native reference did not drain injection pipe')
    try:count=os.write(self.process.stdin.fileno(),line)
    except BlockingIOError:continue
    if count<=0:raise BrokenPipeError('Native reference injection pipe closed')
    line=line[count:]
 def _wire(self,direction,body):
  with self.wire_lock:self.on_wire(direction,body)
 def send(self,body):
  if not isinstance(body,bytes)or not 0<len(body)<=16384:raise ValueError('One nonempty bounded raw serial byte slice required')
  if self.failure or self.closing:raise RuntimeError(self.failure or'Native reference is closing')
  self._command(b'rx '+body.hex().encode()+b'\n',body)
 def request_stats(self):
  if self.failure or self.closing:raise RuntimeError(self.failure or'Native reference is closing')
  self._command(b'stats\n')
 def close(self):
  if self.closing:return
  self.closing=True
  if self.process.poll()is None:
   try:
    self._command(b'quit\n');self.process.stdin.close()
   except(BrokenPipeError,OSError):pass
   try:self.process.wait(timeout=3)
   except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
  if not self.process.stdin.closed:self.process.stdin.close()
  self.reader.join(timeout=3);self.process.stdout.close();self.events.close();self.stderr.close()
  (self.record_dir/'closure.json').write_text(json.dumps(dict(returncode=self.process.returncode,failure=self.failure,stats=self.stats,physical_interface=False),indent=2)+'\n')
 def __exit__(self,*args):self.close()

class SpeeduinoPtyEndpoint(AbstractContextManager):
 def __init__(self,path,on_wire=None,record_dir=None):
  self.link=Path(path).absolute()
  if self.link.exists()or self.link.is_symlink():raise ValueError('PTY link exists; choose a fresh owned path')
  self.master,slave=pty.openpty();tty.setraw(slave);self.slave_name=os.ttyname(slave);os.close(slave);os.set_blocking(self.master,False);self.stop=threading.Event();self.failure='';self.closed=False
  try:
   self.link.parent.mkdir(parents=True,exist_ok=True);self.link.symlink_to(self.slave_name)
   self.runtime=SpeeduinoSerialRuntime(self._write,on_wire,record_dir)
  except BaseException:
   os.close(self.master)
   if self.link.is_symlink()and os.readlink(self.link)==self.slave_name:self.link.unlink()
   raise
  self.thread=threading.Thread(target=self._serve,daemon=True,name='Production Speeduino PTY RX');self.thread.start()
 def _write(self,body):
  deadline=time.monotonic()+2
  while body:
   if not select.select([],[self.master],[],max(0,deadline-time.monotonic()))[1]:raise TimeoutError('Application did not drain reference reply')
   try:body=body[os.write(self.master,body):]
   except BlockingIOError:continue
 def _serve(self):
  try:
   while not self.stop.is_set():
    if self.runtime.failure:raise RuntimeError(self.runtime.failure)
    if not select.select([self.master],[],[],.02)[0]:continue
    try:body=os.read(self.master,4096)
    except BlockingIOError:continue
    except OSError as error:
     if error.errno==errno.EIO:self.stop.wait(.02);continue
     raise
    if body:self.runtime.send(body)
  except Exception as error:self.failure=str(error)
 def close(self):
  if self.closed:return
  self.closed=True
  self.stop.set();self.thread.join(timeout=3);self.runtime.close();os.close(self.master)
  if self.link.is_symlink()and os.readlink(self.link)==self.slave_name:self.link.unlink()
 def __exit__(self,*args):self.close()
