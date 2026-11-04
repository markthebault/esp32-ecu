from pathlib import Path
import collections,copy,gzip,hashlib,json,math,os,subprocess,datetime
O=Path(__file__).resolve().parent;F=O/'final-freeze-003';R=Path('/home/mark/persospace/esp32-ecu');S=R.parent/'speeduino';OUT=O/'execution-003';OUT.mkdir(exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest(); summary=json.loads((F/'parent-matrix/summary.json').read_text()); manifest=json.loads((F/'.cache/engine/speeduino-flex-sim/build-manifest.json').read_text());exe=F/'.cache/engine/speeduino-flex-sim/speeduino-flex-sim'
assert sha(exe.read_bytes())==manifest['binary_sha256']=='1f3b546e9d52ffb1defee63d870540b99579305c0a6566a638436d7905e71ff2'
expected_names={'e0-neutral-startup','e50-ramp','e50-neutral','e50-cold-ramp','e50-hot-ramp','e85-ramp','e100-neutral','e1-reference-deadband','low-frequency48','high-frequency160','sensor-fault170','counter-wrap356','short-low-pulse','long-low-pulse','lower-tolerance49','upper-tolerance151','custom40-160-span','reference-filter75','disabled-curves-live-acquisition','dropout','hidden-width-fault-and-ack','flat-high','flat-low','e50-phase1us','e50-loop-refinement'}
assert {r['name'] for r in summary['results']}==expected_names and len(summary['results'])==25
checks=0
class AuditError(Exception):pass
def ck(value,message):
 global checks
 checks+=1
 if not value:raise AuditError(message)
def close(a,b,epsilon=1e-8):return a is not None and math.isfinite(a) and abs(a-b)<epsilon
def rr(n,d):
 q,r=divmod(n,d);return q+(2*r>d or (2*r==d and q%2==1))
def stimulus(c):
 end=max(c['samples']);events=set();phase=c.get('phase_us',0)
 for start,stop,hz,w in c['segments']:
  n=0
  while start+rr(n*1000000,hz)+phase<stop+1000000//hz+2:
   for t,l in [(start+rr(n*1000000,hz)+phase,1),(start+rr((n+1)*1000000,hz)-w+phase,0)]:
    if start<=t<stop and t<=end:events.add((t,0,'edge',l))
   n+=1
 for t,l in c.get('manual_edges',[]):events.add((t,0,'edge',l))
 t=0
 while t<=end:
  if (t//500)%60<58:
   events.add((t,1,'trigger',1))
   if t+100<=end:events.add((t+100,1,'trigger',0))
  t+=500
 obs=set(c['samples'])
 if c.get('refinement_us'):obs.update(range(0,end+1,c['refinement_us']))
 events.update((t,2,'observe',None) for t in obs);events.update((t,3,'ack',None) for t in c.get('ack_times',[]));events=sorted(events)
 body=''.join(f'{k} {t}'+(' '+str(l) if l is not None else '')+'\n' for t,_,k,l in events)+'quit\n';return body,events

def audit(c,rows,events):
 ck(rows[0]['kind']=='ready','setup receipt');rdy=rows[0]
 ck(rdy['time_us']==0 and rdy['flex_pin']==2 and rdy['flex_interrupt']==0 and rdy['trigger_pin']==19,'resolved production pins')
 ck(rdy['enabled']==c['enabled'] and rdy['callback_is_flexPulse']==c['enabled'] and rdy['trigger_callback_registered'],'real attached callbacks')
 ck(rdy['tick_before_input'] and rdy['trigger_on_high'] and not rdy['trigger_on_low'],'declared native ordering/polarity')
 ck((rdy['low_hz'],rdy['high_hz'],rdy['reference_filter'])==(c['low_hz'],c['high_hz'],c['reference_filter']),'calibration readback')
 obs=[x for x in rows if x['kind']=='snapshot'];acks=[x for x in rows if x['kind']=='ack'];ck([x['time_us'] for x in obs]==[t for t,_,k,l in events if k=='observe'],'all observation times')
 ck([x['time_us'] for x in acks]==c.get('ack_times',[]),'all ACK times');bytime={x['time_us']:x for x in obs};level={'edge':0,'trigger':0};raw=delivered=trig=counter=0;eth=0;temp=0;pw=0;lowstart=0;tick=1000000;lastedge=0;rises=[];falls=[];alpha=c['reference_filter'];enabled=c['enabled']
 for t,_,kind,l in events:
  while tick<=t:
   if enabled:
    low,high=c['low_hz'],c['high_hz'];pct=0 if counter<low else (100 if counter>high+1 and counter<high+20 else 0 if counter>high+1 else counter-low);pct=0 if pct==1 else min(100,pct)
    eth=(pct*(256-alpha)+eth*alpha)//256;pw=min(5000,max(1000,pw));x=((4224*pw)>>10)-8125;temp=(1 if x>=0 else -1)*((abs(x)+50)//100)
   counter=0;tick+=1000000
  if kind in level:
   changed=level[kind]!=l;level[kind]=l
   if changed and kind=='edge':
    raw+=1;lastedge=t
    if l:rises.append(t)
    else:falls.append(t)
    if enabled:
     delivered+=1
     if l:
      width=min((t-lowstart)&0xffffffff,65535);pw=(width*(256-alpha)+(pw&0xffff)*alpha)//256;counter=(counter+1)%256
     else:lowstart=t
   if changed and kind=='trigger' and l:trig+=1
  if kind!='observe':continue
  x=bytime[t];own=x['own'];ref=x['reference'];label=c['name']+':'+str(t)
  ck((x['delivered_flex_edges'],x['delivered_trigger_edges'],own['raw_edges'],own['last_edge_us'])==(delivered,trig,raw,lastedge),label+' raw/callback counts')
  ck((ref['counter'],ref['ethanol_pct'],ref['fuel_temp_c'],ref['low_pulse_us'],ref['secl'])==(counter,eth,temp,pw,t//1000000),label+' independent reference counter/filter/temperature oracle')
  ck(own['source']==('synthetic_edges' if raw else 'unavailable'),label+' source')
  ck(own['corrections_enabled']==enabled,label+' correction enable')
  if own['valid'] or own['capture_reason']=='ready':
   usable=[q for q in rises if q<=t];ck(len(usable)>=9,label+' full window has real raw cycles');last=usable[-9:];periods=[b-a for a,b in zip(last,last[1:])];widths=[]
   for a,b in zip(last,last[1:]):
    ff=[q for q in falls if a<q<b];ck(len(ff)==1,label+' coherent fall per cycle');widths.append(b-ff[0])
   freq=8000000/sum(periods);width=sum(widths)/8;epct=max(0,min(100,100*(freq-c['low_hz'])/(c['high_hz']-c['low_hz'])));tc=max(-40,min(125,.04125*width-81.25))
   ck((own['window_cycles'],own['window_start_us'],own['sample_us'])==(8,last[0],last[-1]),label+' coherent window timestamps')
   ck(close(own['frequency_hz'],freq) and close(own['low_pulse_us'],width) and close(own['ethanol_pct'],epct) and close(own['fuel_temp_c'],tc),label+' independent completed-cycle oracle')
   ck(close(own['sample_age_ms'],(t-last[-1])/1000) and own['sample_age_ms']<=250,label+' freshness')
  if own['valid']:
   ck(own['reason']=='ready' and own['capture_reason']=='ready' and not own['pending_fault'],label+' valid qualification')
   fuel=100+.5*own['ethanol_pct'] if c['ramp'] else 100;spark=.1*own['ethanol_pct'] if c['ramp'] else 0
   tp=100
   if c['ramp']:
    tx=[-40,0,20,40,80,125];ty=[80,90,95,100,110,120];v=own['fuel_temp_c'];i=next((i for i in range(5) if v<=tx[i+1]),4);tp=ty[i]+(ty[i+1]-ty[i])*(v-tx[i])/(tx[i+1]-tx[i])
   if enabled:ck(own['corrections_valid'] and close(own['fuel_pct'],fuel) and close(own['spark_add_deg'],spark) and close(own['temperature_pct'],tp),label+' independent correction curves')
  if enabled and not own['valid']:ck(not own['corrections_valid'] and all(own[k] is None for k in ['fuel_pct','spark_add_deg','temperature_pct']),label+' invalid corrections inhibited')
  if not enabled:ck(own['corrections_valid'] and own['fuel_pct']==100 and own['spark_add_deg']==0 and own['temperature_pct']==100,label+' disabled neutrality')
  if t>=100000 and ref['rpm']==2000 and ref['sync']==2:
   expected_fuel=100 if not enabled else 0 if t<1000000 else math.floor(100+.5*eth) if c['ramp'] else 100
   expected_spark=0 if not enabled else -40 if t<1000000 else math.floor(.1*eth) if c['ramp'] else 0
   ck(ref['fuel_pct']==expected_fuel and ref['spark_add_deg']==expected_spark,label+' reference curve/cache oracle')
 tail=obs[-1]['own'];name=c['name'];expected_reason={'low-frequency48':'frequency_out_of_range','high-frequency160':'frequency_out_of_range','sensor-fault170':'sensor_fault_frequency','counter-wrap356':'sensor_fault_frequency','short-low-pulse':'low_pulse_width_out_of_range','long-low-pulse':'low_pulse_width_out_of_range','dropout':'stale','flat-high':'stale','flat-low':'acquiring'}
 if name in expected_reason:
  ck(not tail['valid'] and not tail['corrections_valid'] and tail['reason']==expected_reason[name],name+' final invalid class')
  ck(tail['pending_fault']==(name!='flat-low'),name+' pending state')
 elif name=='hidden-width-fault-and-ack':
  b=bytime[1200000]['own'];a=bytime[1200002]['own'];ck(b['capture_reason']=='ready' and b['reason']=='low_pulse_width_out_of_range' and b['pending_fault'] and not b['valid'],name+' hidden fault survives reacquisition')
  ck(len(acks)==1 and acks[0]['time_us']==1200001 and acks[0]['accepted'] and acks[0]['generation']==b['fault_generation'] and a['valid'] and not a['pending_fault'],name+' observed generation ACK')
 else:ck(tail['valid'],name+' final qualified')
 if name=='e0-neutral-startup':
  for t in [160000,500000,999999]:
   r=bytime[t]['reference'];ck((r['rpm'],r['sync'],r['fuel_pct'],r['spark_add_deg'],r['advance_deg'],r['pulse_us'])==(2000,2,0,-40,-30,0),'startup native cache effect')
  r=bytime[1000000]['reference'];o=bytime[160000]['own'];ck((r['fuel_pct'],r['spark_add_deg'],r['advance_deg'],r['pulse_us'])==(100,0,10,5445) and o['valid'] and o['ethanol_pct']==0 and o['fuel_pct']==100 and o['spark_add_deg']==0,'startup neutral recovery')
 if name=='counter-wrap356':ck(obs[-1]['reference']['ethanol_pct']==50 and tail['reason']=='sensor_fault_frequency','356Hz modulo256 alias')
 if name=='custom40-160-span':ck(obs[-1]['reference']['ethanol_pct']==60 and close(tail['ethanol_pct'],50),'40..160Hz calibration difference')
 if name=='e1-reference-deadband':ck(obs[-1]['reference']['ethanol_pct']==0 and abs(tail['ethanol_pct']-1)<.05,'production one-pulse deadband')
 if name=='dropout':ck(bytime[2240000]['own']['valid'] and not bytime[2240001]['own']['valid'] and bytime[2240001]['own']['reason']=='stale','dropout completed-sample boundary')
 return {'snapshots':len(obs),'raw_edges':raw,'trigger_callbacks':trig,'final_own_reason':tail['reason']}

def generated_state():
 result={}
 for root in [S/'.pio',R/'.cache/engine/speeduino-flex-sim/gcov']:
  if root.exists():
   for p in root.rglob('*.gcda'):result[str(p)]=[p.stat().st_mtime_ns,sha(p.read_bytes())]
 return result
original_before={p:sha(Path(p).read_bytes()) for p in manifest['locked_original_input_hashes']};assert original_before==manifest['locked_original_input_hashes'];gcov_before=generated_state();results=[];captures={}
env=os.environ.copy();env.update(GCOV_PREFIX=str(exe.parent/'gcov'),GCOV_PREFIX_STRIP='0',PYTHONDONTWRITEBYTECODE='1')
for row in summary['results']:
 c=row['case'];name=row['name'];body,events=stimulus(c);saved=gzip.decompress((F/'parent-matrix'/(name+'.input.gz')).read_bytes()).decode();ck(body==saved and sha(body.encode())==row['input_sha256'],name+' independent stimulus generation')
 flags=(['--disabled'] if not c['enabled'] else [])+(['--ramp'] if c['ramp'] else [])+['--low',str(c['low_hz']),'--high',str(c['high_hz']),'--reference-filter',str(c['reference_filter'])];ck(flags==row['flags'],name+' flags')
 run=subprocess.run([str(exe),*flags],input=body,text=True,capture_output=True,cwd=F,env=env,timeout=30)
 for ext,value in [('input',body),('stdout',run.stdout),('stderr',run.stderr)]:(OUT/(name+'.'+ext+'.gz')).write_bytes(gzip.compress(value.encode(),mtime=0))
 ck(run.returncode==0 and not run.stderr,name+' clean process');parent_output=gzip.decompress((F/'parent-matrix'/(name+'.stdout.gz')).read_bytes());ck(run.stdout.encode()==parent_output and sha(parent_output)==row['stdout_sha256'],name+' exact independent replay')
 rows=[json.loads(x) for x in run.stdout.splitlines()];result=audit(c,rows,events);captures[name]=(c,rows,events);result.update(name=name,passed=True,input_sha256=sha(body.encode()),output_sha256=sha(run.stdout.encode()),exit_code=run.returncode);results.append(result);print(name+' independently PASS',flush=True)
# Causal and query/phase controls use actual independently replayed data.
snaps=lambda n:{r['time_us']:r for r in captures[n][1] if r['kind']=='snapshot'}
a=snaps('e50-neutral')[3200000];b=snaps('e50-ramp')[3200000];acq=['source','valid','sample_us','frequency_hz','low_pulse_us','ethanol_pct','fuel_temp_c','raw_edges']
ck(all(a['own'][k]==b['own'][k] for k in acq),'same stimulus curve change leaves acquisition identical');ck((a['own']['fuel_pct'],a['own']['spark_add_deg'],b['own']['fuel_pct'],b['own']['spark_add_deg'])==(100,0,125,5),'own causal factors');ck(a['reference']['fuel_pct']==100 and b['reference']['fuel_pct']==125 and a['reference']['advance_deg']==10 and b['reference']['advance_deg']==15 and b['reference']['pulse_us']>a['reference']['pulse_us'],'production causal response')
normal,fine,phase=map(snaps,['e50-ramp','e50-loop-refinement','e50-phase1us'])
for t in [1200000,2200000,3200000]:
 ck(all(normal[t]['own'][k]==fine[t]['own'][k] for k in acq),'query refinement own acquisition')
 ck(all(normal[t]['reference'][k]==fine[t]['reference'][k] for k in ['ethanol_pct','fuel_temp_c','counter','low_pulse_us']),'query refinement production acquisition')
 ck(all(normal[t][who][k]==phase[t][who][k] for who in ['own','reference'] for k in ['ethanol_pct','fuel_temp_c']),'phase1us control')
# Negative controls against this independent checker, not parent pass flags.
mutations=[]
def mutate(label,name,edit):
 c,rows,events=captures[name];rows=copy.deepcopy(rows);edit(rows)
 try:audit(c,rows,events)
 except AuditError as e:mutations.append({'name':label,'rejected':True,'reason':str(e)})
 else:raise AuditError('independent corruption accepted: '+label)
last=lambda rows:next(x for x in reversed(rows) if x['kind']=='snapshot')
mutate('counter_alias_erased','counter-wrap356',lambda rows:last(rows)['reference'].update(ethanol_pct=0))
mutate('span_conversion_erased','custom40-160-span',lambda rows:last(rows)['reference'].update(ethanol_pct=50))
mutate('wrong_fault_class','short-low-pulse',lambda rows:last(rows)['own'].update(reason='stale'))
mutate('wrong_temperature_rounding','e50-ramp',lambda rows:last(rows)['reference'].update(fuel_temp_c=42))
mutate('forged_target_source','e50-ramp',lambda rows:last(rows)['own'].update(source='target_capture'))
mutate('wrong_window_origin','e50-ramp',lambda rows:last(rows)['own'].update(window_start_us=0))
mutate('nonneutral_curves','e50-neutral',lambda rows:last(rows)['own'].update(fuel_pct=99))
mutate('hidden_recovered_fault','hidden-width-fault-and-ack',lambda rows:next(x for x in rows if x.get('time_us')==1200000 and x['kind']=='snapshot')['own'].update(pending_fault=False))
original_after={p:sha(Path(p).read_bytes()) for p in manifest['locked_original_input_hashes']};ck(original_after==original_before,'565 original inputs unchanged');gcov_after=generated_state();ck(gcov_before==gcov_after,'external/parent generated coverage unchanged by owned replays')
result={'scope':'portable_raw_edge_acquisition_and_separate_correction_groundwork_only','verdict':'accepted_in_scope','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'production_cases_reexecuted':len(results),'independent_assertions':checks,'cases':results,'controls':['same-stimulus neutral/ramp acquisition and correction causality','query-cadence refinement','1us phase shift'],'independent_rejected_corruptions':mutations,'binary_sha256':sha(exe.read_bytes()),'binary_owned_copy':str(exe),'GCOV_PREFIX_before_startup':env['GCOV_PREFIX'],'GCOV_PREFIX_STRIP':'0','original565_inputs_before_after_stable':original_before==original_after,'generated_coverage_unchanged_by_these_replays':gcov_before==gcov_after,'generated_coverage_excluded_from_global_unchanged_claim':True,'physical_qualification':False,'full_flex_target_UI_config_hardware_plant_integration':False,'review_script_sha256':sha(Path(__file__).read_bytes())}
(OUT/'independent-execution-review.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps({'cases':len(results),'assertions':checks,'rejected_corruptions':len(mutations),'verdict':result['verdict']}),flush=True)
