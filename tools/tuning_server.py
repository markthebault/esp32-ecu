#!/usr/bin/env python3
"""Local MS-envelope development transport. No physical UART or GPIO path.

Both endpoints can share the web simulator's EngineStore. The serial endpoint
is a Linux PTY for application testing, not an ESP32 serial implementation.
"""
import argparse
from contextlib import AbstractContextManager
import errno
import os
from pathlib import Path
import pty
import select
import signal
import socket
import socketserver
import threading
import time
import tty

from engine_runtime import EngineStore, R
from engine_protocol import Stream, envelope


class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  self.request.settimeout(.02)
  stream=Stream(self.server.store)
  try:
   while True:
    try:data=self.request.recv(4096)
    except socket.timeout:
     for response in stream.expire():self.request.sendall(response)
     continue
    if not data:return
    for response in stream.feed(data):self.request.sendall(response)
  except (ConnectionError,OSError):return
  finally:stream.close()


class Server(socketserver.ThreadingTCPServer):
 allow_reuse_address=True
 daemon_threads=True


class TcpEndpoint(AbstractContextManager):
 def __init__(self,store,port=29000):
  self.server=Server(('127.0.0.1',port),Handler)
  self.server.store=store
  self.port=self.server.server_address[1]
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='ECU tuning TCP')
  self.thread.start()
 def close(self):
  self.server.shutdown()
  self.server.server_close()
  self.thread.join(2)
 def __exit__(self,*args):self.close()


class PtyEndpoint(AbstractContextManager):
 """Owned host PTY; optional observer receives bytes actually read/written."""
 def __init__(self,store,path,debug=False,on_wire=None):
  self.store=store
  self.link=Path(path).absolute()
  if self.link.exists() or self.link.is_symlink():raise ValueError('PTY link already exists; choose a new path')
  self.master,slave=pty.openpty()
  tty.setraw(slave)
  self.slave_name=os.ttyname(slave)
  os.close(slave)
  os.set_blocking(self.master,False)
  try:
   self.link.parent.mkdir(parents=True,exist_ok=True)
   self.link.symlink_to(self.slave_name)
  except BaseException:
   os.close(self.master)
   raise
  self.debug=debug
  self.on_wire=on_wire
  self.stop=threading.Event()
  self.failure=''
  self.thread=threading.Thread(target=self.serve,daemon=True,name='ECU tuning PTY')
  self.thread.start()
 def write(self,response):
  deadline=time.monotonic()+2
  while response and not self.stop.is_set():
   if time.monotonic()>deadline:raise TimeoutError('Tuning PTY client stopped reading')
   if not select.select([],[self.master],[],.1)[1]:continue
   try:
    count=os.write(self.master,response)
    if self.on_wire:self.on_wire('TX',response[:count])
    response=response[count:]
   except BlockingIOError:continue
 def serve(self):
  stream=Stream(self.store)
  connected=False
  try:
   while not self.stop.is_set():
    if not select.select([self.master],[],[],.01)[0]:
     if connected:
      for response in stream.expire():self.write(response)
     continue
    try:
     data=os.read(self.master,4096)
     if data:
      connected=True
      if self.on_wire:self.on_wire('RX',data)
      if self.debug:print('RX',len(data),data[:128].hex(),flush=True)
      for response in stream.feed(data):
       if self.debug:print('TX',len(response),response[:128].hex(),flush=True)
       self.write(response)
    except OSError as error:
     if error.errno==errno.EAGAIN:continue
     if error.errno!=errno.EIO:raise
     if connected:stream.close();stream=Stream(self.store);connected=False
     self.stop.wait(.1)
  except (OSError,TimeoutError) as error:
   self.failure=str(error)
   print('Tuning PTY stopped: '+self.failure,flush=True)
  finally:
   stream.close()
   os.close(self.master)
   if self.link.is_symlink() and os.readlink(self.link)==self.slave_name:self.link.unlink()
 def close(self):
  self.stop.set()
  self.thread.join(3)
 def __exit__(self,*args):self.close()


def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--port',type=int,default=29000)
 parser.add_argument('--state',type=Path,default=R/'.cache/engine/tuner-tune.json')
 parser.add_argument('--scenario',default='warm_start')
 parser.add_argument('--pty-link',type=Path)
 parser.add_argument('--debug-protocol',action='store_true')
 args=parser.parse_args()
 store=EngineStore(args.state)
 code,result=store.run(dict(scenario=args.scenario,duration_s=12))
 if code!=200:raise RuntimeError(result)
 endpoint=PtyEndpoint(store,args.pty_link,args.debug_protocol) if args.pty_link else TcpEndpoint(store,args.port)
 def stop(signum,frame):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,stop)
 with endpoint:
  address=f'{endpoint.link} -> {endpoint.slave_name}' if args.pty_link else f'127.0.0.1:{endpoint.port}'
  print(f'Tuning SIL endpoint {address} (completed snapshot, physical outputs inhibited)',flush=True)
  try:
   while not getattr(endpoint,'failure',''):time.sleep(.5)
  except KeyboardInterrupt:pass
if __name__=='__main__':main()
