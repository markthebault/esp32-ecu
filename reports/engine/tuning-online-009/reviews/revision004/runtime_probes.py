#!/usr/bin/env python3
"""Extra isolated probes of the unmodified frozen serial runtime/native binary."""
from pathlib import Path
import importlib.util,json,os,queue,select,struct,sys,threading,time,traceback,zlib
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('review_runtime',BASE/'fixture-root/tools/speeduino_serial_runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
results=[]
def envelope(payload):return len(payload).to_bytes(2,'big')+payload+zlib.crc32(payload).to_bytes(4,'big')
class Client:
 def __init__(self,name):
  self.q=queue.Queue();self.pending=b'';self.native=runtime.SpeeduinoSerialRuntime(self.q.put,record_dir=BASE/'sessions'/name)
 def read(self,n,timeout=2):
  until=time.monotonic()+timeout
  while len(self.pending)<n:self.pending+=self.q.get(timeout=max(.001,until-time.monotonic()))
  result,self.pending=self.pending[:n],self.pending[n:];return result
 def frame(self):
  head=self.read(2);n=int.from_bytes(head,'big');assert 0<n<1024
  data=self.read(n+4);assert zlib.crc32(data[:-4])==int.from_bytes(data[-4:],'big');return data[:-4]
 def close(self):
  self.native.close();self.native.close();assert not self.native.reader.is_alive();assert self.native.process.poll()is not None
def probe(name,fn):
 start=time.monotonic()
 try:detail=fn();results.append(dict(name=name,passed=True,detail=detail,elapsed_s=time.monotonic()-start))
 except Exception as error:results.append(dict(name=name,passed=False,error=str(error),traceback=traceback.format_exc(),elapsed_s=time.monotonic()-start))
 (BASE/'runtime-probes.json').write_text(json.dumps(results,indent=2)+'\n')
def coalesced():
 c=Client('coalesced')
 try:
  commands=[b'C',b'Q',b'f\0',b'p'+struct.pack('<BBHH',0,2,0,64),b'I']
  c.native.send(b''.join(envelope(p)for p in commands)+b'F')
  data=[c.frame()for _ in commands]
  assert data[0]==b'\0\xff'and data[1]==b'\0speeduino 202504-dev'and data[2]==b'\0\2\0y\0@'
  assert data[3]==b'\0'+b'U'*64 and data[4][:2]==b'\0\0'and len(data[4])==4
  assert c.read(3)==b'002';c.native.request_stats();time.sleep(.03)
  assert c.native.stats['received']==sum(len(envelope(p))for p in commands)+1
  assert c.q.empty()and not c.pending and not c.native.failure
  return dict(stats=c.native.stats,reply_lengths=list(map(len,data)),raw_F_inherited_print=True,no_TX_echo=True)
 finally:c.close()
def splits():
 wire=envelope(b'M'+struct.pack('<BBHH',0,2,0,1)+b'V')
 for cut in range(1,len(wire)):
  c=Client('split-'+str(cut))
  try:
   c.native.send(wire[:cut]);time.sleep(.02);c.native.send(wire[cut:]);assert c.frame()==b'\0'
   c.native.send(envelope(b'p'+struct.pack('<BBHH',0,2,0,1)));assert c.frame()==b'\0V';assert not c.native.failure
  finally:c.close()
 return dict(split_boundaries=len(wire)-1,gap_s=.02)
def partial_close():
 c=Client('partial-close');c.native.send(b'\0');time.sleep(.04);start=time.monotonic();c.close();elapsed=time.monotonic()-start
 assert elapsed<1.5 and c.native.process.returncode==0 and not c.native.failure
 return dict(close_elapsed_s=elapsed,returncode=c.native.process.returncode)
def overflow():
 c=Client('rx-capacity')
 try:
  c.native.send(b'F'*16384);c.native.send(b'F'*16384)
  until=time.monotonic()+3
  while not c.native.failure and time.monotonic()<until:time.sleep(.01)
  assert c.native.failure
 finally:c.close()
 stderr=(c.native.record_dir/'native-stderr.log').read_text()
 assert 'serial fixture RX capacity'in stderr and c.native.process.returncode==1
 return dict(controlled_rejection=True,returncode=1,failure=c.native.failure,stderr=stderr)
def callback_failure():
 def reject(_):raise RuntimeError('owned callback rejection')
 n=runtime.SpeeduinoSerialRuntime(reject,record_dir=BASE/'sessions/callback-failure')
 try:
  n.send(b'F');until=time.monotonic()+2
  while not n.failure and time.monotonic()<until:time.sleep(.01)
  assert n.failure=='owned callback rejection'
 finally:n.close()
 assert not n.reader.is_alive()and n.process.poll()is not None
 return dict(failure=n.failure,returncode=n.process.returncode,reader_joined=True)
def pty_churn():
 link=BASE/'pty-churn'
 with runtime.SpeeduinoPtyEndpoint(link,record_dir=BASE/'sessions/pty-churn')as endpoint:
  for _ in range(50):
   fd=os.open(link,os.O_RDWR|os.O_NOCTTY)
   try:
    os.write(fd,b'F');assert select.select([fd],[],[],2)[0];assert os.read(fd,3)==b'002'
   finally:os.close(fd)
  assert not endpoint.failure and not endpoint.runtime.failure
 assert not link.exists()and not link.is_symlink()and endpoint.runtime.process.returncode==0
 assert not endpoint.thread.is_alive()and not endpoint.runtime.reader.is_alive()
 return dict(cycles=50,process_returncode=0,reader_threads_joined=True,owned_link_removed=True)
for name,fn in [('coalesced-fifo-and-no-echo',coalesced),('all-single-byte-M-splits',splits),('close-during-partial-length',partial_close),('rx-capacity-controlled-failure',overflow),('callback-failure-cleanup',callback_failure),('pty-open-close-churn',pty_churn)]:probe(name,fn)
print(json.dumps(results,indent=2));sys.exit(not all(r['passed']for r in results))
