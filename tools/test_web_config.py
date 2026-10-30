#!/usr/bin/env python3
import copy,ctypes,json,math,tempfile,unittest,http.client,threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from web_server import Device,Reading,load_bridge,Handler
R=Path(__file__).resolve().parents[1]
class ConfigTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.bridge=load_bridge();cls.base=json.loads((R/'config/defaults.json').read_text())
 def setUp(self):self.p=copy.deepcopy(self.base)
 def valid(self,p=None):return bool(self.bridge.validate_profile(json.dumps(p or self.p).encode()))
 def readings(self,values):
  raw=[round(v*.6/3.3*4095) for v in values]+[round(12/13/3.3*4095),round(5*.6/3.3*4095)];filtered=[v*3.3/4095/.6 for v in raw[:6]];out=(Reading*6)()
  self.assertEqual(self.bridge.evaluate_profile(json.dumps(self.p).encode(),(ctypes.c_uint*8)(*raw),(ctypes.c_double*6)(*filtered),out),1);return out
 def test_real_defaults_parse(self):self.assertTrue(self.valid())
 def test_unknown_duplicate_and_nonfinite_fields_rejected(self):
  original=json.dumps(self.p)
  for text in ['{"revision":1,'+original[1:],original.replace('3.3','1e999',1),original[:-1]+',"unexpected":1}']:
   self.assertEqual(self.bridge.validate_profile(text.encode()),0)
 def test_deep_json_rejected_before_recursive_parse(self):
  self.assertEqual(self.bridge.validate_profile(('['*1000+'0'+']'*1000).encode()),0)
 def test_channel_identity_cannot_be_remapped(self):self.p['sensors'].reverse();self.assertFalse(self.valid())
 def test_invalid_curve_and_geometry_rejected(self):
  for field,value in [('v1',.5),('filter_ms',-1),('fault_high_v',.01)]:
   p=copy.deepcopy(self.p);p['sensors'][0][field]=value;self.assertFalse(self.valid(p))
  self.p['trigger']['missing']=3;self.p['trigger']['slots']=12;self.assertFalse(self.valid())
 def test_voltage_quantization(self):self.assertAlmostEqual(self.readings([2.1]*6)[0].value,2.1,delta=.001)
 def test_linear_and_reverse_transfer(self):
  s=self.p['sensors'][0];s.update(mode='linear',v0=.5,y0=100,v1=4.5,y1=0)
  self.assertAlmostEqual(self.readings([2.5]*6)[0].value,50,delta=.03)
  self.assertFalse(self.readings([.1]*6)[0].valid)
 def test_table_interpolation_and_no_extrapolation(self):
  s=self.p['sensors'][0];s.update(mode='table',points=[dict(v=.5,value=0),dict(v=2.5,value=20),dict(v=4.5,value=100)])
  self.assertAlmostEqual(self.readings([3.5]*6)[0].value,60,delta=.05)
  self.assertFalse(self.readings([5.]*6)[0].valid)
  s['points'].reverse();self.assertFalse(self.valid())
 def test_ntc_corrects_input_loading(self):
  s=self.p['sensors'][2];s.update(mode='ntc_beta',pullup_fitted=True)
  for temp in [-20,0,25,80,120]:
   r=10000*math.exp(3950*(1/(temp+273.15)-1/298.15));req=1/(1/r+1/55000);v=5*req/(2490+req);values=[2.]*6;values[2]=v
   out=self.readings(values)[2];self.assertTrue(out.valid,out.fault);self.assertAlmostEqual(out.value,temp,delta=.25)
 def test_ntc_requires_physical_pullup_and_correct_channel(self):
  self.p['sensors'][2]['mode']='ntc_beta';self.assertFalse(self.valid());self.p['sensors'][2]['pullup_fitted']=True;self.assertTrue(self.valid());self.p['sensors'][0].update(mode='ntc_beta',pullup_fitted=True);self.assertFalse(self.valid())
 def test_instant_fault_does_not_depend_on_confirmation(self):
  out=self.readings([0]*6);self.assertTrue(all(not x.valid for x in out));self.assertIn(b'below',out[0].fault)
 def test_save_restart_and_stale_revision(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'profile.json';d=Device(path,self.bridge);self.p['sensors'][0].update(mode='linear',unit='kPa',y0=10,y1=110)
   code,p=d.save(json.dumps(self.p).encode());self.assertEqual(code,200);self.assertEqual(p['revision'],2)
   code,_=d.save(json.dumps(self.p).encode());self.assertEqual(code,409)
   restarted=Device(path,self.bridge);self.assertEqual(restarted.profile['sensors'][0]['unit'],'kPa');self.assertEqual(restarted.profile['revision'],2)
 def test_corrupt_storage_blocks_overwrite(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'profile.json';path.write_text('{corrupt');d=Device(path,self.bridge);self.assertFalse(d.storage_ok);self.assertEqual(d.save(json.dumps(self.p).encode())[0],503);self.assertEqual(path.read_text(),'{corrupt')
 def test_save_failure_preserves_runtime_profile(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'directory';d=Device(path,self.bridge);path.mkdir();old=copy.deepcopy(d.profile)
   self.assertEqual(d.save(json.dumps(self.p).encode())[0],507);self.assertEqual(d.profile,old)
class HttpTests(unittest.TestCase):
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory();self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.device=Device(Path(self.folder.name)/'state.json',load_bridge());self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.folder.cleanup()
 def request(self,method,path,body=None,headers=None):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request(method,path,body,headers or {});r=c.getresponse();result=r.status,json.loads(r.read());c.close();return result
 def test_http_requires_boot_token_and_same_origin(self):
  body=json.dumps(self.server.device.profile);self.assertEqual(self.request('PUT','/api/config',body,{'Content-Type':'application/json'})[0],403)
  headers={'Content-Type':'application/json','X-ECU-Token':self.server.device.token,'Origin':'http://another-host'}
  self.assertEqual(self.request('PUT','/api/config',body,headers)[0],403)
 def test_radio_authentication_and_pair_unpair(self):
  self.assertEqual(self.request('GET','/api/radio')[0],403)
  headers={'Content-Type':'application/json','X-ECU-Token':self.server.device.token}
  self.assertEqual(self.request('GET','/api/radio',headers={**headers,'Origin':'http://wrong'})[0],403)
  self.assertEqual(self.request('POST','/api/radio','{"action":"open"}')[0],403)
  self.assertEqual(self.request('POST','/api/radio','{"action":"open"}',headers)[0],202)
  _,state=self.request('GET','/api/radio',headers=headers);self.assertTrue(state['pairing']);self.assertEqual(state['led'],'blue_blink');self.assertEqual(len(state['setup_key']),32)
  self.assertEqual(self.request('POST','/api/radio','{"action":"simulate"}',headers)[0],202)
  _,state=self.request('GET','/api/radio',headers=headers)
  body=json.dumps(dict(action='confirm',mac=state['candidate']['mac'],window=state['window']))
  self.assertEqual(self.request('POST','/api/radio',body,headers)[0],202)
  _,state=self.request('GET','/api/radio',headers=headers);self.assertEqual(len(state['peers']),1);self.assertFalse(state['pairing']);self.assertEqual(state['setup_key'],'')
  self.assertEqual(self.request('POST','/api/radio',json.dumps(dict(action='unpair',mac=state['peers'][0]['mac'])),headers)[0],202)
  _,state=self.request('GET','/api/radio',headers=headers);self.assertEqual(state['peers'],[])
 def test_radio_rejects_malformed_commands(self):
  headers={'Content-Type':'application/json','X-ECU-Token':self.server.device.token}
  for body in ['{bad','[]','{"action":"enable_outputs"}']:
   self.assertEqual(self.request('POST','/api/radio',body,headers)[0],422)
  self.assertEqual(self.request('POST','/api/radio',' '*257,headers)[0],413)
 def test_http_save_and_live_conversion(self):
  code,p=self.request('GET','/api/config');self.assertEqual(code,200);p['sensors'][0].update(mode='linear',unit='kPa',y0=10,y1=110)
  headers={'Content-Type':'application/json','X-ECU-Token':self.server.device.token};code,saved=self.request('PUT','/api/config',json.dumps(p),headers);self.assertEqual(code,200)
  code,status=self.request('GET','/api/status');self.assertEqual(code,200);self.assertEqual(status['revision'],saved['revision']);self.assertGreater(status['sensors'][0]['value'],50);self.assertFalse(status['arm'])
 def test_manual_reader_serves_the_pdf_text(self):
  code,manual=self.request('GET','/api/manual');self.assertEqual(code,200)
  self.assertTrue(manual['pages']);self.assertTrue(any('splash' in p['text'].lower() for p in manual['pages']))
 def test_http_simulated_short_flags_fault(self):
  headers={'Content-Type':'application/json','X-ECU-Token':self.server.device.token}
  self.assertEqual(self.request('POST','/api/simulate',json.dumps(dict(sensor='map',fault='short')),headers)[0],200)
  _,status=self.request('GET','/api/status');self.assertFalse(status['sensors'][0]['valid']);self.assertIsNone(status['sensors'][0]['value']);self.assertEqual(status['sensors'][0]['raw'],0)
if __name__=='__main__':unittest.main(verbosity=2)
