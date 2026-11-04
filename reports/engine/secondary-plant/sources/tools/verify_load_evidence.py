#!/usr/bin/env python3
"""Verify immutable load evidence, independent source binding and optional index."""
import argparse,csv,gzip,hashlib,io,json,math,struct,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/engine/load-model'
sha=lambda b:hashlib.sha256(b).hexdigest()

def verify(live=False,index=False):
 manifest=json.loads((OUT/'artifact-manifest.json').read_text())['files_sha256'];assert set(manifest)=={str(p.relative_to(OUT)) for p in OUT.rglob('*') if p.is_file() and p!=OUT/'artifact-manifest.json'},'Unlisted evidence file'
 for name,h in manifest.items():assert not Path(name).is_absolute() and '..' not in Path(name).parts and sha((OUT/name).read_bytes())==h,'Artifact differs: '+name
 summary=json.loads((OUT/'validation-summary.json').read_text());assert summary['passed'];sources=summary['source_sha256']
 for name,h in sources.items():
  assert sha((OUT/('source-metadata/root.gitattributes' if name=='.gitattributes' else 'sources/'+name)).read_bytes())==h,'Source snapshot differs: '+name
  if live:assert sha((ROOT/name).read_bytes())==h,'Live source differs: '+name
 initial=json.loads((OUT/'reviews/simulator/initial-source-snapshot.json').read_text())['files'];closure=json.loads((OUT/'reviews/simulator/closure-source-snapshot.json').read_text());binding=json.loads((OUT/'reviews/simulator/executed-source-binding.json').read_text())['source_sha256']
 reviewed={r['path']:r['sha256'] for r in initial};reviewed.update({r['path']:r['sha256'] for r in closure});reviewed={p:h for p,h in reviewed.items() if not Path(p).name.startswith('test_')}
 assert binding==reviewed
 for name,h in binding.items():assert sources[name]==h,'Execution source differs from independent reviewed bytes: '+name
 matrix=json.loads((OUT/'matrix/summary.json').read_text());assert matrix['passed'] and len(matrix['runs'])==64 and len(matrix['refinements'])==8 and not matrix['failures'];assert all(r['passed'] and max(r['relative_differences'].values())<r['tolerance'] for r in matrix['refinements'])
 calibration=json.loads((OUT/'validation/calibration-alpha.json').read_text());assert sha((OUT/'validation/calibration-alpha.json').read_bytes())==matrix['calibration_sha256'];assert len(calibration['points'])==256
 assert calibration['provenance']['calibration_source_sha256']==sources['tools/calibrate_load_benchmark.py']
 assert sum(p['status']=='steady' for p in calibration['points'])==244
 for p in calibration['points']:
  value=p['air_kg_s']/(p['observed_rpm']/120*4)*1e6/(100000*.0005/(287.05*298.15)*1e6)*100
  assert abs(value-p['coefficient_pct'])<=.00000051
  if p['status']=='steady':assert p['observed_rpm']==p['rpm'] and abs(p['map_dot_kpa_s'])<.001 and abs(p['air_kg_s']-p['inlet_air_kg_s'])<1e-8
 def bracket(axis,x):
  if x<=axis[0]:return [0]
  if x>=axis[-1]:return [len(axis)-1]
  for i in range(1,len(axis)):
   if x==axis[i]:return [i]
   if x<axis[i]:return [i-1,i]
 for row in matrix['runs']:
  path=OUT/'matrix'/row['trace_file'];assert sha(path.read_bytes())==row['trace_sha256'];result=json.loads(gzip.decompress(path.read_bytes()));assert row['audit']['passed'] and result['summary']['audit']['passed'] and result['summary']['final_outputs_high']==0
  if row['case'].startswith('alpha') and row['case']!='alpha_uncalibrated' and row['label'] in ('portable','target'):
   for r in result['trace']:
    d=r['ecu']['load_model']
    if not d['flags']&1 or d['fuel_load'] is None:continue
    for y in bracket(calibration['tps_pct'],d['fuel_load']):
     for x in bracket(calibration['rpm'],r['ecu']['rpm']):assert calibration['points'][y*16+x]['status']=='steady','Trajectory used an unqualified calibration corner'
 legacy=json.loads((OUT/'legacy/summary.json').read_text());assert legacy['passed'] and len(legacy['cases'])==8
 for row in legacy['cases']:
  assert row['passed'] and all(row['checks'].values());assert sha((ROOT/row['baseline_path']).read_bytes())==row['baseline_sha256'],'Historical baseline differs'
  assert (OUT/'legacy'/(row['name']+'.json.gz')).exists()
 apps=summary['applications'];assert apps['passed'] and apps['owned_applications_closed']
 assert sha((OUT/'applications/ts/load-app008.msq').read_bytes())==apps['tunerstudio']['file_sha256'];assert sha((OUT/'applications/esp32-ecu-load.ini').read_bytes())==apps['tunerstudio']['definition_sha256']
 a=(OUT/'applications/application-page.bin').read_bytes();b=(OUT/'applications/expected-page.bin').read_bytes();assert len(a)==5376 and a==b
 assert struct.unpack_from('<5I',a,5120)==(1,1,3,3,0) and struct.unpack_from('<I',a,5164)[0]==2 and struct.unpack_from('<2f',a,5168)==(99.5,2.5) and not any(a[5176:])
 root=ET.fromstring((OUT/'applications/ts/load-app008.msq').read_bytes());info=root.find('{http://www.msefi.com/:msq}versionInfo');assert info.get('signature')=='ESP32ECU DEV 008 INHIBITED' and info.get('nPages')=='1'
 for name,count in (('engine126.msl',126),('sil83.msl',83)):
  rows=list(csv.reader(io.StringIO((OUT/'applications'/name).read_text()),delimiter='\t'));assert len(rows[2])==count and all(len(r)==count for r in rows[3:]) and 'LoadFuelSource' in rows[2] and '005' in rows[0][0]
 for folder in ('ui-bound','ui-logger','ui-tuning-final','ui-transient-final','ui-semi','ui-idle','ui-cylinder-final','ui-sequential','ui-engine'):
  filename='sequential-ui-tests.json' if folder=='ui-sequential' else 'ui-tests.json';assert json.loads((OUT/'browser'/folder/filename).read_text())['passed']
 for name,environment in (('selected','compact_n16r8_web'),('a3','compact_a3_web'),('bench','compact_a3_timing_bench')):
  p=json.loads((OUT/'static'/('policy-'+name)/'audit.json').read_text());assert p['passed'] and p['elf_sha256']==summary['images_sha256'][environment]['firmware.elf'] and p['binary_sha256']==summary['images_sha256'][environment]['firmware.bin'] and p['app_image_bytes']<=2097152
 assert json.loads((OUT/'static/isr/closure.json').read_text())['passed_static_placement'];usb=json.loads((OUT/'static/tuning-usb.json').read_text());assert usb['exclusive_usb'] and not usb['usb_isr_cache_safe']
 for bits in (32,16):assert json.loads((OUT/'reference'/('build-'+str(bits)+'.json')).read_text())['speeduino_sha']=='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'
 if index:
  expected={str((OUT/n).relative_to(ROOT)):h for n,h in manifest.items()};expected[str((OUT/'artifact-manifest.json').relative_to(ROOT))]=sha((OUT/'artifact-manifest.json').read_bytes())
  if live:
   tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'));expected.update((n,h) for n,h in sources.items() if n in tracked)
  for name,h in expected.items():assert sha(subprocess.check_output(['git','show',':'+name],cwd=ROOT))==h,'Git index differs: '+name
 return dict(passed=True,artifacts=len(manifest),source_snapshots=len(sources),primary_runs=56,refinement_runs=8,legacy_runs=8,independent_execution_sources=len(binding),live_sources_checked=live,index_checked=index,physical_qualification=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-live-sources',action='store_true');p.add_argument('--check-index',action='store_true');a=p.parse_args();print(json.dumps(verify(a.check_live_sources,a.check_index),indent=2))
