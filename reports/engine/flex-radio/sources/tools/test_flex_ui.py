"""Actual Chrome flex editor, migration, diagnostics and log integration."""
import argparse,asyncio,copy,csv,io,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import R,EngineRuntime
from engine_msq import import_msq
from engine_observability import EngineRecorder
from test_engine_flex import tune,edges,step
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 checks=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#flex-enabled').wait_for()
   assert not await page.locator('#flex-enabled').is_checked();assert 'no released flex input' in await page.locator('#engine-flex-panel').inner_text();checks.append('Default corrections are Off; hardware qualification and sensor expiry are explicit')
   await page.locator('#flex-enabled').check();await page.locator('#flex-temperature_enabled').check()
   for key,value in [('fuel_pct','150'),('spark_deg','5'),('temperature_pct','80')]:
    for n in range(6):await page.locator(f'[data-flex-array="{key}"][data-index="{n}"]').fill(value);await page.locator(f'[data-flex-array="{key}"][data-index="{n}"]').dispatch_event('change')
   await page.locator('#engine-flex-panel details').filter(has=page.locator('#flex-low_hz')).evaluate('e=>e.open=true')
   await page.locator('#flex-low_hz').fill('');await page.locator('#flex-low_hz').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='finite value').wait_for();assert device.engine.tune['revision']==1
   await page.locator('#flex-low_hz').fill('50');await page.locator('#flex-low_hz').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   saved=copy.deepcopy(device.engine.tune);assert saved['schema_version']==9 and saved['flex_fuel']==tune()['flex_fuel'];checks.append('Blank calibration rejects without publication; complete curves and flags persist atomically')
   async with page.expect_download() as dl:await page.locator('#engine-msq').click()
   msq=out/'browser010-flex.msq';await (await dl.value).save_as(msq);assert import_msq(msq.read_bytes())==saved;checks.append('Browser own010 MSQ preserves all flex fields through native import')
   old=json.loads((R/'config/engine/defaults-v8.json').read_text());old['secondary_tables']['fuel']['map']['cells'][5]=99.25
   result=await page.evaluate('old=>upgradeLegacyEngine(old,engineTune)',old);assert result['schema_version']==9 and not result['flex_fuel']['correction']['enabled'] and result['secondary_tables']==old['secondary_tables'];checks.append('JSON8 migration keeps the edited secondary map and initializes disabled neutral flex')
   for signature in ('tunerstudio-secondary-roundtrip.msq','tunerstudio-load-roundtrip.msq'):
    result=await page.evaluate('text=>engineFromMsq(text,engineTune)',(R/'tuning/examples'/signature).read_text());assert not result['flex_fuel']['correction']['enabled'];assert all(v==100 for v in result['flex_fuel']['correction']['fuel_pct'])
   checks.append('Historical own008/009 MSQs reset flex flags and curves even when the loaded editor enables them')
   r=EngineRuntime(saved);rec=EngineRecorder()
   try:
    edges(r);step(r);s=r.data();assert s['flex_fuel']['raw_capture_qualified'];assert rec.command(dict(action='start',period_ms=20,duration_s=1),1000000)==200;assert rec.append(s,1000000);rec.command(dict(action='stop',log_id=1),1000001)
    h=rec.header();h['boot_id']=device.engine.data_boot;q=rec.page(1,0);q['boot_id']=h['boot_id'];native=rec.msl(1,h['boot_id'])
   finally:r.close();rec.close()
   report=await page.evaluate('''({h,q,s})=>{
    const bad=[],logger=EcuEngineLogger;
    for(const [key,value]of [['source_code',4],['source','target_capture'],['pending_fault',true],['capture_valid',false],['sample_us','18446744073709551616'],['raw_edges','01'],['available',false],['read_age_ms',0.5],['capture_calibration',{...s.flex_fuel.capture_calibration,low_hz:-1}],['fuel_pct',null],['required',false],['raw_capture_qualified',false],['unexpected',0]]){
     logger.adopt(h);const x=structuredClone(q);x.records[0].sample.flex_fuel[key]=value;
     try{logger.acceptPage(x);bad.push(false)}catch{bad.push(logger.inspect().rows===0&&logger.inspect().cursor===0)}
    }
    logger.adopt(h);logger.acceptPage(q);EcuFlexFuel.status(document.querySelector('#engine-flex-panel'),{flex_fuel:s.flex_fuel,simulator:true});
    return {bad,msl:logger.exportMsl(),text:document.querySelector('#flex-observation').textContent};
   }''',dict(h=h,q=q,s=s));assert all(report['bad']);a=list(csv.reader(io.StringIO(native),delimiter='\t'));b=list(csv.reader(io.StringIO(report['msl']),delimiter='\t'));assert a[2:]==b[2:] and len(b[2])==229;assert 'synthetic_edges' in report['text'] and 'raw capture qualified' in report['text']
   (out/'native007.msl').write_text(native);(out/'browser007.msl').write_text(report['msl']);(out/'control-sample.json').write_text(json.dumps(s,indent=2)+'\n');checks.append('Chrome/native229-column MSL007 agree; malformed flex rows reject before cursor publication')
   # Rendering fixtures disclose scalar and pending-fault provenance.
   text=await page.evaluate('''s=>{const f=structuredClone(s.flex_fuel);f.source='synthetic_value';f.value_qualified=true;f.raw_capture_qualified=false;f.frequency_hz=null;f.reason='<img src=x onerror="window.flexMarkup=true">';EcuFlexFuel.status(document.querySelector('#engine-flex-panel'),{flex_fuel:f,simulator:true});return {text:document.querySelector('#flex-observation').textContent,safe:!document.querySelector('#flex-observation img')&&!window.flexMarkup};}''',s)
   assert text['safe'] and 'synthetic percentage only' in text['text'] and 'unknown Hz' in text['text'];checks.append('Diagnostic rendering keeps scalar data distinct, unknown waveform values and escaped text')
   await page.locator('#engine-flex-panel').screenshot(path=out/'flex-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1100});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'),width
   await page.set_viewport_size({'width':390,'height':1100});await page.locator('#engine-flex-panel').screenshot(path=out/'flex-mobile.png');checks.append('Flex controls and curve tables fit320/390/768/1440px without page overflow')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors);(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
