import asyncio,copy,csv,io,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))
from playwright.async_api import async_playwright
from engine_runtime import EngineRuntime
from engine_observability import EngineRecorder,load_bridge,encoded
from engine_msq import import_msq

OUT=Path(__file__).parent
fixtures=json.loads((OUT/'browser-fixtures.json').read_text())
runtime=EngineRuntime();runtime.step(dict(rpm=900,synced=True,tps_pct=0),1000,use_decoder=False);sample=runtime.data();runtime.close()
sample['sequence']='9007199254740993';sample['idle']['pid_updates']='18446744073709551615'
recorder=EngineRecorder();assert recorder.command(dict(action='start',period_ms=20,duration_s=1),1000)==200;assert recorder.append(sample,1000);assert recorder.command(dict(action='stop',log_id=1),2000)==200
header=recorder.header();page=recorder.page(1,0);header['boot_id']=page['boot_id']='a'*32
native=recorder.msl(1,boot='a'*32);recorder.close()

async def main():
 checks=[];details={};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   tab=await browser.new_page();tab.on('pageerror',lambda error:errors.append(str(error)));await tab.set_content('<div id="idle"></div>')
   for name in ('cylinder_tuning.js','idle_control.js','engine_logger.js'):await tab.add_script_tag(path=str(ROOT/'web'/name))
   html=(ROOT/'web/index.html').read_text();start=html.index('const LEGACY_ENGINE_SIGNATURE=');end=html.index('function engineFile(',start);await tab.add_script_tag(content=html[start:end])
   result=await tab.evaluate('''fixtures=>{
    const results=[];
    const template=structuredClone(fixtures.default);template.settings.idle_enabled=true;template.idle_control.frequency_hz=222;template.idle_control.run_pct.fill(55);
    for(const [name,text]of Object.entries(fixtures.legacy)){
     const tune=engineFromMsq(text,template);engineImportShape(tune,fixtures.default);
     if(tune.settings.idle_enabled||JSON.stringify(tune.idle_control)!==JSON.stringify(EcuIdleControl.defaults()))throw Error(name+' retained enabled/base idle configuration');
     results.push(name);
    }
    const malformed=[];for(const change of [t=>t.idle_control.extra=0,t=>delete t.idle_control.kd,t=>t.idle_control.algorithm='stepper']){let t=structuredClone(fixtures.default);change(t);try{engineImportShape(t,fixtures.default);malformed.push('accepted')}catch{malformed.push('rejected')}}
    return {legacy:results,malformed,msq:engineToMsq(fixtures.default)};
   }''',fixtures)
   assert all(x=='rejected' for x in result['malformed']);assert import_msq(result['msq'])==fixtures['default'];(OUT/'browser-current.msq').write_text(result['msq']);checks.append('Real Chrome legacy MSQs reset enabled/custom editor idle fields; current export imports through native Python; extra/missing/unknown fields rejected')
   browser_msl=await tab.evaluate('''({header,page})=>{EcuEngineLogger.adopt(header);EcuEngineLogger.acceptPage(page);return EcuEngineLogger.exportMsl();}''',dict(header=header,page=page))
   a=list(csv.reader(io.StringIO(browser_msl),delimiter='\t'));b=list(csv.reader(io.StringIO(native),delimiter='\t'));assert a[2]==b[2] and a[3]==b[3] and all(len(r)==91 for r in a[2:]);assert dict(zip(a[2],a[4]))['IdlePidUpdates']=='18446744073709551615' and dict(zip(a[2],a[4]))['SnapshotSequence']=='9007199254740993';checks.append('91-field Chrome/native MSL headers/units match; new PID counter and snapshot identity preserve full64-bit precision')
   (OUT/'browser-current.msl').write_text(browser_msl);(OUT/'native-current.msl').write_text(native)
   rejected=[];native_valid=[]
   for label,value in [('zero',0),('null',None),('missing','DELETE'),('string_false','false')]:
    modified=copy.deepcopy(page);idle=modified['records'][0]['sample']['idle']
    if value=='DELETE':idle.pop('available')
    else:idle['available']=value
    for key in ('target_rpm','duty_pct','feedforward_pct','p_term','i_term','d_term'):idle[key]=None
    native_valid.append(bool(load_bridge().data_validate(encoded(modified['records'][0]['sample']))))
    rejected.append(await tab.evaluate('''({header,page})=>{EcuEngineLogger.adopt(header);try{EcuEngineLogger.acceptPage(page);return false;}catch{return true;}}''',dict(header=header,page=modified)))
   details['availability_type_variants']=dict(labels=['zero','null','missing','string_false'],browser_rejected=rejected,native_accepted=native_valid)
   assert all(rejected) and not any(native_valid)
   checks.append('Invalid availability0/null/missing/string is rejected atomically by both Chrome collector and native observation parser')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,checks=checks,details=details,page_errors=errors);(OUT/'browser-probe.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
asyncio.run(main())
