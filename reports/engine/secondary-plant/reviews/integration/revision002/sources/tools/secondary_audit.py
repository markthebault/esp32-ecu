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
   for kind in('fuel','spark'):
    d=frame['ecu']['secondary_tables'][kind];r=tune['secondary_tables'][kind]
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
      require(abs(secondary-cell)<=1.1,kind+' reference represented-axis interpolation')
    if combined!=base:w['nonneutral']+=1
 for kind,w in witness.items():
  r=tune['secondary_tables'][kind];require(w['evaluated']>10,kind+' arithmetic checks were vacuous')
  if r['mode']!='off':require(w['active']>10,kind+' secondary selection was never exercised')
  if r['mode']in('conditional','input')and case not in('zero_fuel','nack','timeout','underfill','mid_read_reset','producer_pause','control_busy'):
   require(w['inactive']>10,kind+' primary selection was never exercised')
  if r['mode']!='off'and case not in('neutral_multiply','neutral_add'):
   require(w['nonneutral']>0,kind+' nonneutral composition was never exercised')
  w['raw_pairs']=[list(p)for p in sorted(w['raw_pairs'])];w['reasons']=sorted(w['reasons'])
 return dict(passed=not errors,errors=sorted(errors),checks=checks,witnesses=witness)

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
