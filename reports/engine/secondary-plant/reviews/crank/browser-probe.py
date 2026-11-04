from pathlib import Path
import hashlib,html,json,re,subprocess,sys
from html.parser import HTMLParser
out=Path(__file__).resolve().parent;phase=sys.argv[1];src=out/(phase+'-sources');assets=(src/'firmware/main/web_assets.hpp').read_text()
js=[]
for name in ('load_js','secondary_js','engine_log_js'):
 match=re.search(r'inline constexpr char '+name+r'\[\]=R"ECU_ASSET\((.*?)\)ECU_ASSET";',assets,re.S)
 assert match,name
 js.append(match[1])
fixture=json.loads((out/(phase+'-runtime-fixture.json')).read_text());fixture['msl']=(out/(phase+'-native.msl')).read_text();probe=json.loads((out/(phase+'-probe-r3.json')).read_text())
script='\n'.join(js)+'\nconst fixture='+json.dumps(fixture,separators=(',',':'))+';\nconst observations='+json.dumps(probe['observations'],separators=(',',':'))+r''';
try{
 const failures=[];let accepted=0,rejected=0;
 for(const row of observations){let valid=true;try{EcuSecondaryTables.checkObservation(row.observation,row.kind,true)}catch{valid=false}const expected=row.case!=='invalid_rule_not_bypassed';if(valid!==expected)failures.push({case:row.case,expected,valid});if(valid)accepted++;else rejected++;}
 EcuEngineLogger.adopt(fixture.header);EcuEngineLogger.acceptPage(fixture.page);
 const msl=EcuEngineLogger.exportMsl();const normalized=s=>s.trim().split(/\r?\n/).slice(2).join('\n');const parity=normalized(msl)===normalized(fixture.msl);
 if(!parity)failures.push({case:'native_browser_msl',expected:true,valid:false});
 const root=document.querySelector('#status');
 const crank=fixture.page.records[1].sample;
 EcuSecondaryTables.status(root,{simulator:true,secondary_tables:crank.secondary_tables});
 const rendered=root.textContent;const expectedText=['cranking_spark_bypass','synthetic_input','true / true','1020000'];for(const value of expectedText)if(!rendered.includes(value))failures.push({case:'crank_status_'+value});
 const u64=observations.find(r=>r.case==='exact_u64_observation_time'&&r.observation.input_qualified).observation;
 const other=structuredClone(crank.secondary_tables);other.spark=u64;EcuSecondaryTables.status(document.querySelector('#u64-status'),{simulator:true,secondary_tables:other});
 if(!document.querySelector('#u64-status').textContent.includes(u64.input_observed_us))failures.push({case:'exact_u64_status'});
 document.querySelector('#result').textContent=JSON.stringify({passed:failures.length===0,accepted,rejected,recordedRows:fixture.page.records.length,mslColumns:msl.trim().split(/\r?\n/)[2].split('\t').length,nativeBrowserMslParity:parity,exactU64:u64.input_observed_us,failures});
}catch(error){document.querySelector('#result').textContent=JSON.stringify({passed:false,error:String(error),stack:error.stack});}
'''
# Correct literal regex separators in the generated script.
script=script.replace(r'/\\r?\\n/',r'/\r?\n/').replace(r"join('\\n')",r"join('\n')").replace(r"split('\\t')",r"split('\t')")
doc='<html><head><meta charset="utf-8"><style>body{font:15px system-ui;max-width:1000px;margin:24px}.keyline{display:flex;justify-content:space-between;margin:7px 0}h3{margin-top:26px}#result{white-space:pre-wrap}</style></head><body><h1>Independent secondary spark transition diagnostic probe</h1><pre id="result">Pending</pre><div id="status"><div id="switch-accessory-status"></div><div id="secondary-observation"></div></div><h2>Exact U64 observation display</h2><div id="u64-status"><div id="secondary-observation"></div></div><script>'+script+'</script></body></html>'
path=out/(phase+'-browser-probe.html');path.write_text(doc)
cmd=['google-chrome','--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--dump-dom',path.as_uri()]
with(out/(phase+'-chrome-stderr.log')).open('w')as err:result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=err,text=True,check=True,timeout=30)
(out/(phase+'-browser-dom.html')).write_text(result.stdout)
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.active=False;self.text=''
 def handle_starttag(self,tag,attrs):
  if tag=='pre'and('id','result')in attrs:self.active=True
 def handle_endtag(self,tag):
  if tag=='pre':self.active=False
 def handle_data(self,text):
  if self.active:self.text+=text
p=Parser();p.feed(result.stdout);v=json.loads(p.text);(out/(phase+'-browser-result.json')).write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v,indent=2));assert v['passed'],v
subprocess.run(['google-chrome','--headless','--no-sandbox','--disable-gpu','--hide-scrollbars','--window-size=1280,1400','--screenshot='+str(out/(phase+'-browser-status.png')),path.as_uri()],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=30)
