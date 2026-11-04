#!/usr/bin/env python3
"""Exercise the actual snapshot/recorder/codecs on the external engine plant.

The network below is a deterministic software fault model, not ESP-NOW RF.
Actual unchanged Speeduino algorithms drive a separate copy of the same plant.
"""
import argparse,copy,hashlib,heapq,json,math,random,time
from pathlib import Path
import compare_engine_controllers as benchmark
from run_target_scenarios import TargetController
from engine_observability import EngineRecorder
from engine_receiver import EngineReceiver,derive_engine_key,INPUT_NAMES,PROPOSAL_NAMES

R=Path(__file__).resolve().parents[1]
LMK=bytes(range(16));BOOT=bytes(range(16,32));MAC='02:EC:00:00:00:01';SESSION=1234567

class Network:
 def __init__(self):
  self.native=EngineRecorder();self.receiver=EngineReceiver(MAC,LMK);self.random=random.Random(314159)
  self.sequence=0;self.nonce=0;self.queue=[];self.order=0;self.samples={};self.packet_count=0
  self.delivered=0;self.rejected={};self.dropped=0;self.tampered=0;self.age_underestimates=0;self.value_mismatches=0
  self.first_live=None;self.last_query=-10000;self.timed=[];self.log_rows=[];self.log_after=0;self.log_gaps=[]
  assert self.native.command(dict(action='start',period_ms=20,duration_s=10),0)==200
  self.query(0)
 def enqueue(self,when,kind,packet):
  self.order+=1;heapq.heappush(self.queue,(when,self.order,kind,packet))
 def request(self,packet,now):
  reply=self.native.capability_reply(packet,LMK,SESSION,BOOT,self.sequence,5000000+now*1000+2000)
  self.enqueue(now+5,'reply',reply)
 def query(self,now):
  self.nonce+=1;self.last_query=now
  self.request(self.receiver.query(now,self.nonce.to_bytes(16,'little')),now)
 def deliver(self,now):
  while self.queue and self.queue[0][0]<=now:
   stamp,_,kind,packet=heapq.heappop(self.queue)
   if kind=='reply':
    self.receiver.receive_reply(packet,MAC,stamp)
    if not self.receiver.features:
     self.nonce+=1;self.request(self.receiver.update(True,stamp,self.nonce.to_bytes(16,'little')),stamp)
    continue
   before=(self.receiver.last_packet,self.receiver.received_ms)
   try:data=self.receiver.receive(packet,MAC,stamp)
   except ValueError as error:
    reason=str(error);self.rejected[reason]=self.rejected.get(reason,0)+1
    assert before==(self.receiver.last_packet,self.receiver.received_ms)
    continue
   self.delivered+=1;self.first_live=stamp if self.first_live is None else self.first_live
   source=self.samples[data['proposal_sequence']]
   for names,key in [(INPUT_NAMES,'inputs'),(PROPOSAL_NAMES,'proposals')]:
    for name in names:
     left,right=data[key][name],source[key][name]
     if left is None or right is None:self.value_mismatches+=left is not right
     else:self.value_mismatches+=not math.isclose(left,right,rel_tol=2e-7,abs_tol=1e-6)
   actual_age=stamp-int(source['sampled_us'])/1000
   self.age_underestimates+=data['bounded_sample_age_ms']+1e-9<actual_age
   assert data['source_code']==2 and data['worker_observation']['physical_command_mask']==0
   ack=self.receiver.acknowledgement();assert len(ack)==56
   if len(self.timed)<12 or stamp%500<60:self.timed.append(dict(received_ms=stamp,sequence=data['packet_sequence'],snapshot=data['proposal_sequence'],actual_age_ms=actual_age,bounded_age_ms=data['bounded_sample_age_ms'],flags=data['flags'],faults=data['controller_faults']))
 def collect(self):
  for _ in range(32):
   page=self.native.page(1,self.log_after)
   if page['gap_first']:self.log_gaps.append([page['gap_first'],page['gap_last']])
   self.log_rows.extend(page['records']);self.log_after=page['next_after']
   if self.log_after>=page['total']:break
 def observe(self,sample):
  us=int(sample['control_us']);now=us//1000;self.deliver(now)
  self.native.append(sample,us);self.samples[int(sample['sequence'])]=sample
  # Refresh the timed nonce query proactively, or after an intentional long gap.
  if now-self.last_query>=4000 or (now-self.last_query>=1000 and self.receiver.status(now)['query_required']):self.query(now)
  if now%50==0 and now>=50:
   slot=now//50
   if slot%10 not in (0,1):
    self.sequence+=1;self.packet_count+=1
    packet=self.native.frame(sample,LMK,BOOT,SESSION,self.sequence,sample_age=0,control_age=0,worker_age=sample['worker_observation']['age_ms'] or 0,sent=5000000+us)
    if 2000<=now<3350 or self.random.random()<.15:self.dropped+=1
    else:
     delay=self.random.randrange(5,41);self.enqueue(now+delay,'engine',packet)
     if self.sequence%13==0:
      bad=bytearray(packet);bad[144]^=1;self.tampered+=1;self.enqueue(now+delay+1,'engine',bytes(bad))
     if self.sequence%11==0:self.enqueue(now+delay+80,'engine',packet) # authenticated replay/reordering
  # Deliberately pause collection longer than5.12s to require an explicit gap.
  if now%250==0 and not 1000<=now<7500:self.collect()
 def finish(self,out):
  self.deliver(10050);self.native.expire(10000000);self.collect();h=self.native.header()
  (out/'retained-engine.msl').write_text(self.native.msl(1,'1234567890abcdef'*2))
  (out/'collected-log.json').write_text(json.dumps(dict(header=h,gaps=self.log_gaps,records=self.log_rows),separators=(',',':'))+'\n')
  result=dict(scope='Software queue loss/delay/reordering/tampering only; no RF or target CPU cost model',packet_slots=self.packet_count,authenticated_deliveries=self.delivered,deliberately_dropped=self.dropped,tampered_copies=self.tampered,rejections=self.rejected,source_value_mismatches=self.value_mismatches,age_underestimates=self.age_underestimates,first_delivery_ms=self.first_live,log_header=h,collected_rows=len(self.log_rows),collected_gaps=self.log_gaps,age_examples=self.timed)
  result['passed']=self.delivered>80 and not self.value_mismatches and not self.age_underestimates and self.log_gaps and h['total']==500 and h['overwritten']==244 and h['missed_periods']==0
  self.native.close();return result

