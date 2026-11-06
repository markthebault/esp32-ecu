#!/usr/bin/env python3
"""Archive a bounded, verified partial boost-integration checkpoint."""
import argparse,gzip,hashlib,io,json,subprocess,tarfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(p.read_text())
def safe(name):
 p=PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive path')
 return p.as_posix()
def run(work,output):
 work=work.resolve();output=output.resolve();output.mkdir(parents=True,exist_ok=False)
 payloads=[];archives=[]
 def archive(filename,items):
  seen=set();path=output/filename
  with path.open('xb') as stream,gzip.GzipFile(fileobj=stream,filename='',mode='wb',mtime=0,compresslevel=9) as zipped,tarfile.open(fileobj=zipped,mode='w') as tar:
   for name,source in sorted(items,key=lambda x:x[0]):
    name=safe(name)
    if name in seen or source.is_symlink() or not source.is_file():raise ValueError('Duplicate/nonregular payload: '+name)
    seen.add(name);data=source.read_bytes();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(data))
    payloads.append(dict(archive=filename,path=name,bytes=len(data),sha256=sha(data)))
  archives.append(dict(path=filename,bytes=path.stat().st_size,sha256=sha(path.read_bytes()),payloads=len(seen)))
 # Each reviewer supplies an explicit, hashed bounded inventory. Never glob
 # their work directory or silently include intermediate binaries/raw traces.
 reviews=[];items=[]
 for label,directory in (('core',work/'independent-review-001'),('storage-initial',work/'storage-review-001'),('storage-promoted',work/'storage-review-002'),('storage-final',work/'storage-review-003')):
  whitelist=read(directory/'archive-whitelist.json');assert Path(whitelist['root']).resolve()==directory
  for row in whitelist['files']:
   source=directory/safe(row['path']);data=source.read_bytes();assert len(data)==row['bytes'] and sha(data)==row['sha256'],source
   items.append((label+'/'+row['path'],source))
  if not any(row['path']=='archive-whitelist.json' for row in whitelist['files']):items.append((label+'/archive-whitelist.json',directory/'archive-whitelist.json'))
  reviews.append(dict(role=label,review_sha256=sha((directory/'review.json').read_bytes()),payloads=len(whitelist['files'])))
 archive('independent-reviews.tar.gz',items)
 # A base Git commit plus the complete changed/new source files reconstructs
 # this checkpoint. Existing unrelated hardware alternatives/logs are omitted.
 names=subprocess.check_output(['git','ls-files','-z','--modified','--others','--exclude-standard'],cwd=ROOT).split(b'\0')
 allowed=('firmware/','web/','config/','scripts/','tools/','tuning/','docs/')
 sources=sorted({name.decode() for name in names if name and (name.decode().startswith(allowed) or name.decode()=='README.md') and not name.decode().startswith('reports/')})
 sources+=['firmware/main/web_assets.hpp','hardware/boost-control/architecture.json']
 archive('sources.tar.gz',[('repo/'+name,ROOT/name) for name in sorted(set(sources))])
 build=work/'firmware-005';summary=read(build/'summary.json');assert summary['exit_code']==0 and summary['source_inputs_unchanged'] and summary['default_cache_unchanged'] and not summary['flashed']
 for name,checksum in read(build/'sources-before.json').items():assert sha((ROOT/name).read_bytes())==checksum,('Build source drift',name)
 for row in summary['artifacts']:assert sha((build/row['path']).read_bytes())==row['sha256']
 verification=[];items=[]
 for env in summary['environments']:
  isr=read(work/('accepted-isr-'+env)/'closure.json');engine=read(work/('accepted-engine-'+env)/'audit.json');usb=read(work/('accepted-usb-'+env+'.json'))
  assert isr['passed_static_placement'] and not isr['floating_point_instructions'] and isr['boost_state_required']
  assert engine['passed'] and usb['exclusive_usb'] and isr['elf_sha256']==engine['elf_sha256']==usb['elf_sha256']
  commands=read(build/'build'/env/'compile_commands.json');selected=[c['file'] for c in commands if c['file'].endswith('/nvs_page.cpp')]
  assert selected==[str(ROOT/'firmware/components/nvs_flash/src/nvs_page.cpp')]
  verification.append(dict(environment=env,elf_sha256=engine['elf_sha256'],binary_sha256=engine['binary_sha256'],app_image_bytes=engine['app_image_bytes'],physical_engine_outputs_inhibited=True,project_nvs_selected=True,static_placement_passed=True))
  items.append((env+'/firmware.bin',build/'build'/env/'firmware.bin'))
 for row in summary['elf_archives']:
  source=build/row['path'];assert sha(source.read_bytes())==row['sha256'];items.append(('elfs/'+source.name,source))
 archive('inhibited-firmware.tar.gz',items)
 items=[]
 for name in ('summary.json','build.log','sources-before.json','sources-after.json','default-cache-before.json','default-cache-after.json'):
  items.append(('build/'+name,build/name))
 for source in sorted((build/'sdkconfigs-after').glob('*')):items.append(('build/sdkconfigs-after/'+source.name,source))
 for prefix in ('accepted-isr-','accepted-engine-'):
  for env in summary['environments']:
   directory=work/(prefix+env)
   for source in sorted(directory.iterdir()):
    if source.is_file():items.append(('audits/'+directory.name+'/'+source.name,source))
 for env in summary['environments']:items.append(('audits/accepted-usb-'+env+'.json',work/('accepted-usb-'+env+'.json')))
 for directory in ('boost-ui-005','legacy-engine-ui-003','logger-ui-002','native-diagnostic-formats-002','nvs-regression-004','final-radio-service-001'):
  for source in sorted((work/directory).rglob('*')):
   if source.is_file() and source.suffix in ('.json','.jsonl','.msl','.log','.txt','.msq','.png'):items.append(('validation/'+directory+'/'+source.relative_to(work/directory).as_posix(),source))
 for name in ('native-suite-final.log','final-python-regressions.log','nonideal-regressions-001.log','legacy-engine-ui-003.log','logger-ui-002.log'):
  items.append(('validation/'+name,work/name))
 native=(work/'native-suite-final.log').read_text();assert 'radio' in native and 'Integrated engine boost and migration: 512 assertions passed' in native
 python=(work/'final-python-regressions.log').read_text();assert 'Ran 173 tests' in python and python.rstrip().endswith('OK')
 assert read(work/'boost-ui-005/ui-tests.json')['passed'] and read(work/'logger-ui-002/ui-tests.json')['passed'] and read(work/'legacy-engine-ui-003/ui-tests.json')['passed']
 assert read(work/'native-diagnostic-formats-002/summary.json')['passed'] and read(work/'nvs-regression-004/summary.json')['passed']
 archive('validation.tar.gz',items)
 report=dict(schema_version=1,title='Partial main-engine boost integration',base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),goal_complete=False,physical_qualification=False,flashed=False,qualification='Main engine, configuration, diagnostics and virtual PWM development. Screens, coupled turbo/wastegate comparison, protected driver/CAD, desktop application acceptance and physical HIL remain unfinished.',reviews=reviews,accepted_build=verification,rejected_attempt=dict(directory=str(work/'firmware-001'),reason='ISR initializer-list minimum emitted a flash helper; failed static placement. Retained only as rejected evidence, not an accepted firmware release.'),test_counts=dict(python=173,author_engine_boost_assertions=512,current_native_diagnostic_cases=6,corrupt_boost_log_columns_rejected=96),archives=archives,payloads=payloads)
 (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
 verify(output)
 print(json.dumps(dict(passed=True,output=str(output),archives=len(archives),payloads=len(payloads),archive_bytes=sum(x['bytes'] for x in archives))))
def verify(output):
 report=read(output/'manifest.json');expected={(x['archive'],x['path']):x for x in report['payloads']};seen=set()
 for row in report['archives']:
  path=output/row['path'];data=path.read_bytes();assert len(data)==row['bytes'] and sha(data)==row['sha256']
  with tarfile.open(path,'r:gz') as tar:
   for member in tar:
    key=(row['path'],safe(member.name));assert member.isfile() and key in expected and key not in seen
    seen.add(key);data=tar.extractfile(member).read();entry=expected[key];assert len(data)==entry['bytes'] and sha(data)==entry['sha256']
 assert seen==set(expected)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify-only',action='store_true');args=parser.parse_args()
 if args.verify_only:verify(args.output);print('All archive and payload hashes verified')
 else:
  if not args.work:parser.error('--work is required to package')
  run(args.work,args.output)
