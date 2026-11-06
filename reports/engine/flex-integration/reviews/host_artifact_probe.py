#!/usr/bin/env python3
"""Frozen capture/application/source binding; execute only owned helpers."""
import csv,hashlib,io,json,os,shutil,subprocess,sys
from pathlib import Path
F=Path(sys.argv[1]).resolve();O=Path(__file__).resolve().parent
sys.path.insert(0,str(F/'tools'))
from engine_msq import import_msq
from engine_protocol import pages
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();checks=0
def require(v,label):
 global checks
 checks+=1
 if not v:raise AssertionError(label)
plant1=O/'plant-capture-001';plant2=O/'plant-capture-002';p1=json.loads((plant1/'index.json').read_text());p2=json.loads((plant2/'index.json').read_text());compared={}
require(p1['cases']==p2['cases'],'all 27 source-bound cases same declaration/tune/result')
for p in sorted(plant1.iterdir()):
 if p.name=='index.json':continue
 require(H(p)==H(plant2/p.name),'identical saved capture bytes '+p.name);compared[p.name]=H(p)
require(len(compared)==54,'27 gzip and 27 MSL files')
for rel,want in p2['source_sha256'].items():require(H(F/rel)==want,'matrix002 final source bound '+rel)
app=O/'applications-capture-001';declared=json.loads((app/'application-roundtrip.json').read_text());raw=app/'application-edited010-003.msq'
require(H(raw)==declared['file_sha256'],'TS edited MSQ bound')
t=import_msq(raw.read_bytes());page=bytes(pages(t)[1]);require(len(page)==8192 and page==(app/'application-page.bin').read_bytes(),'TS imported entire8192 page exact')
require(hashlib.sha256(page).hexdigest()==declared['expected_page_sha256'],'page SHA bound')
require(t['flex_fuel']['capture']['filter_ms']==130.5,'committed app edit retained')
for name in ('application-edited010.msq','application-edited010-002.msq'):
 require(import_msq((app/name).read_bytes())['flex_fuel']['capture']['filter_ms']==125.5,'earlier saves unchanged, not successes')
mlv=json.loads((app/'mlv-check.json').read_text());msl=app/'flex-waveform007.msl';require(H(msl)==mlv['input_sha256'],'MLV original input bound')
table=list(csv.reader(io.StringIO(msl.read_text()),delimiter='\t'));require(len(table[2])==229 and len(table[4:])==121 and all(len(r)==229 for r in table[2:]),'native MSL121x229')
i=table[2].index('FlexEthanolPct');known=[float(row[i])for row in table[4:]if row[i]!='NaN'];require(abs(min(known)-1.724)<.00051 and abs(max(known)-99.993)<.00051,'saved plotted field min/max')
require(any(row[i]=='NaN'for row in table[4:]),'startup unknowns preserved')
jars=json.loads((app/'independent-jar-hashes.json').read_text());require(jars['TunerStudioMS.jar']==declared['jar_sha256'] and jars['HogLogViewer.jar']==mlv['jar_sha256'],'actual JAR hashes independently read')
regen=O/'host-generated-replay-001';shutil.copytree(F,regen,ignore=shutil.ignore_patterns('.cache','__pycache__'))
generated=['web/flex_fuel.js','tuning/esp32-ecu-flex.ini','tuning/protocol-layout.json','firmware/main/web_assets.hpp'];before={p:H(regen/p)for p in generated};commands=[]
for script in ('scripts/generate_flex_ui.py','scripts/generate_tunerstudio_ini.py','scripts/embed_web.py'):
 command=['python3',str(regen/script)];p=subprocess.run(command,cwd=regen,text=True,capture_output=True,env=os.environ.copy());commands.append(dict(command=command,cwd=str(regen),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));require(p.returncode==0,'owned generator succeeds '+script)
for rel in generated:require(H(regen/rel)==before[rel],'generated exact '+rel)
print(json.dumps({'passed':True,'checks':checks,'plant_capture_sha256':compared,'matrix002_index_sha256':H(plant2/'index.json'),'matrix_source_hashes':p2['source_sha256'],'application_artifacts':{p.name:H(p)for p in app.iterdir()if p.is_file()},'application_scope':'Independently parsed/copied parent saved application evidence and inspected screenshots. No independent application launch; offline own010 only. Online acceptance and physical USB remain unverified. External viewer numeric U64 display is not a precision guarantee.','generator_commands':commands,'generated_sha256':before},indent=2))
