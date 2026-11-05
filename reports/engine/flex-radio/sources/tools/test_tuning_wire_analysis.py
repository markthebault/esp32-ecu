import tempfile,unittest,zlib
from pathlib import Path
from analyze_tuning_wire import analyze
def frame(payload):return len(payload).to_bytes(2,'big')+payload+zlib.crc32(payload).to_bytes(4,'big')
def event(direction,body):return direction+' '+str(len(body))+' '+body.hex()+'\n'
class WireAnalysisTests(unittest.TestCase):
 def run_capture(self,body):
  with tempfile.TemporaryDirectory()as directory:
   path=Path(directory)/'wire.log';path.write_text(body);return analyze(path)
 def test_every_split_and_coalesced_transactions_are_independent_of_usb_slices(self):
  request=frame(b'Q');answer=frame(b'\0ESP32ECU DEV 009 INHIBITED')
  for cut in range(1,len(request)):
   for response_cut in range(1,len(answer)):
    with self.subTest(cut=cut,response_cut=response_cut):
     body=event('RX',request[:cut])+event('RX',request[cut:]+request)+event('TX',answer[:response_cut])+event('TX',answer[response_cut:]+answer)
     result=self.run_capture(body);self.assertTrue(result['capture_complete']);self.assertFalse(result['invalid_frames']);self.assertEqual(result['complete_transactions'],2);self.assertEqual(result['command_counts'],{'Q':2})
 def test_raw_discovery_reset_prefix_and_framed_capabilities(self):
  body=event('RX',b'\xf0F'+frame(b'f\0'))+event('TX',b'002'+frame(b'\0\2\1\0\1\0'));d=self.run_capture(body)
  self.assertTrue(d['capture_complete']);self.assertEqual(d['reset_prefixes'],1);self.assertEqual(d['complete_transactions'],2);self.assertEqual(d['capabilities'],[dict(protocol=2,read_chunk_bytes=256,write_chunk_bytes=256)])
 def test_corruption_truncation_and_unanswered_tail_are_disclosed(self):
  request=frame(b'Q');bad=bytearray(frame(b'\0hello'));bad[-1]^=1
  result=self.run_capture(event('RX',request)+event('TX',bad)+event('RX',request))
  self.assertEqual(result['invalid_frames'],['Response CRC differs']);self.assertFalse(result['capture_complete']);self.assertEqual(len(result['unanswered_requests']),1)
  self.assertTrue(self.run_capture('RX 3 46\n')['invalid_frames'])
 def test_early_or_extra_response_cannot_be_paired_with_a_future_request(self):
  request=frame(b'C');answer=frame(b'\0\xff')
  for body in(event('TX',answer)+event('RX',request),event('RX',request)+event('TX',answer+answer)+event('RX',request)):
   d=self.run_capture(body);self.assertFalse(d['capture_complete']);self.assertTrue(d['invalid_frames']);self.assertEqual(d['unmatched_response_hex'],answer.hex());self.assertEqual(len(d['unanswered_requests']),1)
if __name__=='__main__':unittest.main()
