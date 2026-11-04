"""Native finite recorder and real loopback HTTP diagnostic regressions."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from engine_runtime import load_engine_bridge
from trigger_capture import TriggerCapture
from web_server import Device,Handler,load_bridge

class RecorderTests(unittest.TestCase):
 def setUp(self):self.capture=TriggerCapture(load_engine_bridge());self.addCleanup(self.capture.close)
 def test_parser_bounds_duplicates_and_foreign_commands(self):
  for body in [b'{}',b'[]',b'{"action":"start","samples":16,"samples":32,"timeout_ms":100}',
               b'{"action":"start","samples":16,"timeout_ms":100,"physical_outputs":true}',
               b'{"action":"start","samples":true,"timeout_ms":100}',b'{"action":"start","samples":16.5,"timeout_ms":100}',
               b'{"action":"stop","frame_id":0}',b'{"action":"stop","frame_id":1}\0junk',
               b'{"action":"start","samples":513,"timeout_ms":100}',b'{"action":"start","samples":16,"timeout_ms":5001}']:
   self.assertEqual(self.capture.command(body,1000),422,body)
  self.assertEqual(self.capture.command(b'{"action":"start","samples":16,"timeout_ms":50}',1000),200)
  self.assertEqual(self.capture.command(b'{"action":"start","samples":16,"timeout_ms":50}',1001),409)
 def test_invalid_and_prearm_inputs_do_not_contaminate_frozen_frame(self):
  self.capture.command(b'{"action":"start","samples":16,"timeout_ms":100}',1000)
  self.capture.append(900,1100);self.capture.append(0,1101,valid=False)
  for n in range(16):self.capture.append(1200+n,1202+n,cam=bool(n%2),high=bool(n%3))
  self.capture.append(2000)
  frame=self.capture.frame(1,0,512)
  self.assertEqual((frame['state'],frame['count'],frame['prearm_ignored'],frame['invalid_timebase_ignored']),('full',16,1,1))
  self.assertEqual(len(frame['records']),16);self.assertEqual(frame['records'][-1]['captured_us'],1215)
 def test_rearm_discards_stale_pages_and_does_not_stop_current_frame(self):
  start=b'{"action":"start","samples":16,"timeout_ms":50}'
  self.capture.command(start,0);self.capture.expire(50000);self.capture.command(start,50001)
  self.assertEqual(self.capture.command(b'{"action":"stop","frame_id":1}',50002),409)
  old=self.capture.frame(1,0,64);self.assertTrue(old['snapshot_superseded']);self.assertEqual(old['records'],[])
  self.assertEqual(self.capture.frame()['state'],'armed')

class TriggerHTTPTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.device=Device(Path(self.temp.name)/'profile.json',load_bridge())
  self.http=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.http.device=self.device
  self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.http.shutdown();self.http.server_close();self.thread.join(2)
 def request(self,path,body=None,headers=None):
  connection=http.client.HTTPConnection('127.0.0.1',self.http.server_address[1],timeout=10)
  fields={'Content-Type':'application/json','X-ECU-Token':self.device.token};fields.update(headers or {})
  connection.request('GET' if body is None else 'POST',path,body=body,headers=fields)
  response=connection.getresponse();data=response.read();status=response.status;connection.close();return status,data
 def run_sil(self):self.assertEqual(self.device.engine.run(dict(scenario='warm_start',duration_s=3))[0],200)
 def test_auth_envelopes_no_result_and_script_route(self):
  endpoint='/api/engine/trigger-log';body=b'{"action":"start","samples":128,"timeout_ms":1000}'
  self.assertEqual(self.request(endpoint,body,{'X-ECU-Token':'wrong'})[0],403)
  self.assertEqual(self.request(endpoint,body,{'Origin':'http://foreign.invalid'})[0],403)
  self.assertEqual(self.request(endpoint,body,{'Content-Type':'text/plain'})[0],415)
  self.assertEqual(self.request(endpoint,b'x'*257)[0],413)
  self.assertEqual(self.request(endpoint,body)[0],409)
  code,script=self.request('/trigger_logger.js');self.assertEqual(code,200);self.assertIn(b'function renderTriggers',script)
  for query in ('frame_id=0&offset=0','frame_id=1&offset=513','frame_id=1&offset=0&count=512','offset=0&frame_id=1','frame_id=1&offset=-1'):
   self.assertEqual(self.request(endpoint+'?'+query)[0],422,query)
 def test_paged_synthetic_capture_and_stale_writer(self):
  self.run_sil();endpoint='/api/engine/trigger-log';body=b'{"action":"start","samples":512,"timeout_ms":1000}'
  code,data=self.request(endpoint,body);frame=json.loads(data);self.assertEqual(code,200)
  self.assertEqual((frame['state'],frame['count'],frame['records']),('full',512,[]))
  self.assertEqual(frame['data_source'],'completed_sil_rising_crank');self.assertFalse(frame['includes_cam']);self.assertFalse(frame['includes_falling_edges'])
  rows=[]
  for offset in range(0,512,64):
   code,data=self.request(endpoint+f'?frame_id={frame["frame_id"]}&offset={offset}');page=json.loads(data)
   self.assertEqual(code,200);self.assertEqual(len(page['records']),64);self.assertEqual(page['offset'],offset);rows+=page['records']
  self.assertEqual([r['sequence'] for r in rows],list(range(1,513)))
  self.assertTrue(all(r['raw_counter'] is None and r['channel']=='crank' and r['high'] for r in rows))
  self.assertTrue(all(a['captured_us']<b['captured_us'] for a,b in zip(rows,rows[1:])))
  self.assertEqual(self.request(endpoint,body)[0],200)
  code,data=self.request(endpoint+f'?frame_id={frame["frame_id"]}&offset=0');self.assertEqual(code,409)
  self.assertEqual(json.loads(data)['records'],[])
  self.assertEqual(self.request(endpoint,json.dumps(dict(action='stop',frame_id=frame['frame_id'])).encode())[0],409)
  self.assertFalse(self.device.status()['arm']);self.assertFalse(self.device.engine.status()['physical_outputs_enabled'])
 def test_completed_frame_retains_its_source_revision_after_tune_change(self):
  self.run_sil();self.device.engine.trigger_command(b'{"action":"start","samples":128,"timeout_ms":1000}')
  before=self.device.engine.trigger_frame(1,0,True)
  tune=json.loads(json.dumps(self.device.engine.tune));tune['maps']['ve']['cells'][0]=86
  self.assertEqual(self.device.engine.save(json.dumps(tune).encode())[0],200)
  after=self.device.engine.trigger_frame(1,0,True)
  self.assertEqual(after['source_tune_revision'],1);self.assertEqual(after['records'],before['records']);self.assertFalse(after['available'])

if __name__=='__main__':unittest.main(verbosity=2)
