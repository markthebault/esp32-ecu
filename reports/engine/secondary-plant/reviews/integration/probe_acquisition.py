"""Independent executable review probes; never edits the controller sources."""
import copy,hashlib,json,pathlib,sys
BASE=pathlib.Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from compare_engine_controllers import benchmark_tune
from secondary_stimulus import SecondaryMonitor, NEVER
from switch_acquisition_runtime import AcquisitionRuntime
from engine_runtime import EngineRuntime
from target_runtime import TargetRuntime

def tune():
 t=benchmark_tune();t['transient_enrichment']['mode']='off'
 for r in t['secondary_tables'].values():r.update(mode='input',debounce_ms=20)
 return t

def cycle(m,begin,r=None):
 end=m.begin(begin)
 timeline=[]
 while m.next_event()!=NEVER:
  when=m.next_event();m.progress(when);timeline.append(dict(at_us=when,snapshot=m.runtime.snapshot()))
 s,values,completed=m.observe(end)
 o=r.step(dict(rpm=1200,synced=True,**values),end,use_decoder=False)if r is not None and completed else None
 ack=m.consumed(s,completed,end)
 return dict(begin_us=begin,end_us=end,snapshot=s,inputs=values,completed=completed,control=o,ack=ack,timeline=timeline)

checks=[];details={}
def check(ok,label,**data):
 checks.append(dict(passed=bool(ok),label=label,**data))

def main(out):
 m=SecondaryMonitor(tune(),dict(initial=[False,False],edges=[dict(at_us=21199,channel=0,level=True),dict(at_us=21201,channel=0,level=False)]))
 try:
  first=[cycle(m,i)for i in range(0,20000,5000)]
  end=m.begin(20000)
  check(end==21800 and not m.runtime.snapshot()['raw_known'],'guarded read not published at issue')
  for when in (20400,21200):
   m.progress(when);check(not m.runtime.snapshot()['raw_known'],'guarded read not published at stage',stage_us=when)
  gpio_latch=copy.deepcopy(m.pending)
  m.progress(21800);s,values,complete=m.observe(21800);m.consumed(s,complete,21800)
  check(values['table_switches'][0]['level'] and m.program.levels(21800)==[False,False],'GPIO value latched at midpoint rather than completion')
  check(gpio_latch['gpio_sample_us']==21200 and s['observed_us']=='20000' and s['read_completed_us']=='21800','sample time is disclosed and conservative source timestamp preserved')
  held=cycle(m,25000)
  check(held['snapshot']['observed_us']=='20000' and held['snapshot']['read_completed_us']=='21800','write completion cannot refresh source observation')
  details['midpoint_and_write_only']=dict(initialization=first,gpio_latch=gpio_latch,completed=s,write_only=held)
 finally:m.close()
 for label,cls in(('portable',EngineRuntime),('target_dispatcher',TargetRuntime)):
  t=tune();m=SecondaryMonitor(t,dict(initial=[True,True],faults=[dict(begin_us=65000,end_us=150000,kind='producer_pause')]))
  r=cls(t)
  try:
   rows=[cycle(m,i,r)for i in range(0,350000,5000)]
   during=[x for x in rows if 65000<=x['begin_us']<150000]
   stale=[x for x in during if x['control']['secondary_tables']['fuel']['reason']=='input_stale']
   resumed=[x for x in rows if x['snapshot']['fault']=='producer_gap']
   final=rows[-1]
   check(bool(stale) and all(not x['control']['secondary_tables']['fuel']['input_qualified'] and x['control']['faults']&4 for x in stale),label+' independently rejects producer-pause source age')
   check(bool(resumed) and any(x['ack']for x in resumed),label+' resume exposes PollGap and completed invalid observation ACK')
   check(final['control']['secondary_tables']['fuel']['input_qualified'] and not(final['control']['faults']&4),label+' input qualification recovers after new guarded reads and debounce')
   details[label+'_pause']=rows
  finally:m.close();r.close()
 m=SecondaryMonitor(tune(),dict(initial=[True,True],faults=[dict(begin_us=50000,end_us=70000,kind='nack'),dict(begin_us=45000,end_us=250000,kind='control_busy')]))
 try:
  rows=[cycle(m,i)for i in range(0,310000,5000)]
  successful_while_busy=[x for x in rows if not x['completed'] and int(x['snapshot']['reads'])>3 and x['snapshot']['fault_pending']]
  acks=[x for x in rows if x['ack']]
  check(bool(successful_while_busy) and all(not x['snapshot']['ready']for x in successful_while_busy),'successful reads cannot hide a skipped fault while control is busy')
  check(len(acks)==1 and acks[0]['end_us']==250300,'ACK waits for completed invalid observer')
  ack_time=acks[0]['end_us'];ready=next(x for x in rows if x['end_us']>ack_time and x['snapshot']['ready'])
  check(int(ready['snapshot']['observed_us'])>ack_time,'ACK cannot restore pre-ACK read readiness')
  details['busy_ack']=rows
 finally:m.close()
 a=AcquisitionRuntime()
 try:
  op1=a.next(3,0);check(not a.complete(dict(op1,token='999'),3,[],0,400),'foreign completion token rejected')
  a.complete(op1,3,[],0,400);old=a.snapshot()
  op2=a.next(3,100400);a.complete(op2,3,[],100400,100800);new=a.snapshot()
  check(int(new['fault_id'])==int(old['fault_id'])+1 and not a.consumed(old,True),'old fault ID cannot ACK newer failure')
  check(a.snapshot()['fault_pending'] and a.consumed(new,True) and not a.snapshot()['ready'],'exact pending fault ID ACK invalidates readiness')
  details['exact_fault_id']=dict(old=old,new=new,after=a.snapshot())
 finally:a.close()
 t=tune()
 for r in t['secondary_tables'].values():r['mode']='off'
 m=SecondaryMonitor(t)
 try:
  rows=[cycle(m,i)for i in range(0,30000,5000)]
  check(m.runtime.snapshot()['attempts']=='0' and all(x['end_us']==x['begin_us']for x in rows),'Off rules do not issue acquisitions or delay control')
 finally:m.close()
 result=dict(passed=all(x['passed']for x in checks),scope='Direct acquisition and core-input diagnostic, not a coupled engine/target scheduling test. TargetRuntime has no trigger stream here and may separately latch producer_timeout; this probe checks only input qualification/fault bit4.',checks=checks,details=details,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [ROOT/'tools/secondary_stimulus.py',ROOT/'tools/switch_acquisition_runtime.py',ROOT/'tools/switch_acquisition_bridge.cpp',ROOT/'firmware/include/ecu/switch_acquisition.hpp',ROOT/'firmware/include/ecu/secondary_tables.hpp']})
 out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print(json.dumps(dict(passed=result['passed'],checks=checks),indent=2))
 if not result['passed']:raise SystemExit(1)
if __name__=='__main__':
 out=BASE/(sys.argv[1]if len(sys.argv)>1 else'acquisition-probe001.json')
 if out.exists():raise SystemExit('Preserve earlier evidence; output exists')
 main(out)
