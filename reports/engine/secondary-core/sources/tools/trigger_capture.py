"""Finite native trigger recorder; host web replay stays explicitly historical."""
import ctypes
import json

class TriggerCapture:
 def __init__(self,bridge):
  self.bridge=bridge;P=ctypes.c_void_p;U=ctypes.c_uint;T=ctypes.c_uint64;S=ctypes.c_char_p
  for name,(args,result) in {'trigger_create':([],P),'trigger_destroy':([P],None),
   'trigger_validate':([S,U],ctypes.c_int),'trigger_command':([P,S,U,T],ctypes.c_int),'trigger_append':([P,T,T,U,U,U],None),
   'trigger_expire':([P,T],None),'trigger_frame':([P,U,U,U],S)}.items():
   fn=getattr(bridge,name);fn.argtypes=args;fn.restype=result
  self.handle=bridge.trigger_create()
 def command(self,body,now):return self.bridge.trigger_command(self.handle,body,len(body),now)
 def validate(self,body):return bool(self.bridge.trigger_validate(body,len(body)))
 def append(self,time_us,callback_us=None,counter=0,epoch=0,cam=False,high=True,valid=True):
  self.bridge.trigger_append(self.handle,time_us,time_us if callback_us is None else callback_us,counter,epoch,int(cam)|int(high)<<1|int(valid)<<2)
 def expire(self,now):self.bridge.trigger_expire(self.handle,now)
 def frame(self,expected=0,offset=0,count=0):return json.loads(self.bridge.trigger_frame(self.handle,expected,offset,count))
 def close(self):
  if self.handle:self.bridge.trigger_destroy(self.handle);self.handle=None
 def __del__(self):
  if getattr(self,'handle',None):self.close()
