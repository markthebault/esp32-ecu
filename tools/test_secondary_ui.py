"""Installed Chrome: secondary edits, compatibility, CAS and full log parity."""
import argparse,asyncio,copy,csv,io,json,tempfile,threading
import xml.etree.ElementTree as ET
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import EngineRuntime,R
from engine_msq import export_msq,import_msq
from engine_protocol import pages
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 checks=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#sec-fuel-mode').wait_for()
   initial=copy.deepcopy(device.engine.tune);assert initial['schema_version']==8
   await page.locator('#sec-fuel-mode').select_option('multiply');await page.locator('#engine-save').click()
   await page.locator('#toast').filter(has_text='cell meaning').wait_for();assert device.engine.tune==initial
   await page.locator('#sec-fuel-source').select_option('tps');assert await page.evaluate('engineTune.secondary_tables.fuel.map')==initial['secondary_tables']['fuel']['map']
   await page.locator('[data-sec-review="fuel"][data-action="initialize"]').click();assert 'Acknowledge' in await page.locator('#sec-fuel-error').inner_text()
   await page.locator('#sec-fuel-ack').check();await page.locator('[data-sec-review="fuel"][data-action="initialize"]').click()
   assert await page.evaluate('engineTune.secondary_tables.fuel.map.cells')==initial['secondary_tables']['fuel']['map']['cells']
   await page.locator('#sec-fuel-ack').check();await page.locator('[data-sec-review="fuel"][data-action="neutral"]').click()
   assert await page.evaluate('engineTune.secondary_tables.fuel.map.cells')==[100]*256
   assert '% TPS' in await page.locator('#engine-map').inner_text()
   await page.locator('[data-cell="0"]').fill('150');await page.locator('[data-cell="0"]').dispatch_event('change')
   await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   saved=copy.deepcopy(device.engine.tune);assert saved['secondary_tables']['fuel']['mode']=='multiply' and saved['secondary_tables']['fuel']['map']['cells'][0]==150 and saved['maps']==initial['maps']
   checks.append('Mode/source edits retain data; Save blocks mismatched units; acknowledgement precedes axis replacement and explicit neutral fill; Save publishes full map')
   await page.locator('#sec-spark-mode').select_option('add');await page.locator('#sec-spark-ack').check();await page.locator('[data-sec-review="spark"][data-action="neutral"]').click()
   await page.locator('[data-cell="0"]').fill('-2.5');await page.locator('[data-cell="0"]').dispatch_event('change')
   await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 3').wait_for()
   saved=copy.deepcopy(device.engine.tune);assert saved['secondary_tables']['spark']['cells']=='adder' and saved['secondary_tables']['spark']['map']['cells'][0]==-2.5
   async with page.expect_download() as d:await page.locator('#engine-msq').click()
   file=out/'secondary-browser009.msq';await (await d.value).save_as(file);assert 'DEV 009' in file.read_text() and pages(import_msq(file.read_bytes()))==pages(saved)
   units=lambda text:{e.get('name'):e.get('units') for e in ET.fromstring(text).iter() if e.tag.endswith('}constant') and e.get('name','').startswith('secondary_')}
   assert units(file.read_text())==units(export_msq(saved)) and units(file.read_text())['secondary_spark_mapTable']=='deg delta'
   imported=await page.evaluate('text=>engineFromMsq(text,engineTune)',file.read_text());assert pages(imported)==pages(saved)
   checks.append('Independent spark additive units and signed cell edits survive8192-byte own009 browser/native MSQ roundtrip')
   application=R/'tuning/examples/tunerstudio-secondary-roundtrip.msq';await page.locator('#engine-import-file').set_input_files(application)
   await page.locator('#engine-save-state').filter(has_text='Imported edits').wait_for()
   current=await page.evaluate('engineTune');assert pages(current)==pages(import_msq(application.read_bytes(),base_revision=3)) and device.engine.tune==saved
   assert current['secondary_tables']['fuel']['map']['cells'][0]==124.5 and current['secondary_tables']['spark']['map']['cells'][0]==-3.75
   checks.append('Actual TunerStudio own009 file imports both edited rules/maps without publishing or rebasing the editor')
   application=R/'tuning/examples/tunerstudio-load-roundtrip.msq';await page.locator('#engine-import-file').set_input_files(application)
   await page.locator('#engine-save-state').filter(has_text='Imported edits').wait_for()
   current=await page.evaluate('engineTune');assert current['schema_version']==8 and current['load_model']['afr']=='measured' and current['load_model']['fixed_baro_kpa']==99.5 and all(r['mode']=='off' for r in current['secondary_tables'].values())
   assert pages(current)==pages(import_msq(application.read_bytes(),base_revision=3)) and device.engine.tune==saved
   old=json.loads((R/'config/engine/defaults-v7.json').read_text());old['revision']=3;old['maps']['ve']['cells'][0]=0
   candidate=await page.evaluate('value=>upgradeLegacyEngine(value,engineTune)',old);assert candidate['schema_version']==8 and candidate['maps']['ve']['cells'][0]==0 and candidate['load_model']==old['load_model']
   old6=json.loads((R/'config/engine/defaults-v6.json').read_text());old6['maps']['ve']['cells'][0]=0
   assert await page.evaluate('value=>{try{upgradeLegacyEngine(value,engineTune);return false}catch{return true}}',old6)
   checks.append('Actual own008 file retains load/AFR calibration and migrates secondaryOff; JSON7 keeps zero coefficient while older bounds remain enforced; imports do not publish')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 3').wait_for()
   await page.locator('#sec-fuel-threshold').fill('');await page.locator('#sec-fuel-threshold').dispatch_event('change');await page.locator('#engine-save').click()
   await page.locator('#toast').filter(has_text='finite values').wait_for();assert device.engine.tune==saved
   await page.locator('#sec-fuel-threshold').fill('3000');await page.locator('#sec-fuel-threshold').dispatch_event('change')
   external=copy.deepcopy(saved);external['secondary_tables']['spark']['map']['cells'][1]=3;assert device.engine.save(json.dumps(external).encode())[0]==200
   await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='revision changed').wait_for();assert device.engine.tune['revision']==4 and device.engine.tune['secondary_tables']['spark']['map']['cells'][1]==3
   checks.append('Blank metadata rejects and stale editor Save returns409 without replacing independently committed secondary cells')
   # Native core observations, not a coupled plant or physical switch test.
   fixture=copy.deepcopy(saved);rule=fixture['secondary_tables']['fuel'];rule.update(mode='input',cells='absolute',debounce_ms=20)
   runtime=EngineRuntime(fixture);records=[]
   try:
    for when in (1000000,1010000,1020000,1040000):
     observed=when+1 if when==1040000 else when
     runtime.step(dict(rpm=1200,synced=True,table_switches=[dict(valid=True,level=True,observed_us=str(observed)),dict(valid=False,level=False,observed_us=str(when))]),when,use_decoder=False)
     if when>=1020000:records.append(runtime.data())
   finally:runtime.close()
   assert records[-1]['secondary_tables']['fuel']['reason']=='input_time_reversed' and records[-1]['secondary_tables']['fuel']['input_observed_us']=='1040001'
   recorder=device.engine.data_recorder;assert recorder.command(dict(action='start',period_ms=20,duration_s=2),1020000)==200
   for record,when in zip(records,(1020000,1040000)):assert recorder.append(record,when)
   recorder.command(dict(action='stop',log_id=1),1040001);h=recorder.header();h['boot_id']=device.engine.data_boot;q=recorder.page(1,0);q['boot_id']=h['boot_id'];native=recorder.msl(1,h['boot_id'])
   result=await page.evaluate('''({h,q})=>{const logger=window.EcuEngineLogger,bad=[];
    for(const [key,value]of [['threshold',null],['debounce_ms',null],['threshold','3000'],['input_observed_us','18446744073709551616'],['mode_code',5],['flags',0],['unexpected',0]]){logger.adopt(h);const p=structuredClone(q);p.records.at(-1).sample.secondary_tables.fuel[key]=value;try{logger.acceptPage(p);bad.push(false)}catch{bad.push(logger.inspect().rows===0&&logger.inspect().cursor===0)}}
    logger.adopt(h);logger.acceptPage(q);return {bad,msl:logger.exportMsl()};}''',dict(h=h,q=q))
   assert all(result['bad']);a=list(csv.reader(io.StringIO(native),delimiter='\t'));b=list(csv.reader(io.StringIO(result['msl']),delimiter='\t'));assert a[2:]==b[2:] and len(b[2])==188
   (out/'native006.msl').write_text(native);(out/'browser006.msl').write_text(result['msl'])
   checks.append('Native/browser188-field MSL006 agree, including future invalid raw timestamp; malformed secondary metadata rejects atomically before cursor publication')
   # DOM fixtures exercise target rendering; they are not target measurements.
   assert device.engine.status()['switch_accessory']['source']=='host_no_target_i2c'
   probe=await page.evaluate('''()=>{const root=document.querySelector('#engine-secondary-panel'),render=e=>{EcuSecondaryTables.status(root,e);return root.querySelector('#switch-accessory-status').textContent};
    const target={simulator:false,switch_accessory:{source:'target_j4_i2c',phase:'retry_wait',requested_mask:3,fault:'i2c_timeout',last_fault:'i2c_timeout',raw_known:true,ready:false,fresh:false,fault_pending:true,fault_id:'18446744073709551615',observed_us:'18446744073709550000',read_completed_us:'18446744073709551000',reads:'9007199254740993',failures:'3',consumed_faults:'2',last_duration_us:3001,max_duration_us:3001,budget_us:3000,bus_allocated:true,sdk_error:263}};
    const fault=render(target);target.switch_accessory.ready=true;target.switch_accessory.fresh=true;target.switch_accessory.fault_pending=false;target.switch_accessory.phase='<img src=x onerror="window.badSwitchMarkup=true">';const recovered=render(target),safe=!root.querySelector('#switch-accessory-status img')&&!window.badSwitchMarkup;
    const unknown=render({simulator:false}),host=render({simulator:true,switch_accessory:{source:'host_no_target_i2c'}});
    return {fault,recovered,safe,unknown,host,guide:root.querySelector('#switch-accessory-guide').textContent};}''')
   assert 'i2c_timeout' in probe['fault'] and '18446744073709551615' in probe['fault'] and '9007199254740993' in probe['fault'] and 'Input rules inhibit' in probe['fault']
   assert 'readback accepted' in probe['recovered'] and 'fresh raw sample' in probe['recovered'] and probe['safe']
   assert 'unknown' in probe['unknown'] and 'synthetic' not in probe['unknown'] and 'synthetic stimuli only' in probe['host']
   assert all(s in probe['guide'] for s in ('pin5 SAFE_N completely unconnected','wire continuity','Closed contact reads high','clock/state fault requires an ECU restart','USB power with carrier3V3'))
   (out/'switch-status-dom-fixtures.json').write_text(json.dumps(probe,indent=2)+'\n')
   checks.append('Switch diagnostic DOM fixtures retain exactU64 text, show fault/recovery separately from qualification, escape markup and keep missing target provenance unknown; explicit host data stays synthetic')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 4').wait_for()
   await page.locator('#switch-accessory-guide').evaluate('e=>e.open=true')
   await page.locator('#toast').evaluate("e=>e.classList.add('hidden')");await page.locator('#engine-secondary-panel').screenshot(path=out/'secondary-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   await page.set_viewport_size({'width':390,'height':1000});await page.locator('#engine-secondary-panel').screenshot(path=out/'secondary-mobile.png')
   checks.append('Secondary controls and map grids fit320/390/768/1440px without document overflow')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors);(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/secondary-integration/ui');a=p.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
