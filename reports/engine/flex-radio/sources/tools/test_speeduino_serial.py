"""Black-box production serial positive control, without physical hardware."""
import os,queue,struct,tempfile,threading,time,unittest,zlib
from pathlib import Path
from engine_protocol import envelope
from speeduino_serial_runtime import SpeeduinoSerialRuntime,SpeeduinoPtyEndpoint,ROOT

@unittest.skipUnless((ROOT/'.cache/engine/speeduino-serial-sim/build-manifest.json').exists(),'Build scripts/build_speeduino_serial.py for actual production serial tests')
class SpeeduinoSerialTests(unittest.TestCase):
 def setUp(self):
  self.received=queue.Queue();self.runtime=SpeeduinoSerialRuntime(self.received.put);self.addCleanup(self.runtime.close);self.pending=b''
 def read(self,count,timeout=2):
  deadline=time.monotonic()+timeout
  while len(self.pending)<count:
   try:self.pending+=self.received.get(timeout=max(.001,deadline-time.monotonic()))
   except queue.Empty:self.fail('Actual production serial reply timed out: '+self.runtime.failure)
  result,self.pending=self.pending[:count],self.pending[count:];return result
 def frame(self,payload=None):
  if payload is not None:self.runtime.send(envelope(payload))
  head=self.read(2);size=int.from_bytes(head,'big');self.assertTrue(0<size<=1024);body=self.read(size+4)
  self.assertEqual(zlib.crc32(body[:-4]),int.from_bytes(body[-4:],'big'));return body[:-4]
 def test_genuine_discovery_and_inherited_print(self):
  self.runtime.send(b'F');self.assertEqual(self.read(3),b'002')
  self.assertEqual(self.frame(b'Q'),b'\0speeduino 202504-dev')
  self.assertEqual(self.frame(b'f\0'),b'\0\2\0y\0@');self.assertEqual(self.frame(b'f\xff'),b'\0\2\0y\0@')
  # Pinned production I sends4 bytes despite copying a2-byte object. Preserve
  # the quirk; extra bytes are neither a requirement nor synthesized data.
  result=self.frame(b'I');self.assertEqual(result[:2],b'\0\0');self.assertEqual(len(result),4)
 def test_complete_calibration_page_and_independent_crc(self):
  body=b''
  for offset in range(0,288,64):
   reply=self.frame(b'p'+struct.pack('<BBHH',0,2,offset,min(64,288-offset)));self.assertEqual(reply[0],0);body+=reply[1:]
  self.assertEqual(len(body),288)
  reply=self.frame(b'd\0\2');self.assertEqual(reply[0],0);self.assertEqual(int.from_bytes(reply[1:],'big'),zlib.crc32(body))
 def test_runtime_comes_from_static_virtual_adc_and_stopped_engine(self):
  deadline=time.monotonic()+1
  while True:
   data=b''
   for offset in range(0,139,64):
    reply=self.frame(b'r'+struct.pack('<BBHH',0,0x30,offset,min(64,139-offset)));self.assertEqual(reply[0],0);data+=reply[1:]
   settled=struct.unpack_from('<H',data,4)[0]==100 and data[6]in(64,65)and data[7]in(124,125)
   if settled or time.monotonic()>=deadline:break
   time.sleep(.01)
  self.assertEqual(len(data),139);self.assertEqual(struct.unpack_from('<H',data,4)[0],100);self.assertEqual(struct.unpack_from('<H',data,14)[0],0)
  self.assertIn(data[6],(64,65));self.assertIn(data[7],(124,125))
 def test_fragment_can_arrive_while_production_waits_for_crc(self):
  wire=envelope(b'Q');self.runtime.send(wire[:-2]);time.sleep(.05);self.runtime.send(wire[-2:]);self.assertEqual(self.frame(),b'\0speeduino 202504-dev')
 def test_partial_length_times_out_and_recovers(self):
  self.runtime.send(b'\0');started=time.monotonic();self.assertEqual(self.frame(),b'\x80');elapsed=time.monotonic()-started
  self.assertGreater(elapsed,.3);self.assertLess(elapsed,1.5);self.assertEqual(self.frame(b'Q'),b'\0speeduino 202504-dev')
 def test_bad_crc_is_actual_production_error_and_query_recovers(self):
  wire=bytearray(envelope(b'Q'));wire[-1]^=1;self.runtime.send(bytes(wire));self.assertEqual(self.frame(),b'\x82');self.assertEqual(self.frame(b'Q'),b'\0speeduino 202504-dev')
 def test_partial_crc_times_out_and_recovers(self):
  self.runtime.send(envelope(b'Q')[:-2]);self.assertEqual(self.frame(),b'\x80');self.assertEqual(self.frame(b'Q'),b'\0speeduino 202504-dev')
 def test_actual_reference_writes_are_immediately_readable_and_burn_acknowledges(self):
  read=b'p'+struct.pack('<BBHH',0,2,0,1);before=self.frame(read);self.assertEqual(before,b'\0U')
  self.assertEqual(self.frame(b'M'+struct.pack('<BBHH',0,2,0,1)+b'V'),b'\0')
  self.assertEqual(self.frame(read),b'\0V');self.assertEqual(self.frame(b'b\0\2'),b'\4');self.assertEqual(self.frame(read),b'\0V')
  # This characterizes native production RAM/write/burn behavior only. A new
  # process starts its independent fake EEPROM; physical persistence is absent.
 def test_invalid_slice_rejects_before_native_injection(self):
  for body in(b'',b'x'*16385,'Q',bytearray(b'Q')):
   with self.assertRaises(ValueError):self.runtime.send(body)
  self.assertEqual(self.frame(b'Q'),b'\0speeduino 202504-dev')
 def test_concurrent_senders_log_the_same_order_as_real_native_replies(self):
  captured=[];errors=[]
  def observe(direction,body):
   if direction=='RX':captured.append(body[2:-4]);time.sleep(.001)
  self.runtime.on_wire=observe
  def send(command):
   try:self.runtime.send(envelope(command))
   except Exception as error:errors.append(str(error))
  senders=[threading.Thread(target=send,args=(b'Q'if n%2 else b'C',))for n in range(20)]
  for sender in senders:sender.start()
  for sender in senders:sender.join(timeout=2);self.assertFalse(sender.is_alive())
  self.assertFalse(errors)
  for expected in captured:self.assertEqual(self.frame(),b'\0speeduino 202504-dev'if expected==b'Q'else b'\0\xff')
 def test_real_pty_relays_bytes_without_protocol_facade_and_closes(self):
  with tempfile.TemporaryDirectory()as directory:
   path=Path(directory)/'reference';endpoint=SpeeduinoPtyEndpoint(path)
   try:
    fd=os.open(path,os.O_RDWR|os.O_NOCTTY)
    try:
     os.write(fd,b'F');import select
     self.assertTrue(select.select([fd],[],[],2)[0],endpoint.failure+' '+endpoint.runtime.failure);self.assertEqual(os.read(fd,3),b'002')
    finally:os.close(fd)
   finally:endpoint.close();endpoint.close()
   self.assertFalse(path.exists());self.assertFalse(path.is_symlink());self.assertEqual(endpoint.runtime.process.returncode,0);self.assertFalse(endpoint.runtime.failure)
 def test_repeated_client_open_close_does_not_turn_nonblocking_race_into_failure(self):
  with tempfile.TemporaryDirectory()as directory:
   with SpeeduinoPtyEndpoint(Path(directory)/'reference')as endpoint:
    import select
    for _ in range(10):
     fd=os.open(endpoint.link,os.O_RDWR|os.O_NOCTTY)
     try:
      os.write(fd,b'F');self.assertTrue(select.select([fd],[],[],2)[0],endpoint.failure);self.assertEqual(os.read(fd,3),b'002')
     finally:os.close(fd)
    self.assertFalse(endpoint.failure);self.assertFalse(endpoint.runtime.failure)
if __name__=='__main__':unittest.main(verbosity=2)
