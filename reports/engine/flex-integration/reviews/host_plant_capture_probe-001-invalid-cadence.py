#!/usr/bin/env python3
"""Audit frozen saved captures; replay four bounded native-only controls."""
import csv,gzip,hashlib,io,json,sys
from pathlib import Path
F=Path(sys.argv[1]).resolve();P=Path(sys.argv[2]).resolve();O=Path(__file__).resolve().parent
sys.path.insert(0,str(F/'tools'))
from engine_sil import Simulation
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
index=json.loads((P/'index.json').read_text());checks=0
def require(v,label):
 global checks
 checks+=1
 if not v:raise AssertionError(label)
cases={q['name']:q for q in index['cases']};require(len(cases)==27,'27 unique captures')
required={(s,c)for s in ('batch_wasted_4cyl','semi_sequential_4cyl','sequential_4cyl')for c in ('off','neutral','neutral50','neutral150','corrected','filtered','zero','missing','dropout')}
require({(q['strategy'],q['case'])for q in cases.values()}==required,'complete declared case set')
sources={};source_differences=[]
for rel,want in index['source_sha256'].items():
 actual=H(F/rel);sources[rel]=dict(capture=want,review_freeze=actual)
 if actual!=want:source_differences.append(rel)
captures={};artifacts={};columns=set();rows=0
for name,c in cases.items():
 q=P/(name+'.json.gz');artifacts[q.name]=H(q);raw=gzip.decompress(q.read_bytes());r=json.loads(raw);captures[name]=r
 require(r['summary']==c['summary'],name+' summary bound')
 require(not r['summary']['physical_outputs_enabled'] and r['summary']['final_outputs_high']==0 and r['summary']['executor_stopped'],name+' virtual inhibition and stop')
 require(all(not row['physical_outputs_enabled'] for row in r['trace']),name+' every row inhibited')
 require(len(r['trace'])==200 and [round(row['time'],8)for row in r['trace']]==[round((n+1)*.02,8)for n in range(200)],name+' independent trace cadence')
 for row in r['trace']:
  f=row['flex_fuel'];s=row['engine_sample'];sf=s['flex_fuel'];now=round(row['time']*1e6)
  require(f['configuration_revision']==c['tune']['revision'] and sf['configuration_revision']==c['tune']['revision'],name+' producer revision')
  require(f['sample_us']==sf['sample_us'] and f['last_edge_us']==sf['last_edge_us'] and f['raw_edges']==sf['raw_edges'],name+' same completed observation')
  if f['raw_capture_qualified']:
   require(f['source_code']==2 and int(f['window_start_us'])<int(f['sample_us'])<=int(f['last_edge_us'])<=now,name+' coherent raw provenance/time')
   require(abs(f['sample_age_ms']-(now-int(f['sample_us']))/1000)<1e-6,name+' original sample age')
  if c['case']!='off' and not f['control_ok']:
   require(row['fuel_cut'] and row['spark_cut'] and row['pulse_ms']==0,name+' invalid required cut')
 case=c['case']
 if case=='missing':require(r['summary']['fuel_mg']==0 and all(not row['flex_fuel']['value_qualified'] for row in r['trace']),name+' never fabricated missing value')
 if case=='zero':require(r['summary']['fuel_mg']==0 and all(row['pulse_ms']==0 for row in r['trace']) and any(row['flex_fuel']['control_ok'] and not row['spark_cut'] for row in r['trace']),name+' valid zero only fuel cut')
 if case=='dropout':
  tail=[row for row in r['trace'] if row['time']>=2.3]
  require(all(not row['flex_fuel']['control_ok'] and row['fuel_cut'] and row['spark_cut'] and row['pulse_ms']==0 for row in tail),name+' dropout cut')
  require(max(int(row['flex_fuel']['last_edge_us'])for row in r['trace'])<2000000 and r['summary']['flex_stimulus']['raw_edges']==400,name+' no false edge after cutoff')
 if case in ('corrected','filtered'):
  qualified=[row['flex_fuel']for row in r['trace']if row['flex_fuel']['raw_capture_qualified']]
  require(qualified and all((x['fuel_pct'],x['temperature_pct'],x['spark_add_deg'])==(150,80,5)for x in qualified),name+' nonneutral factors')
 if case.startswith('neutral'):
  want=0 if case=='neutral50' else 100 if case=='neutral150' else 50
  require(abs(r['final']['flex_fuel']['ethanol_pct']-want)<.011,name+' calibrated neutral ethanol')
 m=P/(name+'.msl');artifacts[m.name]=H(m);table=list(csv.reader(io.StringIO(m.read_text()),delimiter='\t'))
 require(len(table)==204 and len(set(map(len,table[2:])))==1,name+' rectangular retained MSL')
 columns.add(len(table[2]));rows+=len(r['trace'])
for strategy in ('batch_wasted_4cyl','semi_sequential_4cyl','sequential_4cyl'):
 a=captures[strategy+'-off'];b=captures[strategy+'-neutral']
 require(a['edges']==b['edges'],'exact neutral virtual edges '+strategy)
 require(a['trigger_edges']==b['trigger_edges'] and a['cam_edges']==b['cam_edges'],'exact neutral plant crank/cam '+strategy)
 require(a['summary']['fuel_mg']==b['summary']['fuel_mg'] and a['summary']['final_rpm']==b['summary']['final_rpm'],'exact neutral fuel/RPM '+strategy)
replays={}
for name in ('batch_wasted_4cyl-off','batch_wasted_4cyl-neutral','sequential_4cyl-corrected','semi_sequential_4cyl-dropout'):
 c=cases[name];req=c['request'];actual=Simulation(c['tune'],req['scenario'],req['duration_s'],req['seed'],req['flex_stimulus']).run();want=captures[name]
 require(actual==want,'owned replay identical complete decoded capture '+name)
 replays[name]={'identical':True,'trace_rows':len(actual['trace']),'edges':len(actual['edges'])}
print(json.dumps({'passed':True,'checks':checks,'cases':len(cases),'trace_rows':rows,'msl_columns':sorted(columns),'source_differences':source_differences,'source_hashes':sources,'artifacts':artifacts,'replays':replays,'scope':'Owned shared native engine only; saved 27 fixed-gasoline plant captures and four independently replayed controls. No Speeduino production executable, physical target, or ethanol combustion model.'},indent=2))
