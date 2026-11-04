"""Independent negative controls for the frozen saved-result auditor."""
import copy,gzip,hashlib,json,pathlib,sys
BASE=pathlib.Path(__file__).resolve().parent;ROOT=BASE.parents[2];sys.path.insert(0,str(ROOT/'tools'))
from run_secondary_scenarios import audit
from secondary_audit import interpolate
matrix=ROOT/(sys.argv[2]if len(sys.argv)>2 else'.cache/engine/secondary-plant-matrix-003')
source=matrix/'portable-ratio_mixed-250.json.gz'
original=json.loads(gzip.decompress(source.read_bytes()))
rows=[]
for mutation in('consistent_wrong_ratio_coordinate','erased_acknowledgments'):
 if mutation=='erased_acknowledgments':
  f=matrix/'portable-nack-250.json.gz'
  d=json.loads(gzip.decompress(f.read_bytes()))
  for h in d['secondary_monitor']:h['fault_acknowledged']=False
  a=audit(d,'nack',True)
 else:
  d=copy.deepcopy(original);r=d['summary']['secondary_profile']['requested']['tune']['secondary_tables']['fuel']
  def change(o,rpm):
   if not(o['evaluated']and o['active']):return
   o['coordinate']+=75
   o['secondary']=interpolate(r['map'],rpm,o['coordinate'])
   o['combined']=min(255,max(0,o['primary_corrected']*o['secondary']/100))
  for h in d['secondary_monitor']:
   if h['control']:change(h['control']['secondary_tables']['fuel'],h['control']['rpm'])
  for f in d['trace']:change(f['ecu']['secondary_tables']['fuel'],f['ecu']['rpm'])
  a=audit(d,'ratio_mixed',True)
 rows.append(dict(mutation=mutation,accepted=a['passed'],errors=a['errors'],arithmetic=a['arithmetic']))
out=BASE/(sys.argv[1]if len(sys.argv)>1 else'audit-mutations001.json')
if out.exists():raise SystemExit('Preserve existing evidence')
report=dict(scope='Deliberate saved-result corruption to measure acceptance sensitivity. An accepted mutation is an auditor gap, not proof of a firmware defect.',checks=rows,source_file=str(source.relative_to(ROOT)),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),auditor_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in('tools/run_secondary_scenarios.py','tools/secondary_audit.py')})
out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps([dict(mutation=r['mutation'],accepted=r['accepted'],errors=r['errors'])for r in rows],indent=2))
