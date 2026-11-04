"""Independent complete-edge actuator accounting and cylinder-trim evidence."""
import gzip,hashlib,json,math,pathlib,statistics,sys
BASE=pathlib.Path(__file__).resolve().parent;ROOT=BASE.parents[2]

def replay(d):
 high={};mass=0.;sparks=0;by_cylinder=[0.]*4;last=0;errors=[];flow=300*.745/60*1000
 for us,ch,up,cause in d['edges']:
  if us<last or not 0<=ch<8:errors.append('edge time/order/channel')
  last=us
  if up:
   if ch in high:errors.append('duplicate rise')
   high[ch]=us
  else:
   if ch not in high:errors.append('fall without rise');continue
   start=high.pop(ch)
   if ch<4:
    delivered=flow*max(0,(us-start)*1e-6-.0009);mass+=delivered;by_cylinder[ch]+=delivered
   elif cause=='scheduled':sparks+=1
 ledger=d['summary']['ledger'];delta=mass-ledger['fuel_in_mg']
 if abs(delta)>1e-6:errors.append('complete-edge fuel integral differs from plant')
 if sparks!=d['summary']['sparks']:errors.append('scheduled discharges differ from plant sparks')
 if high or d['summary']['final_outputs_high']:errors.append('termination left high')
 return dict(passed=not errors,errors=errors,edge_integral_fuel_mg=mass,plant_fuel_mg=ledger['fuel_in_mg'],difference_mg=delta,edge_integral_fuel_by_cylinder_mg=by_cylinder,edge_sparks=sparks,plant_sparks=d['summary']['sparks'])

def trims(d,label):
 errors=[];t=d['summary']['secondary_profile']['requested']['tune'];expected_project=[18,12,15,15];expected_reference=[17,13,15,15];expected=expected_project if label in('portable','target')else expected_reference
 controls=[]
 if label in('portable','target'):
  for f in d['trace']:
   if f['time']<4:continue
   c=f['ecu'];dead=c['deadtime_ms'];trimmed=c['cylinders']['proposals']
   for i,o in enumerate(trimmed):
    if o['advance_deg']!=expected[i]:errors.append('project per-cylinder multiply/trim order')
    pct=t['cylinder_trims']['fuel_maps'][i]['cells'][0]
    want=(c['pulse_ms']-dead)*pct/100+dead
    if abs(o['pulse_ms']-want)>1e-8:errors.append('project trims did not precede opening time')
   if c['load_model']['trim_source']!='map' or abs(c['load_model']['trim_load']-f['sensor_map_kpa'])>2e-4:errors.append('trim coordinate differs from primary MAP')
   controls.append(dict(time_us=round(f['time']*1e6),cylinders=trimmed))
 records=[]
 for i in range(4):
  spark=[s for s in d['spark_timing']if s['time_s']>=4 and s['channel']==i+4]
  burns=[r for r in d['combustions']if r['time_s']>=4 and r['cylinder']==i+1]
  high=None;widths=[]
  for us,ch,up,cause in d['edges']:
   if ch!=i:continue
   if up:high=us
   elif high is not None:
    if us>=4000000 and cause=='scheduled':widths.append(us-high)
    high=None
  if not spark or not widths or not burns:errors.append('cylinder physical witness missing')
  records.append(dict(cylinder=i+1,expected_source_order_demand_deg=expected[i],sparks=len(spark),mean_actual_deg=statistics.mean(r['actual_deg']for r in spark),actual_range_deg=[min(r['actual_deg']for r in spark),max(r['actual_deg']for r in spark)],max_abs_difference_from_expected_deg=max(abs(r['actual_deg']-expected[i])for r in spark),mean_delivered_pulse_us=statistics.mean(widths),pulse_range_us=[min(widths),max(widths)],combustions=len(burns),mean_charge_fuel_mg=statistics.mean(r['fuel_mg']for r in burns)))
 means=[r['mean_actual_deg']for r in records]
 if not(means[0]>means[2]>means[1]and means[0]>means[3]>means[1]):errors.append('actual spark angles do not show configured trim direction')
 return dict(passed=not errors,errors=sorted(set(errors)),cylinders=records,source_policy='project trims before secondary multiplication and opening time; reference individual spark trims after composition and fuel trims on full pulse using percentageApprox',angle_acceptance='Actual ranges and differences are reported, with no fitted angle tolerance; per-cylinder ordering and nonvacuous executed edges are asserted.',late_project_control_samples=len(controls))

def main(matrix,out):
 rows=[];trim=[]
 for p in sorted(matrix.glob('*.json.gz')):
  d=json.loads(gzip.decompress(p.read_bytes()));label=d['summary']['label'];case=d['summary']['case'];rows.append(dict(name=p.stem,source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),**replay(d)))
  if case=='trim_multiply':trim.append(dict(label=label,**trims(d,label)))
 report=dict(passed=bool(rows)and all(r['passed']for r in rows)and all(r['passed']for r in trim),matrix=str(matrix.relative_to(ROOT)),scope='Independent integration of every executed injector edge using declared300cc/min,0.745g/cc,900us opening delay; scheduled physical spark count replay; actual late per-cylinder trimmed discharge angles and pulses. No commanded-demand plant shortcut or fitted physical acceptance.',runs=rows,trim_runs=trim,max_abs_fuel_residual_mg=max(abs(r['difference_mg'])for r in rows))
 if out.exists():raise SystemExit('Preserve existing evidence')
 out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(dict(passed=report['passed'],runs=len(rows),max_abs_fuel_residual_mg=report['max_abs_fuel_residual_mg'],failures=[r for r in rows if not r['passed']],trim_runs=trim),indent=2))
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main(ROOT/(sys.argv[1]if len(sys.argv)>1 else'.cache/engine/secondary-plant-matrix-002'),BASE/(sys.argv[2]if len(sys.argv)>2 else'edges-trims001.json'))
