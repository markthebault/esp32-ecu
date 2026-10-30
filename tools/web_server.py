#!/usr/bin/env python3
"""Offline ECU UI simulator. Never connects to, or drives, vehicle hardware.
Requires a C++ compiler and ESP-IDF's cJSON source installed by PlatformIO.
"""
import argparse,ctypes,json,math,os,secrets,subprocess,sys,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from radio_simulator import RadioSimulator
R=Path(__file__).resolve().parents[1]
class Reading(ctypes.Structure):
 _fields_=[('value',ctypes.c_double),('sensor_v',ctypes.c_double),('adc_v',ctypes.c_double),('valid',ctypes.c_int),('fault',ctypes.c_char*64)]
def load_bridge():
 target=R/'.cache/web';target.mkdir(parents=True,exist_ok=True)
 source=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
 if not (source/'cJSON.c').exists():raise RuntimeError('Install the pinned PlatformIO ESP-IDF framework first; see docs/web-configuration.md.')
 lib=target/('config_bridge.dylib' if sys.platform=='darwin' else 'config_bridge.so')
 deps=[R/'tools/config_bridge.cpp',R/'firmware/main/config_json.hpp',R/'firmware/include/ecu/config.hpp',source/'cJSON.c']
 if not lib.exists() or max(p.stat().st_mtime for p in deps)>lib.stat().st_mtime:
  subprocess.run(['cc','-O2','-fPIC','-c',str(source/'cJSON.c'),'-o',str(target/'cJSON.o')],check=True)
  subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(source),'-I'+str(R/'firmware/main'),'-I'+str(R/'firmware/include'),str(R/'tools/config_bridge.cpp'),str(target/'cJSON.o'),'-o',str(lib)],check=True)
 bridge=ctypes.CDLL(str(lib));bridge.validate_profile.argtypes=[ctypes.c_char_p];bridge.validate_profile.restype=ctypes.c_int
 bridge.evaluate_profile.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_double),ctypes.POINTER(Reading)];bridge.evaluate_profile.restype=ctypes.c_int
 return bridge
class Device:
 def __init__(self,path,bridge):
  self.radio=RadioSimulator(path.with_name(path.name+'.peers'));self.path=path;self.bridge=bridge;self.lock=threading.Lock();self.started=time.monotonic();self.token=secrets.token_hex(16);self.faults={};self.filtered=None;self.last=0;self.storage_ok=True;self.storage='defaults; no saved profile'
  self.defaults=json.loads((R/'config/defaults.json').read_text());self.profile=self.defaults
  if path.exists():
   try:
    text=path.read_bytes()
    if len(text)>16384 or not bridge.validate_profile(text):raise ValueError('invalid saved profile')
    self.profile=json.loads(text);self.storage='loaded from disk (simulated NVS)'
   except (ValueError,OSError):self.storage_ok=False;self.storage='saved profile invalid; defaults active; saving blocked'
 def save(self,body):
  if len(body)>16384:return 413,{'error':'Profile exceeds 16 KiB.'}
  if b'\x00' in body or not self.bridge.validate_profile(body):return 422,{'error':'Profile violates schema or calibration limits.'}
  p=json.loads(body)
  with self.lock:
   if not self.storage_ok:return 503,{'error':'Storage fault. Inspect saved profile file.'}
   if p['revision']!=self.profile['revision'] or p['revision']==4294967295:return 409,{'error':'Profile revision changed. Export edits, reload, then reapply them.'}
   p['revision']+=1;encoded=json.dumps(p,separators=(',',':'),allow_nan=False).encode();self.path.parent.mkdir(parents=True,exist_ok=True)
   temp=None
   try:
    with tempfile.NamedTemporaryFile(dir=self.path.parent,delete=False) as f:temp=Path(f.name);f.write(encoded);f.flush();os.fsync(f.fileno())
    os.replace(temp,self.path)
   except OSError:
    if temp and temp.exists():temp.unlink()
    return 507,{'error':'Save failed. Previous runtime profile remains active.'}
   self.profile=p;self.filtered=None;self.storage='saved to disk (simulated NVS)';return 200,p
 def status(self):
  with self.lock:
   p=self.profile;now=time.monotonic();t=now-self.started;rail=5.;values=[2.24+.015*math.sin(t*.7),.72+.008*math.sin(t*.5),2.12+.003*math.sin(t),2.82+.006*math.sin(t*.6),2.45+.018*math.sin(t),.56+.008*math.sin(t*.4)]
   ids=['map','tps','clt','iat','wideband','postcat']
   if any(f=='rail' for f in self.faults.values()):rail=2.4;values=[v*rail/5 for v in values]
   for i,sid in enumerate(ids):
    fault=self.faults.get(sid,'normal')
    if fault=='short':values[i]=0.
    elif fault=='high':values[i]=5.28
    elif fault=='noise':values[i]=max(0,min(5.25,values[i]+.5*math.sin(t*37)))
   adc=lambda v:round(max(0,min(4095,v/3.3*4095)))
   raw=[adc(v*.6) for v in values]+[adc(12.64/13),adc(rail*.6)]
   sv=[v*p['adc_reference_v']/4095/.6 for v in raw[:6]];dt=max(0,(now-self.last)*1000)
   if self.filtered is None:self.filtered=sv.copy()
   else:
    for i,s in enumerate(p['sensors']):self.filtered[i]+=dt/(s['filter_ms']+dt)*(sv[i]-self.filtered[i]) if dt else 0
   self.last=now;out=(Reading*6)();ok=self.bridge.evaluate_profile(json.dumps(p).encode(),(ctypes.c_uint*8)(*raw),(ctypes.c_double*6)(*self.filtered),out);assert ok
   sensors=[{'id':s['id'],'raw':raw[i],'adc_v':out[i].adc_v,'sensor_v':out[i].sensor_v,'value':out[i].value if out[i].valid else None,'valid':bool(out[i].valid),'confirmed':s['confirmed'],'fault':out[i].fault.decode()} for i,s in enumerate(p['sensors'])]
   return dict(simulator=True,firmware='A3 host simulator / no physical hardware',uptime_s=t,sample_age_ms=0,fresh=True,revision=p['revision'],storage_ok=self.storage_ok,storage=self.storage,adc_ok=True,safe=True,interlock=False,overflow=False,synced=False,rpm=0,can_frames=0,cam_edges=0,crank_edges=0,crank_level=0,cam_level=0,arm=False,output_state='All outputs OFF',sensor_5v=raw[7]*p['adc_reference_v']/4095/.6,battery_v=raw[6]*p['adc_reference_v']/4095*13,raw_adc=raw,sensors=sensors)
