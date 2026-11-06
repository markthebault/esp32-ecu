"""Independent saved-history ACK, recovery, source-age and cut review."""
import gzip,hashlib,json,pathlib,sys
BASE=pathlib.Path(__file__).resolve().parent;ROOT=BASE.parents[2]
CASES=('nack','timeout','underfill','mid_read_reset','producer_pause','control_busy')
def review(d):
 errors=[];checks=0;acks=[];ready_after=[];qualified_after=[];h=d['secondary_monitor'];count=0;pending_ids=set();consumed_ids=set()
 def require(ok,message):
  nonlocal checks
  checks+=1
  if not ok:errors.append(message)
 high=set();cursor=0
 for row in h:
  s=row['acquisition'];now=row['control_attempt_us'];control=row['control'];fid=int(s['fault_id'])
  require(int(s['consumed_faults'])==count,'consumed-fault counter differs from exact ACK count')
  if s['fault_pending']:
   pending_ids.add(fid);require(fid>0 and not s['ready'],'pending fault falsely became ready')
  if row['fault_acknowledged']:
   require(row['control_completed'] and control is not None and bool(control['faults']&4) and s['fault_pending'] and not s['ready'],'ACK without completed inhibited observation')
   require(fid not in consumed_ids,'duplicate ACK for exact fault ID')
   consumed_ids.add(fid);count+=1;acks.append(dict(time_us=now,fault_id=fid,reads=int(s['reads']),observed_us=int(s['observed_us'])))
  if s['ready']:
   require(int(s['read_completed_us'])<=now and int(s['observed_us'])<=int(s['read_completed_us']),'future or unfinished read published')
   for ack in acks:
    if now>ack['time_us']:
     require(int(s['observed_us'])>ack['time_us'] and int(s['reads'])>ack['reads'],'readiness recovered without new post-ACK guarded read')
  if control:
   while cursor<row['edge_cursor']:
    us,ch,up,cause=d['edges'][cursor];cursor+=1
    if up:high.add(ch)
    else:high.discard(ch)
   if control['faults']:require(not high,'completed fault observation left active GPIO')
   if acks and now>acks[-1]['time_us'] and s['ready']:
    if not ready_after or ready_after[-1]['fault_id']!=acks[-1]['fault_id']:ready_after.append(dict(fault_id=acks[-1]['fault_id'],observed_us=int(s['observed_us']),at_us=now))
    for kind in ('fuel','spark'):
     rule=d['summary']['secondary_profile']['requested']['tune']['secondary_tables'][kind]
     o=control['secondary_tables'][kind]
     if rule['mode']=='input'and o['input_qualified']:
      first=next(r for r in ready_after if r['fault_id']==acks[-1]['fault_id'])
      require(int(o['input_observed_us'])-first['observed_us']>=rule['debounce_ms']*1000,'postfault qualification did not span declared debounce in source time')
      if not any(q['fault_id']==acks[-1]['fault_id']and q['kind']==kind for q in qualified_after):qualified_after.append(dict(kind=kind,fault_id=acks[-1]['fault_id'],at_us=now,observed_us=int(o['input_observed_us']),first_healthy_source_us=first['observed_us']))
 require(bool(acks),'fault ACK witness is vacuous')
 require(pending_ids<=consumed_ids,'an observed pending fault was never ACKed')
 require(bool(ready_after),'no new healthy guarded read after ACK')
 case=d['summary']['case']
 if case!='control_busy':require(not h[-1]['control']['faults'] and len(qualified_after)>=2,'recoverable input fault did not recover both rules by horizon')
 if case=='control_busy':
  good_held=[r for r in h if not r['control_completed']and r['acquisition']['fault_pending']and int(r['acquisition']['reads'])>acks[0]['reads']-1]
  # ACK can occur after several good recovery reads. Compare to the count at the first pending fault.
  first=next(r for r in h if r['acquisition']['fault_pending']);reads_at_failure=int(first['acquisition']['reads'])
  good_held=[r for r in h if not r['control_completed']and r['acquisition']['fault_pending']and int(r['acquisition']['reads'])>reads_at_failure]
  require(bool(good_held)and all(not r['acquisition']['ready']and not r['fault_acknowledged']for r in good_held),'busy observer did not retain fault through actual successful recovery reads')
 if case=='producer_pause':
  window=next(f for f in d['summary']['secondary_profile']['requested']['stimulus']['faults']if f['kind']=='producer_pause')
  stale=[r for r in h if window['begin_us']<=r['control_attempt_us']<window['end_us'] and r['control']and r['control']['secondary_tables']['fuel']['reason']=='input_stale']
  require(bool(stale)and all(r['control']['secondary_tables']['fuel']['input_age_ms']>20 and r['control']['faults']&4 and not r['acquisition']['fault_pending']for r in stale),'core did not independently reject stale source before producer resume')
 return dict(passed=not errors,checks=checks,errors=sorted(set(errors)),fault_ids=sorted(pending_ids),acks=acks,first_ready_after_ack=ready_after,first_qualified_after_ack=qualified_after)
def main(matrix,out):
 rows=[]
 for label in('portable','target'):
  for case in CASES:
   p=matrix/(label+'-'+case+'-250.json.gz')
   if not p.exists():continue
   d=json.loads(gzip.decompress(p.read_bytes()));rows.append(dict(name=label+'-'+case,source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),**review(d)))
 report=dict(passed=bool(rows)and all(r['passed']for r in rows),matrix=str(matrix.relative_to(ROOT)),scope='Independent exact fault-ID ACK/counter liveness, no hidden good-read recovery, source freshness/debounce chronology, and all-low after completed fault observations. Saved coupled trace review, not physical timing validation.',runs=rows,total_checks=sum(r['checks']for r in rows))
 if out.exists():raise SystemExit('Preserve existing evidence')
 out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main(ROOT/(sys.argv[1]if len(sys.argv)>1 else'.cache/engine/secondary-plant-matrix-002'),BASE/(sys.argv[2]if len(sys.argv)>2 else'fault-history001.json'))
