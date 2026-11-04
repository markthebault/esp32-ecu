"""Independent contact program and delayed synthetic MCP transaction fixture.

The actual portable acquisition state machine supplies validity/qualification
inputs. This models a blocking5ms monitor operation while the plant/dispatcher
continues, not physical I2C timing, electrical behavior or measured MCU load.
"""
import bisect,copy
from switch_acquisition_runtime import AcquisitionRuntime
NEVER=2**64-1
KINDS={'nack','timeout','unavailable','marker','loop_stuck_low','configuration','reset_before_guard','overrun','underfill','producer_pause','control_busy'}
class ContactProgram:
 def __init__(self,spec=None):
  if spec is not None and not isinstance(spec,dict):raise ValueError('A contact program object is required')
  spec=copy.deepcopy(spec if spec is not None else {})
  if set(spec)-{'initial','edges','faults'}:raise ValueError('Unknown contact program fields')
  self.initial=spec.get('initial',[False,False]);self.edges=spec.get('edges',[]);self.faults=spec.get('faults',[])
  if not isinstance(self.initial,list)or len(self.initial)!=2 or any(type(v)is not bool for v in self.initial):raise ValueError('Two initial boolean contact levels required')
  self.times=[[],[]];self.values=[[],[]];events=set();previous=[-1,-1]
  for e in self.edges:
   if not isinstance(e,dict)or set(e)!={'at_us','channel','level'}or type(e['at_us'])is not int or not 0<=e['at_us']<=60_000_000 or type(e['channel'])is not int or e['channel']not in(0,1)or type(e['level'])is not bool:raise ValueError('Invalid contact event')
   channel=e['channel'];when=e['at_us']
   if when<=previous[channel]:raise ValueError('Per-channel contact times must strictly increase')
   previous[channel]=when;self.times[channel].append(when);self.values[channel].append(e['level']);events.add(when)
  for f in self.faults:
   if not isinstance(f,dict)or set(f)!={'begin_us','end_us','kind'}or f['kind']not in KINDS or any(type(f[k])is not int for k in('begin_us','end_us'))or not 0<=f['begin_us']<f['end_us']<=60_000_000:raise ValueError('Invalid synthetic fault window')
   events.update((f['begin_us'],f['end_us']))
  self.events=sorted(events)
 def levels(self,now):
  result=[]
  for channel in(0,1):
   index=bisect.bisect_right(self.times[channel],now)-1;result.append(self.values[channel][index]if index>=0 else self.initial[channel])
  return result
 def active(self,now):return {f['kind']for f in self.faults if f['begin_us']<=now<f['end_us']}
 def next_event(self,now):
  index=bisect.bisect_right(self.events,now);return self.events[index]if index<len(self.events)else NEVER

class Device:
 def __init__(self):self.reset()
 def reset(self):self.registers=[255]+[0]*10
 def gpio(self,levels,active):
  r=self.registers;loop=not(r[0]&128)and bool(r[10]&128)
  physical=(0x20 if 'marker'in active else 0x28)|int(levels[0])|(int(levels[1])<<1)|(int(loop and 'loop_stuck_low'not in active)<<6)
  # Inputs read external levels; outputs read their driven latch. This is a
  # digital register/pin model with no transistor/clamp/analog qualification.
  return ((physical&r[0])|(r[10]&(~r[0]&255)))^r[1]
 def read(self,reg,levels,active):return self.gpio(levels,active)if reg==9 else self.registers[reg]
 def write(self,reg,data):
  for v in data:
   self.registers[reg]=v
   if not(self.registers[5]&32):reg=(reg+1)%11

