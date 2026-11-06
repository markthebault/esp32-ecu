"""Independent arithmetic/selection witnesses for saved coupled experiments.

This consumes observations and executed edges, never supplies controller inputs.
The plant remains an uncalibrated research model, not an ideal tuning oracle.
"""
import bisect,math

def interpolate(table,rpm,load):
 def interval(axis,value):
  high=max(1,min(len(axis)-1,bisect.bisect_right(axis,value)));low=high-1
  fraction=max(0,min(1,(value-axis[low])/(axis[high]-axis[low])))
  return low,high,fraction
 x0,x1,x=interval(table['rpm'],rpm);y0,y1,y=interval(table['load'],load);v=table['cells']
 return (v[y0*16+x0]*(1-x)+v[y0*16+x1]*x)*(1-y)+(v[y1*16+x0]*(1-x)+v[y1*16+x1]*x)*y

def reference_interpolate(mapping,rpm,native_load):
 """Pinned production QU1.8 semantics, independently evaluated from raw maps.

 Bin search uses nearest raw axis units, positions truncate at1/256, four
 corner weights round separately and the final weighted sum truncates.
 Weights need not sum to256, so ideal interpolation has no fixed1-unit error
 bound. Spark's +40 encoding must remain in the weighted calculation.
 """
 def position(axis,value,factor):
  upper=max(1,min(15,bisect.bisect_left(axis,(value+factor//2)//factor)));lower=upper-1
  offset=max(0,min(256,(value-axis[lower]*factor)*256//((axis[upper]-axis[lower])*factor)))
  return lower,upper,offset
 x0,x1,x=position(mapping['raw_rpm'],rpm,100);y0,y1,y=position(mapping['raw_load'],native_load,2);v=mapping['raw_cells']
 cells=(v[y1*16+x0],v[y1*16+x1],v[y0*16+x0],v[y0*16+x1])
 if len(set(cells))==1:return cells[0]
 weights=tuple((a*b+128)//256 for a,b in((256-x,y),(x,y),(256-x,256-y),(x,256-y)))
 return (sum(c*w for c,w in zip(cells,weights))&65535)//256

def arithmetic_audit(result,case,ours):
 tune=result['summary']['secondary_profile']['requested']['tune'];errors=set();checks=0
 witness={k:dict(evaluated=0,active=0,inactive=0,nonneutral=0,raw_pairs=set(),reasons=set())for k in('fuel','spark')}
 def require(ok,message):
  nonlocal checks
  checks+=1
  if not ok:errors.add(message)
 if ours:
  for h in result['secondary_monitor']:
   c=h['control']
   if not c:continue
   for kind in('fuel','spark'):
    d=c['secondary_tables'][kind];r=tune['secondary_tables'][kind];w=witness[kind]
    require(d['mode']==r['mode']and d['source']==r['source']and d['cells']==r['cells'],kind+' observed rule differs from complete tune')
    bypass=kind=='spark'and d['reason']=='cranking_spark_bypass'
    if r['mode']=='input':
     acq=h['acquisition'];sample=acq['samples'][r['input_channel']]
     require(d['input_raw']==sample['level']and d['input_valid']==sample['valid'],kind+' diagnostic differs from acquired switch sample')
     require(d['input_observed_us']==sample['observed_us']if acq['raw_known']else d['input_observed_us']is None,kind+' acquired timestamp was relabelled')
    if r['mode']=='off':expected=False
    elif bypass:expected=False
    elif r['mode']in('multiply','add'):expected=True
    elif r['mode']=='conditional':expected=d['condition_value']>r['threshold']if d['condition_value']is not None else None
    else:expected=d['input_level']==r['active_high']if d['input_qualified']else None
    if expected is not None:require(d['active']==expected,kind+' selection differs from independent predicate')
    if not d['evaluated']:continue
    w['evaluated']+=1;w['reasons'].add(d['reason'])
    if bypass:continue
    w['active'if d['active']else'inactive']+=1
    base=d['primary_corrected'];raw=base
    if d['active']:
     cell=interpolate(r['map'],c['rpm'],d['coordinate'])
     require(math.isclose(d['secondary'],cell,abs_tol=2e-4),kind+' secondary table lookup')
     raw=base*d['secondary']/100 if r['mode']=='multiply'else base+d['secondary']if r['mode']=='add'else d['secondary']-(d['primary']-base)if kind=='spark'else d['secondary']
    expected=max(0,min(255,raw))if kind=='fuel'else max(-5,min(40,raw))
    require(math.isclose(d['combined'],expected,abs_tol=2e-4),kind+' independent composition/clamp')
    if abs(d['combined']-base)>1e-4:w['nonneutral']+=1
    acq=h['acquisition']
    if d['input_qualified']:w['raw_pairs'].add(tuple(int(v['level'])for v in acq['samples']))
  for frame in result['trace']:
   if not frame['control_observation_completed']:continue
   for kind in('fuel','spark'):
    d=frame['ecu']['secondary_tables'][kind];r=tune['secondary_tables'][kind]
    if d['coordinate']is not None:
     load=frame['sensor_map_kpa']if r['source']=='map'else frame['tps']if r['source']=='tps'else 100*frame['sensor_map_kpa']/result['summary']['load_profile']['requested']['emap_kpa']
     require(math.isclose(d['coordinate'],load,abs_tol=2e-4),kind+' physical sensor/source coordinate')
    if r['mode']=='conditional'and d['condition_value']is not None:
     value=frame['ecu']['rpm']if r['condition']=='rpm'else frame['sensor_map_kpa']if r['condition']=='map_kpa'else frame['tps']
     require(math.isclose(d['condition_value'],value,abs_tol=2e-4),kind+' physical condition value')
    if d['evaluated']and d['active']:
     expected=interpolate(r['map'],frame['ecu']['rpm'],d['coordinate'])
     require(math.isclose(d['secondary'],expected,abs_tol=2e-4),kind+' bilinear source/table lookup')
 else:
  profile=result['summary']['secondary_profile']['reference']
  for frame in result['trace']:
   d=frame['ecu']['secondary_reference']
   if not frame['ecu']['sync']or d['rpm']<=0:continue
   for kind in('fuel','spark'):
    r=tune['secondary_tables'][kind];w=witness[kind];m=profile['maps'][kind];mode=r['mode']
    expected_load=d['map_kpa']if r['source']=='map'else d['tps_raw_half_pct']*2 if r['source']=='tps'else d['map_kpa']*100//d['emap_kpa']if d['emap_kpa']else-1
    require(d['secondary_'+kind+'_load']==expected_load,kind+' reference source/unit coordinate')
    bypass=kind=='spark'and d['loop_rotation']==1
    if mode=='off'or bypass:active=False
    elif mode in('multiply','add'):active=True
    elif mode=='input':active=bool(d['loop_'+kind+'_raw'])==r['active_high']
    else:
     value=d[{'rpm':'rpm','map_kpa':'map_kpa','tps_pct':'tps_raw_half_pct','ethanol_pct':'ethanol_pct'}[r['condition']]]
     threshold=m['represented_threshold']*(2 if r['condition']=='tps_pct'else 1);active=value>threshold
    require(bool(d[kind+'_active'])==active,kind+' reference selection differs from actual-input predicate')
    w['evaluated']+=1
    if bypass:continue
    w['active'if active else'inactive']+=1;w['raw_pairs'].add((d['loop_fuel_raw'],d['loop_spark_raw']))
    base=d['primary_ve'if kind=='fuel'else'primary_advance'];combined=d['combined_ve'if kind=='fuel'else'combined_advance'];expected=base
    if active:
     load=d['secondary_'+kind+'_load']/(4 if r['source']=='tps'else 1)
     table=dict(rpm=m['represented_rpm'],load=m['represented_load'],cells=m['represented_cells']);cell=interpolate(table,d['rpm'],load)
     if len(set(m['represented_cells']))==1:
      cell=m['represented_cells'][0]
      if mode=='multiply':expected=math.floor(abs(base*cell)/100+.5)*(1 if base>=0 else-1)
      elif mode=='add':expected=base+cell
      else:expected=cell
      expected=max(0,min(255,expected))if kind=='fuel'else max(-128,min(127,expected))
      require(combined==expected,kind+' reference independent integer composition')
     else:
      secondary=d['secondary_ve']if kind=='fuel'else d['secondary_advance_diagnostic']+127 if mode=='multiply'else d['secondary_advance_diagnostic']
      encoded=reference_interpolate(m,d['rpm'],d['secondary_'+kind+'_load'])
      require(secondary==encoded-(40 if kind=='spark'else 0),kind+' reference integer represented-axis interpolation')
    if combined!=base:w['nonneutral']+=1
 for kind,w in witness.items():
  r=tune['secondary_tables'][kind];require(w['evaluated']>10,kind+' arithmetic checks were vacuous')
  quantization_counterexample=case=='conditional_near_quantization'and not ours
  if quantization_counterexample:
   require(w['active']==0 and w['nonneutral']==0,kind+' quantization counterexample unexpectedly activated')
   require(any(f['tps']>r['threshold']and f['ecu']['secondary_reference']['tps_raw_half_pct']<=result['summary']['secondary_profile']['reference']['maps'][kind]['represented_threshold']*2 for f in result['trace']),kind+' quantized condition divergence was not exercised')
  elif r['mode']!='off':require(w['active']>10,kind+' secondary selection was never exercised')
  if r['mode']in('conditional','input')and case not in('zero_fuel','nack','timeout','underfill','mid_read_reset','producer_pause','control_busy'):
   require(w['inactive']>10,kind+' primary selection was never exercised')
  if r['mode']!='off'and case not in('neutral_multiply','neutral_add')and not quantization_counterexample:
   require(w['nonneutral']>0,kind+' nonneutral composition was never exercised')
  if case=='conditional_tps_plateau':
   equal=[f for f in result['trace']if(f['ecu']['secondary_tables'][kind]['condition_value']==r['threshold']if ours else f['ecu']['secondary_reference']['tps_raw_half_pct']==r['threshold']*2)]
   require(len(equal)>10,kind+' exact threshold plateau was not exercised')
   require(all(not(f['ecu']['secondary_tables'][kind]['active']if ours else f['ecu']['secondary_reference'][kind+'_active'])for f in equal),kind+' equality activated a strict threshold')
  w['raw_pairs']=[list(p)for p in sorted(w['raw_pairs'])];w['reasons']=sorted(w['reasons'])
 return dict(passed=not errors,errors=sorted(errors),checks=checks,witnesses=witness)

def delivery_audit(result,case):
 """Require actual delivery, exact consumption counts and post-ACK fresh reads."""
 history=result['secondary_monitor'];errors=set();acks=[];witnesses=[]
 def require(ok,message):
  if not ok:errors.add(message)
 for index,h in enumerate(history):
  a=h['acquisition']
  if index:
   prev=history[index-1]
   require(int(a['consumed_faults'])==int(prev['acquisition']['consumed_faults'])+int(prev['fault_acknowledged']),'consumed fault counter differs from exact ACK history')
  if h['fault_acknowledged']:
   require(a['fault_pending']and not a['ready']and h['control_completed']and h['control']and h['control']['faults']&4,'ACK lacked completed invalid control observation')
   require(a['fault_id']not in acks,'same fault ID acknowledged twice');acks.append(a['fault_id'])
   later=history[index+1:];ready=next((r for r in later if r['acquisition']['ready']),None)
   require(ready is not None,'acknowledged fault never reacquired a valid sample')
   if ready:
    require(int(ready['acquisition']['observed_us'])>h['control_attempt_us'],'ready sample predates fault ACK')
    for kind,r in result['summary']['secondary_profile']['requested']['tune']['secondary_tables'].items():
     if r['mode']!='input':continue
     qualified=next((q for q in later if q['control']and q['control']['secondary_tables'][kind]['input_qualified']),None)
     require(qualified is not None,kind+' never requalified after ACK')
     if qualified:require(int(qualified['control']['secondary_tables'][kind]['input_observed_us'])-int(ready['acquisition']['observed_us'])>=round(r['debounce_ms']*1000),kind+' skipped post-fault source-time debounce')
    witnesses.append(dict(fault_id=a['fault_id'],ack_us=h['control_attempt_us'],first_ready_us=ready['control_attempt_us'],first_source_us=ready['acquisition']['observed_us']))
 if case in('nack','timeout','underfill','mid_read_reset','producer_pause','control_busy'):require(bool(acks),'recoverable fault was never acknowledged')
 return dict(passed=not errors,errors=sorted(errors),acknowledged_fault_ids=acks,recovery=witnesses)

def causal_audit(results):
 """Within-controller controls, avoiding an assumption of cross-ECU equality."""
 rows=[]
 for label,cases in results.items():
  if 'off'not in cases:continue
  base=cases['off']
  for case in('off_metadata','neutral_multiply','neutral_add','multiply','add','fuel_only','spark_only'):
   if case not in cases:continue
   d=cases[case];neutral=case in('off_metadata','neutral_multiply','neutral_add')
   equal=d['edges']==base['edges']and d['summary']['ledger']==base['summary']['ledger']and d['combustions']==base['combustions']
   passed=equal if neutral else d['edges']!=base['edges']and d['summary']['ledger']['combustion_shaft_j']!=base['summary']['ledger']['combustion_shaft_j']
   rows.append(dict(label=label,case=case,expected='identical executed edges, ledger and combustions'if neutral else'changed executed edges and shaft work',equal=equal,passed=passed))
 return dict(passed=all(r['passed']for r in rows),checks=rows)