class Handler(BaseHTTPRequestHandler):
 server_version='ECUSimulator/1'
 def log_message(self,fmt,*args):pass
 def reply(self,status,data,kind='application/json'):
  body=json.dumps(data,allow_nan=False).encode() if kind=='application/json' else data
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'");self.end_headers();self.wfile.write(body)
 def do_GET(self):
  d=self.server.device
  if self.path in ('/','/index.html'):return self.reply(200,(R/'web/index.html').read_bytes(),'text/html; charset=utf-8')
  if self.path=='/api/session':return self.reply(200,dict(token=d.token,simulator=True))
  if self.path=='/api/config':
   with d.lock:return self.reply(200,d.profile)
  if self.path=='/api/defaults':return self.reply(200,d.defaults)
  if self.path=='/api/guide':return self.reply(200,json.loads((R/'config/interface-guide.json').read_text()))
  if self.path=='/api/manual':return self.reply(200,json.loads((R/'config/manual.json').read_text()))
  if self.path=='/api/radio':
   origin=self.headers.get('Origin');host=self.headers.get('Host','')
   if self.headers.get('X-ECU-Token')!=d.token or (origin and origin!='http://'+host):return self.reply(403,{'error':'Session token or origin rejected.'})
   with d.lock:return self.reply(200,d.radio.status())
  if self.path=='/api/status':return self.reply(200,d.status())
  return self.reply(404,{'error':'Not found'})
 def mutate(self):
  d=self.server.device;origin=self.headers.get('Origin');host=self.headers.get('Host')
  if self.headers.get('X-ECU-Token')!=d.token or (origin and origin!='http://'+host):return self.reply(403,{'error':'Session token or origin rejected.'})
  if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply(415,{'error':'Use application/json.'})
  try:length=int(self.headers.get('Content-Length','0'))
  except ValueError:return self.reply(400,{'error':'Invalid length'})
  if not 0<length<=16384:return self.reply(413,{'error':'Body must be 1-16384 bytes.'})
  body=self.rfile.read(length)
  if self.command=='POST' and self.path=='/api/radio':
   if len(body)>256:return self.reply(413,{'error':'Radio command exceeds 256 bytes.'})
   try:
    data=json.loads(body)
    with d.lock:result=d.radio.command(data)
    return self.reply(*result)
   except (ValueError,KeyError,TypeError):return self.reply(422,{'error':'Invalid radio command.'})
  if self.command=='PUT' and self.path=='/api/config':return self.reply(*d.save(body))
  if self.command=='POST' and self.path=='/api/simulate':
   try:
    data=json.loads(body);sensor=data['sensor'];fault=data['fault']
    if sensor not in ['map','tps','clt','iat','wideband','postcat'] or fault not in ['normal','short','high','noise','rail']:raise ValueError()
    with d.lock:d.faults[sensor]=fault
    return self.reply(200,{'ok':True})
   except (ValueError,KeyError,TypeError):return self.reply(422,{'error':'Invalid simulator condition'})
  return self.reply(404,{'error':'Not found'})
 do_PUT=mutate;do_POST=mutate
 def setup(self):super().setup();self.connection.settimeout(5)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765);parser.add_argument('--state',type=Path,default=R/'.cache/web/profile.json');args=parser.parse_args()
 server=ThreadingHTTPServer((args.host,args.port),Handler);server.device=Device(args.state,load_bridge());print(f'ECU simulator: http://{args.host}:{args.port} (no hardware)',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=='__main__':main()
