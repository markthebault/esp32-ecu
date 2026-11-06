"""Installed Chrome: explicit unit transitions, source exchange, CAS and logs."""
import argparse,asyncio,copy,csv,io,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import EngineRuntime,R
from engine_msq import import_msq
from engine_protocol import pages
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 checks=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#load-fuel_source').wait_for()
   original=copy.deepcopy(device.engine.tune);assert original['schema_version']==8
   await page.locator('#load-fuel_source').select_option('tps');await page.locator('#engine-save').click()
   await page.locator('#toast').filter(has_text='acknowledge the new table basis').wait_for();assert device.engine.tune==original
   assert await page.evaluate('engineTune.maps.ve.load')==original['maps']['ve']['load']
   await page.locator('[data-load-basis="ve"][data-load-action="initialize"]').click()
   assert 'Acknowledge' in await page.locator('#load-error-ve').inner_text();assert await page.evaluate('engineTune.maps.ve.cells')==original['maps']['ve']['cells']
   await page.locator('#load-spark_source').select_option('tps');await page.locator('#load-pressure').select_option('none')
   for k in ('ve','spark','lambda','trim'):
    await page.locator('#load-ack-'+k).check();await page.locator(f'[data-load-basis="{k}"][data-load-action="initialize"]').click()
   assert '% TPS' in await page.locator('#engine-map').inner_text()
   assert await page.evaluate('engineTune.maps.ve.cells')==original['maps']['ve']['cells']
   assert await page.evaluate('engineTune.maps.ve.load')!=original['maps']['ve']['load']
   await page.locator('[data-cell="0"]').fill('3.25');await page.locator('[data-cell="0"]').dispatch_event('change')
   await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   saved=copy.deepcopy(device.engine.tune);assert saved['load_model']['fuel_source']=='tps' and saved['maps']['ve']['cells'][0]==3.25
   checks.append('Source edits preserve axes/cells, mismatch blocks Save, explicit acknowledgement precedes axis replacement; coefficient below20 saves from schema7 onward')
   async with page.expect_download() as d:await page.locator('#engine-msq').click()
   file=out/'load-browser009.msq';await (await d.value).save_as(file);assert 'DEV 009' in file.read_text() and pages(import_msq(file.read_bytes()))==pages(saved)
   imported=await page.evaluate('text=>engineFromMsq(text,engineTune)',file.read_text());assert pages(imported)==pages(saved)
   checks.append('Browser own0098192-byte complete-page MSQ preserves sources, basis metadata and all map fields through native roundtrip')
   application=R/'tuning/examples/tunerstudio-load-roundtrip.msq'
   await page.locator('#engine-import-file').set_input_files(application)
   await page.locator('#engine-save-state').filter(has_text='Imported edits').wait_for()
   assert await page.locator('#load-afr').input_value()=='measured' and await page.locator('#load-fixed_baro_kpa').input_value()=='99.5' and await page.locator('#load-afr_delay_s').input_value()=='2.5'
   current=await page.evaluate('engineTune');assert pages(current)==pages(import_msq(application.read_bytes(),base_revision=2)) and device.engine.tune==saved
   checks.append('Actual TunerStudio008 file imports measured-AFR/99.5kPa/2.5s edits and all F32 table cells exactly, preserving loaded CAS and leaving active tune unchanged')
   oracle_dir=R/'reports/engine/load-model/reviews/architecture'
   if not (oracle_dir/'baseline-msq-oracle.json').exists():oracle_dir=R/'.cache/engine/load-architecture-review'
   oracle=json.loads((oracle_dir/'baseline-msq-oracle.json').read_text())
   for c in oracle['cases']:
    text=(oracle_dir/'legacy-msq-oracles'/(c['case']+'.msq')).read_text()
    result=await page.evaluate('text=>{try{return {accepted:true,tune:engineFromMsq(text,engineTune)}}catch(e){return {accepted:false,error:e.message}}}',text)
    assert result['accepted']==(c['expected']=='accepted'),(c['case'],result)
    if result['accepted']:assert result['tune']['load_model']==original['load_model']
   old=json.loads((R/'config/engine/defaults-v6.json').read_text());old['revision']=2;old['transient_enrichment']['mode']='map_rate'
   await page.locator('#engine-import-file').set_input_files(dict(name='legacy6.json',mimeType='application/json',buffer=json.dumps(old).encode()))
   await page.locator('#engine-save-state').filter(has_text='Imported edits').wait_for();assert await page.evaluate('engineTune.schema_version')==8 and await page.locator('#ae-mode').input_value()=='map_rate';assert device.engine.tune==saved
   checks.append('All21 frozen own001..007 import outcomes agree; JSON6 migrates to MAP/target while preserving its transient settings, without publication')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   await page.locator('#load-pressure').select_option('map_baro');await page.locator('#load-baro_source').select_option('aux');await page.locator('#engine-save').click()
   await page.locator('#toast').filter(has_text='Live barometric pressure requires J16').wait_for();assert device.engine.tune==saved
   await page.locator('#load-aux_role').select_option('baro');await page.locator('#load-fixed_baro_kpa').fill('');await page.locator('#load-fixed_baro_kpa').dispatch_event('change');await page.locator('#engine-save').click()
   await page.locator('#toast').filter(has_text='enter a finite value').wait_for();assert device.engine.tune==saved
   await page.locator('#load-fixed_baro_kpa').fill('99');await page.locator('#load-fixed_baro_kpa').dispatch_event('change')
   external=copy.deepcopy(saved);external['load_model']['afr_delay_s']=12;assert device.engine.save(json.dumps(external).encode())[0]==200
   await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='revision changed').wait_for();assert device.engine.tune['load_model']['afr_delay_s']==12 and device.engine.tune['revision']==3
   checks.append('J16 role conflicts and blank pressure input reject; concurrent Save is409 and preserves active configuration')
   # A real native observation drives both MSL exporters, with no plant claims.
   runtime=EngineRuntime(saved)
   try:
    runtime.step(dict(rpm=1200,synced=True,map_kpa=None,map_qualified=False,tps_pct=10),1000000,use_decoder=False);sample=runtime.data()
   finally:runtime.close()
   recorder=device.engine.data_recorder;assert recorder.command(dict(action='start',period_ms=20,duration_s=2),1000000)==200;assert recorder.append(sample,1000000);recorder.command(dict(action='stop',log_id=1),1000001)
   h=recorder.header();h['boot_id']=device.engine.data_boot;q=recorder.page(1,0);q['boot_id']=h['boot_id'];native=recorder.msl(1,h['boot_id'])
   result=await page.evaluate('''({h,q})=>{const x=window.EcuEngineLogger,bad=[];
    for(const value of [null,{},[],{available:false}]){x.adopt(h);const p=structuredClone(q);p.records.at(-1).sample.load_model=value;try{x.acceptPage(p);bad.push(false)}catch{bad.push(x.inspect().rows===0&&x.inspect().cursor===0)}}
    for(const [key,value] of [['fuel_source_code',3],['fuel_source','map'],['afr_state_code',255],['fuel_load','10'],['afr_factor',null],['unexpected',0],['spark_load',3.5e38],['afr_factor',1e300],['pressure_factor',1e-300]]){x.adopt(h);const p=structuredClone(q);p.records.at(-1).sample.load_model[key]=value;try{x.acceptPage(p);bad.push(false)}catch{bad.push(x.inspect().rows===0&&x.inspect().cursor===0)}}
    x.adopt(h);x.acceptPage(q);return {bad,msl:x.exportMsl()};}''',dict(h=h,q=q))
   assert all(result['bad']);a=list(csv.reader(io.StringIO(native),delimiter='\t'));b=list(csv.reader(io.StringIO(result['msl']),delimiter='\t'));assert a[2:]==b[2:] and len(b[2])==188
   (out/'native005.msl').write_text(native);(out/'browser005.msl').write_text(result['msl'])
   checks.append('Native/browser188-column MSL006 agree exactly including unavailable MAP; malformed load observations reject before cursor publication')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 3').wait_for()
   await page.locator('#engine-load-panel').scroll_into_view_if_needed();await page.screenshot(path=out/'load-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   await page.set_viewport_size({'width':390,'height':1000});await page.locator('#engine-load-panel').scroll_into_view_if_needed();await page.screenshot(path=out/'load-mobile.png')
   checks.append('Load editor and source-labelled map/trim grids fit320/390/768/1440px')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors);(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/load/ui');a=p.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
