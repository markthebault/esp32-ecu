"""Independent domain bounds and causal selection witnesses for final fixtures."""
import gzip,hashlib,json,pathlib,sys
BASE=pathlib.Path(__file__).resolve().parent;ROOT=BASE.parents[2]

def main(matrix,out):
 errors=[];domains=[];witness=[];artifacts={}
 def require(ok,msg):
  if not ok:errors.append(msg)
 for p in sorted(matrix.glob('*-250.json.gz')):
  d=json.loads(gzip.decompress(p.read_bytes()));label=d['summary']['label'];case=d['summary']['case'];t=d['summary']['secondary_profile']['requested']['tune'];ours=label in('portable','target');artifacts[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
  if not ours:
   values=[s['ecu']['secondary_reference']for s in d['trace']]
   maxrpm=max((s['rpm']+50)//100 for s in values);maxload=max((s['secondary_'+kind+'_load']+1)//2 for s in values for kind in('fuel','spark'))
   require(maxrpm<=255 and maxload<=255,label+' '+case+' exceeds reviewed uint8 native bin-search domain')
   domains.append(dict(label=label,case=case,max_rounded_rpm_axis_coordinate=maxrpm,max_rounded_load_axis_coordinate=maxload))
  if case=='input'and ours:
   pairs=sorted({(int(h['acquisition']['gpio'])&1,(int(h['acquisition']['gpio'])>>1)&1)for h in d['secondary_monitor']if h['acquisition']['ready']})
   require(pairs==[(0,0),(0,1),(1,0),(1,1)],label+' default Input omitted a physical GPIO pair');witness.append(dict(label=label,case=case,physical_gpio_pairs=pairs))
  if case=='input_shared_debounce'and ours:
   history=[h for h in d['secondary_monitor']if h['control']]
   rise={k:next(h['control_attempt_us']for h in history if h['control_attempt_us']>=3000000 and h['control']['secondary_tables'][k]['active'])for k in('fuel','spark')}
   fall={k:next(h['control_attempt_us']for h in history if h['control_attempt_us']>=4000000 and not h['control']['secondary_tables'][k]['active'])for k in('fuel','spark')}
   require(t['secondary_tables']['fuel']['input_channel']==t['secondary_tables']['spark']['input_channel']and t['secondary_tables']['fuel']['debounce_ms']<t['secondary_tables']['spark']['debounce_ms'],label+' shared debounce fixture is not independent')
   require(rise['fuel']<rise['spark']and fall['fuel']<fall['spark'],label+' shared-channel unequal debounce has no distinct rising/falling selections')
   witness.append(dict(label=label,case=case,first_rise_us=rise,first_fall_us=fall))
  if case=='input_opposite':
   if ours:
    states=[h['control']['secondary_tables']for h in d['secondary_monitor']if h['control']and h['control']['state']=='running'and h['control_attempt_us']>500000]
    held=[s for s in states if all(s[k]['input_qualified']and not s[k]['pending']for k in('fuel','spark'))]
    require(bool(held),label+' opposite polarity had no qualified held state')
    require(all(s[k]['active']==(s[k]['input_raw']==t['secondary_tables'][k]['active_high'])for s in held for k in('fuel','spark')),label+' opposite-polarity output disagrees with independent acquired raw level')
    saw=any(not s['fuel']['active']and s['spark']['active']for s in held)
   else:
    states=[f['ecu']['secondary_reference']for f in d['trace']if f['time']>.5 and f['ecu']['secondary_reference']['loop_rotation']==2]
    saw=any(not s['fuel_active']and s['spark_active']for s in states)
    require(all(bool(s[k+'_active'])==(bool(s['loop_'+k+'_raw'])==t['secondary_tables'][k]['active_high'])for s in states for k in('fuel','spark')),label+' opposite polarity reference predicate')
   require(saw,label+' opposite-polarity independent activation witness absent');witness.append(dict(label=label,case=case,distinct_selection_witness=saw))
  if case=='conditional_tps_plateau':
   sections=[]
   for name,lo,hi,expected in(('upward equality',3.1,3.4,False),('above',3.6,4.1,True),('downward equality',4.4,4.9,False)):
    f=[f for f in d['trace']if lo<=f['time']<=hi];require(len(f)>10,label+' '+name+' plateau witness absent')
    for frame in f:
     for k in('fuel','spark'):
      if ours:
       s=frame['ecu']['secondary_tables'][k];value=s['condition_value'];active=s['active'];threshold=t['secondary_tables'][k]['threshold']
      else:
       s=frame['ecu']['secondary_reference'];value=s['tps_raw_half_pct'];active=bool(s[k+'_active']);threshold=t['secondary_tables'][k]['threshold']*2
      require(active==expected,label+' '+name+' strict selection')
      if name!='above':require(value==threshold,label+' '+name+' was not exactly represented equality')
    sections.append(dict(name=name,count=len(f),active=expected))
   witness.append(dict(label=label,case=case,sections=sections))
 report=dict(passed=not errors,matrix=str(matrix.relative_to(ROOT)),runs=len(artifacts),errors=sorted(set(errors)),scope='Independent actual native lookup-domain bound, all raw GPIO pairs, shared-channel unequal-debounce transition chronology, opposite polarity, and exact-threshold equality before/after activation. Domain bound explicitly excludes wrapped uint8 lookup coordinates beyond255.',reference_domains=domains,selection_witnesses=witness,artifacts=artifacts)
 if out.exists():raise SystemExit('Preserve existing evidence')
 out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=report['passed'],runs=len(artifacts),errors=report['errors'],selection_witnesses=witness,max_raw_lookup=max(r['max_rounded_load_axis_coordinate']for r in domains)),indent=2))
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main(ROOT/(sys.argv[1]if len(sys.argv)>1 else'.cache/engine/secondary-plant-matrix-003'),BASE/(sys.argv[2]if len(sys.argv)>2 else'domains-selection001.json'))
