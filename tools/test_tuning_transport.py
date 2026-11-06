"""Owned PTY capture must reflect actual full replies, including partial writes."""
import os,select,struct,tempfile,time,unittest,zlib
from pathlib import Path
from unittest.mock import patch
from engine_protocol import envelope,LIVE_BYTES
from engine_runtime import EngineStore
from tuning_server import PtyEndpoint


class PtyCaptureTests(unittest.TestCase):
 def test_full_runtime_capture_matches_partial_os_writes(self):
  with tempfile.TemporaryDirectory() as directory:
   store=EngineStore(Path(directory)/'tune.json');events=[]
   try:
    with PtyEndpoint(store,Path(directory)/'serial',on_wire=lambda direction,body:events.append((direction,bytes(body)))) as endpoint:
     fd=os.open(endpoint.link,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
     try:
      write=os.write
      def sliced(descriptor,body):return write(descriptor,body[:31] if descriptor==endpoint.master else body)
      request=envelope(b'r'+struct.pack('<BBHH',0,0x30,0,LIVE_BYTES))
      with patch('tuning_server.os.write',side_effect=sliced):
       write(fd,request);reply=bytearray();deadline=time.monotonic()+10
       while len(reply)<LIVE_BYTES+7:
        self.assertLess(time.monotonic(),deadline,'Owned PTY reply timed out')
        if select.select([fd],[],[],.05)[0]:reply.extend(os.read(fd,17))
      self.assertEqual(len(reply),1159)
      length=int.from_bytes(reply[:2],'big');self.assertEqual(length,LIVE_BYTES+1)
      self.assertEqual(reply[2],0)
      self.assertEqual(zlib.crc32(reply[2:-4]),int.from_bytes(reply[-4:],'big'))
     finally:os.close(fd)
    self.assertEqual(endpoint.failure,'')
    self.assertEqual(b''.join(data for direction,data in events if direction=='RX'),request)
    self.assertEqual(b''.join(data for direction,data in events if direction=='TX'),bytes(reply))
    self.assertGreater(len([1 for direction,_ in events if direction=='TX']),1)
    self.assertFalse(endpoint.link.exists())
   finally:store.runtime.close();store.data_recorder.close()


if __name__=='__main__':unittest.main(verbosity=2)
