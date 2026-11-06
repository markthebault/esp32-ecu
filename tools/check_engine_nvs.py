#!/usr/bin/env python3
"""Check the pinned NVS override using real storage/page code and a memory partition.

Persistent low-level flash-operation error injection is a software model. This
does not emulate physical brownouts, partial writes, flash wear or target time.
"""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(output):
 output=output.resolve();output.mkdir(parents=True,exist_ok=False)
 component=ROOT/'firmware/components/nvs_flash';sdk=Path.home()/'.platformio/packages/framework-espidf';original=sdk/'components/nvs_flash'
 manifest=json.loads((component/'ecu-source-manifest.json').read_text());assert json.loads((sdk/'package.json').read_text())['version']==manifest['package']
 for name,row in manifest['files'].items():
  assert digest(component/name)==row['project_sha256'] and digest(original/name)==row['upstream_sha256'],name
 page=(original/'src/nvs_page.cpp').read_bytes();pattern=b'findItem(item.nsIndex, item.datatype, item.key, findItemIndex, dupItem)'
 assert page.count(pattern)==1 and page.replace(pattern+b' == ESP_OK) {',pattern[:-1]+b', item.chunkIndex) == ESP_OK) { // ESP32ECU local modification: preserve distinct blob chunks.')==(component/'src/nvs_page.cpp').read_bytes()
 sources=('nvs_storage.cpp','nvs_pagemanager.cpp','nvs_page.cpp','nvs_types.cpp','nvs_item_hash_list.cpp')
 frozen=[component/'ecu-source-manifest.json',*[component/name for name in manifest['files']],*[ROOT/'tools/nvs_sdk'/name for name in ('nvs_probe.cpp','nvs_nonblob.cpp')],*sorted((ROOT/'tools/nvs_sdk/shims').glob('*.h')),sdk/'components/esp_rom/linux/esp_rom_crc.c']
 before={str(p):digest(p) for p in frozen};commands=[];results={};ledgers={}
 def execute(command,name):
  commands.append(dict(name=name,command=command))
  with (output/(name+'.log')).open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-DLINUX_TARGET','-DNO_DEBUG_STORAGE','-DESP_TEE_BUILD=1']
 common_include=[ROOT/'tools/nvs_sdk/shims',sdk/'components/esp_common/include',sdk/'components/esp_rom/include']
 execute(['cc',*flags,*[v for p in common_include for v in ('-I',str(p))],'-c',str(sdk/'components/esp_rom/linux/esp_rom_crc.c'),'-o',str(output/'crc.o')],'crc')
 for label,base in (('upstream',original),('project',component)):
  includes=[*common_include,base/'src',base/'include',base/'private_include']
  for kind,source in (('blob','nvs_probe.cpp'),('nonblob','nvs_nonblob.cpp')):
   binary=output/(label+'-'+kind);prefix=label+'-'+kind
   execute(['c++','-std=c++17',*flags,*[v for p in includes for v in ('-I',str(p))],*[str(base/'src'/name) for name in sources],str(ROOT/'tools/nvs_sdk'/source),str(output/'crc.o'),'-o',str(binary)],prefix+'-compile')
   execute([str(binary),str(output/(prefix+'-faults.jsonl'))],prefix+'-run')
   text=(output/(prefix+'-run.log')).read_text()
   ledger=output/(prefix+'-faults.jsonl');records=[json.loads(line) for line in ledger.read_text().splitlines()]
   assert len(records)==(360 if kind=='blob' else 120)
   grid=[row['cut'] for row in records] if kind=='blob' else [(row['kind'],row['cut']) for row in records]
   assert grid==(list(range(360)) if kind=='blob' else [(k,c) for k in range(3) for c in range(40)])
   expected_missing=1 if label=='upstream' and kind=='blob' else 0
   missing=sum(row['value'] not in ('old','new') for row in records);ack_loss=sum(row['write_result']==0 and row['value']!='new' for row in records)
   assert missing==expected_missing and ack_loss==0,text
   if kind=='blob':
    lost=re.search(r'unavailable_after_reinit=(\d+)',text);ack=re.search(r'acknowledged_loss=(\d+)',text);assert lost and ack and int(lost[1])==missing and int(ack[1])==ack_loss
    normal=[tuple(map(int,m)) for m in re.findall(r'^size=(\d+) saves=(\d+) writes=',text,re.M)]
    assert normal==[(size,200) for size in (49152,53248,57344,60000)],text
    if label=='upstream':assert records[9]==dict(cut=9,write_result=0x6001,read_result=0x1102,value='unavailable')
   else:assert json.loads(text.splitlines()[-1])['passed'] is True
   ledgers[prefix]=records
   results[prefix]=dict(expected_missing=expected_missing,acknowledged_loss=ack_loss,ledger_rows=len(records),ledger_sha256=digest(ledger),stdout_sha256=digest(output/(prefix+'-run.log')),normal_saves_per_size=200 if kind=='blob' else None)
 for kind in ('blob','nonblob'):
  for index,(old,new) in enumerate(zip(ledgers['upstream-'+kind],ledgers['project-'+kind])):
   if kind=='blob' and index==9:assert new==dict(cut=9,write_result=0x6001,read_result=0,value='old')
   else:assert old==new,(kind,index,old,new)
 assert before=={str(p):digest(p) for p in frozen}
 report=dict(passed=True,scope=__doc__.strip(),physical_qualification=False,installed_sdk_unchanged=True,runtime_files_verified=len(manifest['files']),results=results,source_sha256=before,commands=commands)
 (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=True,runtime_files_verified=len(manifest['files']),results=results)))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output)
