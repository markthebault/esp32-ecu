"""Validate the separate exact oracle against actual production-loop outputs."""
import hashlib,json,pathlib,sys
BASE=pathlib.Path(__file__).resolve().parent;ROOT=BASE.parents[2];sys.path.insert(0,str(ROOT/'tools'))
from compare_engine_controllers import benchmark_tune
from speeduino_runtime import SpeeduinoRuntime
from secondary_audit import reference_interpolate
SOURCES=('map','tps','imap_emap')

def tune(fuel,spark):
 t=benchmark_tune();t['transient_enrichment']['mode']='off';t['load_model']['aux_role']='emap'
 for kind,source in(('fuel',fuel),('spark',spark)):
  r=t['secondary_tables'][kind];r.update(mode='multiply',cells='multiplier',source=source,axis={'map':'map_kpa','tps':'tps_pct','imap_emap':'imap_emap_pct'}[source])
  r['map']['load']=[i*10 for i in range(16)]if source=='map'else [i*20 for i in range(16)]if source=='imap_emap'else[0,2,4,6,8,10,12,16,20,24,30,40,50,65,80,100]
  r['map']['cells']=[101+(row*13+col*17)%31 if kind=='fuel'else 121+(row*11+col*7)%34 for row in range(16)for col in range(16)]
 return t

def main(out):
 rows=[];errors=[];checks=0
 for bits in(32,16):
  for i,source in enumerate(SOURCES):
   other=SOURCES[(i+1)%3];t=tune(source,other);r=SpeeduinoRuntime(timer_bits=bits,secondary_channels=(0,1));samples=[];tooth=0
   try:
    r.configure_load(t);r.configure_secondary(t)
    for index,(map_kpa,tps_pct,rpm,emap)in enumerate([(25,5,1000,125),(44,12,1176,125),(63,23,1250,110),(88,48,2000,130),(105,77,1500,150)]):
     begin=r.now;end=begin+250000;period=round(1e6/rpm)
     r.pressures(emap,100);r.sensors(dict(map_kpa=map_kpa,tps_pct=tps_pct,clt_c=85,iat_c=25,battery_v=14,**{'lambda':1}))
     events=[(u,0)for u in range(begin+250,end+1,250)]
     for u in range(begin+period,end+1,period):
      tooth+=1
      if tooth%60<58:events.append((u,1))
     next_observe=begin+150000
     for u,is_tooth in sorted(events):
      r.advance(u,tooth=bool(is_tooth))
      if u<next_observe:continue
      next_observe=u+10000;s=r.secondary_status()
      if not(s['fuel_active']and s['spark_active']):continue
      raw={k:reference_interpolate(r.secondary_profile['maps'][k],s['rpm'],s['secondary_'+k+'_load'])for k in('fuel','spark')}
      expected_load={k:s['map_kpa']if t['secondary_tables'][k]['source']=='map'else s['tps_raw_half_pct']*2 if t['secondary_tables'][k]['source']=='tps'else s['map_kpa']*100//s['emap_kpa']for k in('fuel','spark')}
      observed=dict(fuel=s['secondary_ve'],spark=s['secondary_advance_diagnostic']+127)
      expected=dict(fuel=raw['fuel'],spark=max(0,min(255,raw['spark']-40)))
      for k in('fuel','spark'):
       checks+=1
       if s['secondary_'+k+'_load']!=expected_load[k]:errors.append('source load units')
       if observed[k]!=expected[k]:errors.append('exact raw interpolation: '+str((bits,source,index,k,s,raw)))
       factor=100 if k=='rpm'else 2
       if (s['secondary_'+k+'_load']+1)//2>255:errors.append('unsupported raw lookup domain')
      samples.append(dict(status=s,expected_raw_cells=raw,observed=observed,expected=expected))
    rows.append(dict(bits=bits,fuel_source=source,spark_source=other,samples=samples,profile=r.secondary_profile))
   finally:r.close()
 report=dict(passed=not errors and checks>0,checks=checks,errors=errors,scope='Strict comparison of the postprocessing raw-table oracle to independently configured nonconstant fuel/spark maps in real non-UNIT_TEST production setup/loop across MAP/TPS/ratio, native32/native16, changing sensor values and fixed-speed diagnostic segments. Not coupled-engine evidence. Raw rounded load coordinates <=255.',runs=rows,source_bindings={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in('tools/secondary_audit.py','tools/speeduino_runtime.py','tools/speeduino_sim.cpp')})
 if out.exists():raise SystemExit('Preserve earlier evidence')
 out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=report['passed'],checks=checks,errors=errors,samples=sum(len(r['samples'])for r in rows)),indent=2))
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main(BASE/(sys.argv[1]if len(sys.argv)>1 else'reference-interpolation001.json'))
