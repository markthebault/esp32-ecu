"""Deterministic raw-edge bench stimulus. It is not a fuel chemistry model."""
import math

class FlexStimulus:
 def __init__(self,request=None):
  self.request=request;self.count=0;self.next=0;self.last_query=-1
  if request is None:return
  if not isinstance(request,dict) or set(request) not in ({'frequency_hz','low_pulse_us'},{'frequency_hz','low_pulse_us','dropout_at_s'}):raise ValueError('Flex stimulus requires frequency_hz and low_pulse_us, with optional dropout_at_s')
  for key,lo,hi in [('frequency_hz',10,500),('low_pulse_us',998,5002),('dropout_at_s',.1,30)]:
   value=request.get(key)
   if key=='dropout_at_s' and value is None:continue
   if type(value)not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('Invalid synthetic flex '+key)
  self.period=1e6/request['frequency_hz'];self.width=request['low_pulse_us']
  if self.width>=self.period-2:raise ValueError('Synthetic flex low pulse must fit inside its cycle')
  self.cutoff=round(request['dropout_at_s']*1e6) if 'dropout_at_s' in request else 30000001
 def feed(self,runtime,now):
  if type(now)is not int or now<self.last_query:raise ValueError('Flex stimulus query clock reversed')
  self.last_query=now
  if self.request is None:return
  while self.next<=now and self.next<self.cutoff:
   high=self.count%2==0;runtime.flex_edge(self.next,high);self.count+=1
   cycle=(self.count+1)//2
   self.next=round(cycle*self.period-(self.width if self.count%2 else 0))
 def summary(self):
  return dict(source='synthetic_edges' if self.request is not None else 'unavailable',raw_edges=self.count,stimulus=self.request,qualification='Independent frequency/width stimulus; plant fuel chemistry remains the fixed gasoline model. No ethanol combustion validation.')
