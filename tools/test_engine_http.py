"""Real loopback HTTP/TCP/PTY integration. No ECU attached."""
import http.client
import json
import os
from pathlib import Path
import select
import socket
import struct
import tempfile
import threading
import time
import tty
import unittest
import zlib
from http.server import ThreadingHTTPServer

from engine_protocol import SIGNATURE,envelope
from web_server import Device,Handler,load_bridge
from tuning_server import TcpEndpoint,PtyEndpoint


class IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name)
  self.device=Device(self.root/'profile.json',load_bridge())
  self.http=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.http.device=self.device
  self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.http.shutdown();self.http.server_close();self.thread.join(2);self.directory.cleanup()
 def request(self,path,method='GET',body=None,headers=None):
  c=http.client.HTTPConnection('127.0.0.1',self.http.server_address[1],timeout=10)
  h={'Content-Type':'application/json','X-ECU-Token':self.device.token};h.update(headers or {})
  c.request(method,path,body=body,headers=h);r=c.getresponse();data=r.read();code=r.status;c.close()
  return code,data
 def frame(self,client,payload):
  client.sendall(envelope(payload))
  def read(n):
   b=b''
   while len(b)<n:
    part=client.recv(n-len(b))
    if not part:raise EOFError('Tuning socket closed early')
    b+=part
   return b
  n=struct.unpack('>H',read(2))[0];answer=read(n);self.assertEqual(struct.unpack('>I',read(4))[0],zlib.crc32(answer)&0xffffffff)
  return answer
 def test_engine_http_auth_schema_and_revision(self):
  code,body=self.request('/api/engine/config');self.assertEqual(code,200);tune=json.loads(body)
  for headers,expected in [({'X-ECU-Token':'wrong'},403),({'Origin':'http://foreign.invalid'},403),({'Content-Type':'text/plain'},415)]:
   self.assertEqual(self.request('/api/engine/config','PUT',body,headers)[0],expected)
  bad=dict(tune,physical_outputs='enabled');self.assertEqual(self.request('/api/engine/config','PUT',json.dumps(bad))[0],422)
  self.assertEqual(self.request('/api/engine/config','PUT',body)[0],200)
  self.assertEqual(self.request('/api/engine/config','PUT',body)[0],409)
 def test_real_tcp_burn_updates_http_and_http_edit_requires_reconnect(self):
  with TcpEndpoint(self.device.engine,0) as endpoint,socket.create_connection(('127.0.0.1',endpoint.port),timeout=2) as client:
   self.assertEqual(self.frame(client,b'Q'),b'\0'+SIGNATURE)
   self.assertEqual(self.frame(client,b'I'),b'\0\0')
   self.assertEqual(self.frame(client,b'f\0'),b'\0\2'+struct.pack('>HH',256,256))
   write=b'M'+struct.pack('<BBHH',0,2,128,4)+struct.pack('<f',91)
   self.assertEqual(self.frame(client,write),b'\0');self.assertEqual(self.frame(client,b'b\0\2'),b'\4')
   code,body=self.request('/api/engine/config');tune=json.loads(body)
   self.assertEqual((code,tune['revision'],tune['maps']['ve']['cells'][0]),(200,2,91))
   tune['maps']['ve']['cells'][0]=87;self.assertEqual(self.request('/api/engine/config','PUT',json.dumps(tune))[0],200)
   read=b'p'+struct.pack('<BBHH',0,2,128,4)
   self.assertEqual(struct.unpack('<f',self.frame(client,read)[1:])[0],91)
   with socket.create_connection(('127.0.0.1',endpoint.port),timeout=2) as reconnected:
    self.assertEqual(struct.unpack('<f',self.frame(reconnected,read)[1:])[0],87)
 def test_http_run_and_log_are_historical_and_tuning_snapshot_identifies_them(self):
  self.assertEqual(self.request('/api/engine/log')[0],409)
  code,body=self.request('/api/engine/run','POST',json.dumps(dict(scenario='warm_start',duration_s=3)))
  self.assertEqual(code,200);self.assertEqual(json.loads(body)['summary']['tune_revision'],1)
  code,log=self.request('/api/engine/log');self.assertEqual(code,200);self.assertIn(b'UNVALIDATED REDUCED-ORDER SIMULATION',log)
  with TcpEndpoint(self.device.engine,0) as endpoint,socket.create_connection(('127.0.0.1',endpoint.port),timeout=2) as client:
   block=self.frame(client,b'r'+struct.pack('<BBHH',0,0x30,0,76));self.assertEqual(block[0],0)
   data=struct.unpack('<11f8I',block[1:]);self.assertEqual(data[13],1);self.assertEqual(data[14],1);self.assertEqual(data[15],1);self.assertEqual(data[-2:],(1,1))
 def test_pty_fragments_and_crc_rejection(self):
  path=self.root/'tuner-serial'
  with PtyEndpoint(self.device.engine,path):
   fd=os.open(path,os.O_RDWR|os.O_NOCTTY);tty.setraw(fd)
   try:
    frame=envelope(b'Q');os.write(fd,frame[:3]);os.write(fd,frame[3:])
    def read(n):
     b=b'';deadline=time.monotonic()+2
     while len(b)<n:
      self.assertLess(time.monotonic(),deadline)
      if select.select([fd],[],[],.05)[0]:b+=os.read(fd,n-len(b))
     return b
    self.assertEqual(read(len(SIGNATURE)+7),envelope(b'\0'+SIGNATURE))
    os.write(fd,frame[:-1]+bytes([frame[-1]^1]));self.assertEqual(read(7),envelope(b'\x82'))
   finally:os.close(fd)
  self.assertFalse(path.is_symlink())


if __name__=='__main__':unittest.main(verbosity=2)