def run(output):
 output.mkdir(parents=True,exist_ok=True);rows=[];started=time.monotonic();original=benchmark.OurController
 cases=[(False,'throttle_step'),(True,'warm_start'),(True,'cam_dropout')]
 try:
  for sequential,scenario in cases:
   folder=output/(('sequential-' if sequential else 'batch-')+scenario);folder.mkdir(exist_ok=True)
   network=Network()
   class ObservedController(TargetController):
    def sample(self,sample,us):
     cut=super().sample(sample,us);network.observe(self.runtime.data());return cut
   benchmark.OurController=ObservedController
   print('Project,',folder.name,flush=True)
   ours=benchmark.run('ours',scenario,10,250,control_period_us=5000,sequential=sequential)
   transport=network.finish(folder)
   print('Speeduino,',folder.name,flush=True)
   reference=benchmark.run('speeduino',scenario,10,250,control_period_us=5000,sequential=sequential,reference_timer_bits=16)
   comparison=dict(project=ours['summary'],speeduino=reference['summary'])
   (folder/'controller-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
   (folder/'network.json').write_text(json.dumps(transport,indent=2)+'\n')
   # Observation must not change the previously reviewed control/plant result.
   previous_path=R/'.cache/engine'/('sequential-final' if sequential else 'sequential-batch-regression')/('native_esp32_dispatcher-'+scenario+'-250.json')
   baseline=None
   if previous_path.exists():
    previous=json.loads(previous_path.read_text())
    baseline=all(ours[k]==previous[k] for k in ('edges','triggers','cams','final_ecu'))
   rows.append(dict(strategy=ours['summary']['strategy'],scenario=scenario,network=transport,observation_preserves_previous_trace=baseline,previous_trace_path=str(previous_path.relative_to(R)),previous_trace_sha256=hashlib.sha256(previous_path.read_bytes()).hexdigest() if previous_path.exists() else None,comparison=comparison))
 finally:benchmark.OurController=original
 paths=['tools/run_engine_observability_scenarios.py','tools/engine_receiver.py','tools/engine_observability_bridge.cpp','tools/target_timing_bridge.cpp','firmware/main/espnow.cpp','firmware/main/engine_service.cpp','firmware/main/engine_log_service.cpp','firmware/main/web_config.cpp']
 paths+=sorted(str(p.relative_to(R)) for p in (R/'firmware/include/ecu').glob('engine_*'))
 report=dict(scope='External verified MVEM air path with local uncalibrated empirical combustion/free shaft, actual native target dispatcher and unchanged pinned Speeduino algorithms; observability does not qualify physical ECU behavior',cases=rows,passed=all(row['network']['passed'] and row['observation_preserves_previous_trace'] is not False for row in rows),runtime_seconds=time.monotonic()-started,source_hashes={p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in paths})
 (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=R/'.cache/engine/observability-scenarios');args=parser.parse_args()
 report=run(args.report_dir);print(json.dumps(dict(passed=report['passed'],cases=len(report['cases']),runtime_seconds=report['runtime_seconds']),indent=2));raise SystemExit(0 if report['passed'] else 1)