class SecondaryMonitor:
 def __init__(self,tune,program=None):
  self.program=program if isinstance(program,ContactProgram)else ContactProgram(program);self.mask=0
  for r in tune['secondary_tables'].values():
   if r['mode']=='input':
    if type(r['input_channel'])is not int or r['input_channel']not in(0,1):raise ValueError('Protected input channel must be0or1')
    self.mask|=1<<r['input_channel']
  self.runtime=AcquisitionRuntime();self.device=Device()
  self.pending=None;self.stages=[];self.reset_windows=set();self.history=[];self.applied_faults=[];self.last_begin=None
 def begin(self,now):
  if self.pending or self.stages:raise ValueError('Monitor cannot begin another transaction before completion')
  self.last_begin=now
  active=self.program.active(now)
  if 'producer_pause'in active:return now
  request=self.runtime.next(self.mask,now)
  if not request['kind']:return now
  kind=request['kind'];duration=1800 if kind==5 else 850 if kind==3 else 400 if kind==1 else 300
  result=2 if 'timeout'in active else 1 if 'unavailable'in active else 3 if 'nack'in active else 0
  if result:duration=3000 if result==2 else 400
  if 'overrun'in active:duration=3001
  self.pending=dict(request=request,started=now,ended=now+duration,result=result,data=[],faults=[])
  if result:
   self.pending['faults']=[k for k in('timeout','unavailable','nack')if k in active];self.stages=[(now+duration,'complete')]
  elif kind==5:
   self.pending['data']=[0xa5]*12;self.stages=[(now+400,'config'),(now+1200,'gpio'),(now+duration,'guard')]
   for index,f in enumerate(self.program.faults):
    if f['kind']=='reset_before_guard'and f['begin_us']<=now<f['end_us']and index not in self.reset_windows and not self.runtime.snapshot()['challenge_high']:
     self.stages.append((now+duration-100,'reset'));self.reset_windows.add(index);break
   self.stages.sort()
  else:self.stages=[(now+duration,'complete')]
  if 'overrun'in active:self.pending['faults'].append('overrun')
  return now+duration
 def next_event(self):return self.stages[0][0]if self.stages else NEVER
 def progress(self,now):
  if self.stages and self.stages[0][0]<now:raise ValueError('Integration skipped a transaction stage')
  while self.stages and self.stages[0][0]==now:
   _,stage=self.stages.pop(0);p=self.pending;op=p['request'];active=self.program.active(now);levels=self.program.levels(now)
   if stage=='reset':self.device.reset();p['faults'].append('reset_before_guard');continue
   if stage=='config':
    if 'configuration'in active:self.device.registers[0]=255;p['faults'].append('configuration')
    p['data'][:9]=[self.device.read(i,levels,active)for i in range(9)];continue
   if stage=='gpio':
    p['data'][9:11]=[self.device.read(i,levels,active)for i in(9,10)]
    p['gpio_sample_us']=now;p['raw_at_gpio']=levels
    for k in('marker','loop_stuck_low'):
     if k in active:p['faults'].append(k)
    continue
   if stage=='guard':
    p['data'][11]=self.device.read(0,levels,active)
    if 'underfill'in active:p['data'][11]=0xa5;p['faults'].append('underfill')
   elif not p['result']:
    if op['write_size']:self.device.write(op['reg'],op['data'])
    else:
     p['data']=[self.device.read(op['reg'],levels,active)]
     if 'marker'in active:p['faults'].append('marker')
   if not self.runtime.complete(op,p['result'],p['data'],p['started'],now):raise RuntimeError('Owned synthetic acquisition completion rejected')
   self.applied_faults.extend(dict(kind=k,token=op['token'],kind_code=op['kind'],started_us=p['started'],completed_us=now)for k in p['faults'])
   self.pending=None
 def observe(self,now):
  if self.pending or self.stages:raise ValueError('Cannot publish an unfinished synchronous monitor transaction')
  snapshot=self.runtime.snapshot()
  inputs={}if not snapshot['raw_known']else{'table_switches':[{k:x[k]for k in('valid','level','observed_us')}for x in snapshot['samples']]}
  return snapshot,inputs,'control_busy'not in self.program.active(now)
 def consumed(self,snapshot,completed,now):
  acknowledged=self.runtime.consumed(snapshot,completed)
  self.history.append(dict(monitor_begin_us=self.last_begin,control_attempt_us=now,control_completed=completed,fault_acknowledged=acknowledged,acquisition=copy.deepcopy(snapshot)))
  return acknowledged
 def close(self):self.runtime.close()
