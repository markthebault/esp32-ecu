#!/usr/bin/env python3
"""Verify immutable flex software evidence and replay saved/kernel checks."""
import argparse,gzip,hashlib,json,os,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/engine/flex-integration'
def sha(body):return hashlib.sha256(body).hexdigest()
def require(ok,label):
 if not ok:raise ValueError(label)
def path(root,name):
 p=Path(name);require(bool(name)and not p.is_absolute()and '..'not in p.parts,'Unsafe path: '+name)
 out=root/p;require(not out.is_symlink()and out.resolve().is_relative_to(root.resolve()),'Escaping/symlink path: '+name);return out
def document(p):return json.loads(p.read_text())
def compressed(p):
 with gzip.open(p,'rb')as f:body=f.read(16*1024*1024+1)
 require(len(body)<=16*1024*1024,'Oversized saved plant result');return json.loads(body)

def verify(report=REPORT,live=False,replay=False):
 report=report.resolve();manifest=document(report/'artifact-manifest.json');entries=manifest['artifacts'];names={r['path']for r in entries}
 require(len(names)==len(entries),'Duplicate artifact')
 actual={str(p.relative_to(report))for p in report.rglob('*')if p.is_file()and p!=report/'artifact-manifest.json'}
 require(actual==names,'Artifact set differs')
 for r in entries:
  p=path(report,r['path']);body=p.read_bytes();require(len(body)==r['bytes']and sha(body)==r['sha256'],'Changed artifact: '+r['path'])
 summary=document(report/'summary.json')
 require(summary['scope']=='flex_development_software_integration'and summary['checks_passed'],'Integration scope/checks')
 for key in ('target_capture_implemented','pcb_input_released','flex_radio_implemented','physical_qualification','online_tuner_accepted','ethanol_combustion_validated','full_speeduino_parity'):
  require(summary[key]is False,'Overstated acceptance: '+key)
 for name,r in summary['sources'].items():
  body=path(report,r['snapshot']).read_bytes();require(sha(body)==r['sha256'],'Source snapshot changed: '+name)
  if live:require(path(ROOT,name).read_bytes()==body,'Live source changed: '+name)
 for item in summary['reviews']:
  review=document(path(report,item['path']));require(review['accepted']and not review['open_findings'],'Independent review has open findings')
  for name,digest in item['bound_sources'].items():require(summary['sources'][name]['sha256']==digest,'Review source mismatch: '+name)
 matrix=document(report/'plant/index.json');require(matrix['passed']and not matrix['failures']and len(matrix['cases'])==27,'Plant matrix acceptance')
 for name,digest in matrix['source_sha256'].items():require(summary['sources'][name]['sha256']==digest,'Plant source binding: '+name)
 cache={};case_map={}
 for case in matrix['cases']:
  name=case['name'];result=compressed(path(report,'plant/'+name+'.json.gz'));cache[name]=result;case_map[name]=case
  require(result['summary']==case['summary'],'Saved plant summary differs: '+name)
  require(result['summary']['physical_outputs_enabled']is False and result['summary']['final_outputs_high']==0,'Plant inhibition/end cut: '+name)
  kind=case['case'];rows=result['trace'];s=result['summary'];f=result['final']['flex_fuel']
  if kind=='missing':require(s['fuel_mg']==0 and all(r['fuel_cut']and r['spark_cut']for r in rows),'Missing sensor did not cut: '+name)
  elif kind=='zero':require(s['fuel_mg']==0 and all(r['pulse_ms']==0 for r in rows),'Zero factor resurrected fuel: '+name)
  elif kind=='dropout':
   tail=[r for r in rows if r['time']>=2.3];require(tail and all(r['fuel_cut']and r['spark_cut']and r['pulse_ms']==0 and not r['flex_fuel']['control_ok']for r in tail),'Stale sensor did not cut: '+name)
  elif kind!='off':require(s['final_faults']==0 and s['fuel_mg']>0 and f['raw_capture_qualified'],'Qualified operation: '+name)
 for name,case in case_map.items():
  if case['case']=='neutral':
   a=cache[name];b=cache[case['strategy']+'-off'];require(a['edges']==b['edges']and all(a['summary'][k]==b['summary'][k]for k in ('final_rpm','fuel_mg')),'Neutral causal control differs: '+name)
 app=document(report/'applications/application-roundtrip.json');require(app['passed']and app['all_bytes_match']and app['before']==125.5 and app['after']==130.5,'Actual offline application edit')
 require(sha((report/'applications/application-edited010-003.msq').read_bytes())==app['file_sha256'],'Application MSQ differs')
 require(sha((report/'applications/application-page.bin').read_bytes())==app['expected_page_sha256'],'Application expected page differs')
 require(document(report/'applications/mlv-check.json')['passed'],'Actual log application check')
 for name in ('flex','tuning','secondary','observability'):
  require(document(report/f'browser/{name}/ui-tests.json')['passed'],'Chrome check: '+name)
 selected=document(report/'build/selected/audit.json');isr=document(report/'build/isr-selected/closure.json');usb=document(report/'build/tuning.json')
 require(selected['passed']and selected['policy']=='engine_scheduler_physical_writes_compile_time_inhibited','Selected output policy')
 require(isr['passed_static_placement']and not isr['failures'],'ISR placement')
 require(selected['elf_sha256']==isr['elf_sha256']==usb['elf_sha256'],'Target audit ELF binding')
 require('engine_flex_checks 296'in(report/'validation/native.log').read_text(),'Native kernel checks')
 if replay:
  with tempfile.TemporaryDirectory(prefix='ecu-flex-integration-')as temporary:
   work=Path(temporary);env={**os.environ,'ASAN_OPTIONS':'detect_leaks=1:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1','GCOV_PREFIX':str(work/'gcov'),'GCOV_PREFIX_STRIP':'0'}
   exe=work/'engine-flex';argv=['g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(report/'sources/firmware/include'),str(report/'sources/firmware/tests/engine_flex_test.cpp'),'-o',str(exe)]
   subprocess.run(argv,check=True,env=env);r=subprocess.run([str(exe)],capture_output=True,text=True,env=env)
   require(r.returncode==0 and r.stdout.strip()=='engine_flex_checks 296'and not r.stderr,'Frozen sanitizer replay: '+r.stderr)
   outputs=[]
   for name,include,defines in [('baseline',report/'reviews/baseline/firmware/include',[]),('candidate',report/'sources/firmware/include',['-DREVIEW_NEW'])]:
    exe=work/name;argv=['g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer',*defines,'-I'+str(include),str(report/'reviews/off-baseline-001.cpp'),'-o',str(exe)]
    subprocess.run(argv,check=True,env=env);r=subprocess.run([str(exe)],capture_output=True,env=env)
    require(r.returncode==0 and not r.stderr and r.stdout.count(b'\n')==14400,'Off-baseline replay failed: '+name);outputs.append(r.stdout)
   require(outputs[0]==outputs[1]and sha(outputs[0])=='5825b992bb99148fc851c8656e164edde7a54b22cc98d8f8803258df4de6da92','Off-baseline bytes differ')
 print('Verified',len(entries),'artifacts,',len(summary['sources']),'sources and27 saved plant cases'+('; replayed296 sanitizer checks and14400 exact Off rows'if replay else '')+'. Target/PCB/flex radio, ethanol chemistry, online vendor and physical/full parity gates remain open.')
 return dict(passed=True,artifacts=len(entries),sources=len(summary['sources']),plant_cases=27,replayed=replay)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,default=REPORT);p.add_argument('--check-live-sources',action='store_true');p.add_argument('--replay',action='store_true');a=p.parse_args();verify(a.report,a.check_live_sources,a.replay)
