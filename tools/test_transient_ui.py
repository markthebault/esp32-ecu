"""Installed Chrome: transient tuning, migrations, rejection, CAS and SIL data."""
import argparse,asyncio,copy,csv,io,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_msq import import_msq
from engine_runtime import R
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 checks=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#ae-mode').wait_for()
   assert await page.locator('#ae-mode').input_value()=='legacy_tps'
   await page.locator('#ae-mode').select_option('map_rate');await page.locator('#ae-apply').select_option('add_reference')
   assert 'independently of current MAP/VE/warmup' in await page.locator('#ae-editor-basis').inner_text()
   assert device.engine.tune['transient_enrichment']['mode']=='legacy_tps'
   await page.locator('#ae-duration_ms').fill('');await page.locator('#ae-duration_ms').dispatch_event('change');await page.locator('#engine-save').click()
   await page.locator('#toast').filter(has_text='enter a finite value').wait_for();assert device.engine.tune['revision']==1
   await page.locator('#ae-duration_ms').fill('120');await page.locator('#ae-duration_ms').dispatch_event('change')
   for prefix in ('tps','map'):
    if prefix=='map':await page.locator('summary').filter(has_text='MAP rate curve').click()
    for i,value in enumerate((0,2,4,6)):
     field=page.locator(f'[data-ae-array="{prefix}_added_pct"][data-ae-index="{i}"]');await field.fill(str(value));await field.dispatch_event('change')
   await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   saved=copy.deepcopy(device.engine.tune);assert saved['schema_version']==8 and saved['transient_enrichment']['duration_ms']==120
   checks.append('Default legacy behavior retained; unsaved new mode differs from active; blank value rejects; explicit Save publishes full schema8 tune')
   async with page.expect_download() as d:await page.locator('#engine-msq').click()
   path=out/'transient-browser.msq';await (await d.value).save_as(path);assert import_msq(path.read_bytes())==saved and 'DEV 009' in path.read_text()
   current=await page.evaluate('text=>engineFromMsq(text,engineTune)',path.read_text());assert current==saved
   checks.append('Browser own009 MSQ and native importer preserve complete transient curves and application settings')
   axis=page.locator('[data-ae-array="tps_rates"][data-ae-index="1"]');await axis.fill('0');await axis.dispatch_event('change');await page.locator('#engine-save').click()
   await page.locator('#toast').filter(has_text='Invalid engine tune').wait_for();assert device.engine.tune==saved
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   for old in sorted((R/'tuning/examples').glob('*.msq')):
    if any(identity in old.read_text() for identity in ('ESP32ECU DEV 007 INHIBITED','ESP32ECU DEV 008 INHIBITED','ESP32ECU DEV 009 INHIBITED')):continue
    value=await page.evaluate('text=>engineFromMsq(text,engineTune)',old.read_text())
    assert value['schema_version']==8 and value['transient_enrichment']['mode']=='legacy_tps',old.name
   old=json.loads((R/'config/engine/defaults-v5.json').read_text());old['revision']=2;old['settings']['accel_gain']=.007
   await page.locator('#engine-import-file').set_input_files(dict(name='legacy5.json',mimeType='application/json',buffer=json.dumps(old).encode()))
   await page.locator('#engine-save-state').filter(has_text='Imported edits').wait_for()
   assert await page.locator('#ae-mode').input_value()=='legacy_tps' and await page.locator('#ae-accel_gain').input_value()=='0.007'
   assert device.engine.tune==saved
   checks.append('Malformed curve rejects atomically; old application identities and JSON5 explicitly migrate to legacy AE without saving')
   application=R/'tuning/examples/tunerstudio-transient-roundtrip.msq'
   await page.locator('#engine-import-file').set_input_files(application)
   await page.locator('#engine-save-state').filter(has_text='Imported edits').wait_for()
   assert await page.locator('#ae-mode').input_value()=='map_rate' and await page.locator('#ae-apply').input_value()=='add_reference'
   assert await page.locator('#ae-duration_ms').input_value()=='125.5' and device.engine.tune==saved
   checks.append('Actual TunerStudio007 offline125.5ms edit imports without publication and retains the loaded editor CAS base')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   concurrent=copy.deepcopy(saved);concurrent['transient_enrichment']['duration_ms']=130
   assert device.engine.save(json.dumps(concurrent).encode())[0]==200
   await page.locator('#ae-duration_ms').fill('140');await page.locator('#ae-duration_ms').dispatch_event('change');await page.locator('#engine-save').click()
   await page.locator('#toast').filter(has_text='revision changed').wait_for()
   assert device.engine.tune['revision']==3 and device.engine.tune['transient_enrichment']['duration_ms']==130
   checks.append('Intervening writer causes409; stale form never overwrites the committed tune')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 3').wait_for()
   await page.locator('#engine-run').click();await page.locator('#engine-run-result').filter(has_text='batch_wasted_4cyl').wait_for(timeout=60000)
   await page.locator('#ae-observation').filter(has_text='MAP rate table').wait_for()
   observed=await page.locator('#ae-observation').inner_text();assert 'SYNTHETIC' in observed and 'sensor acquisition window' in observed
   assert device.engine.latest['transient_enrichment']['available'] and not device.engine.status()['physical_outputs_enabled']
   async with page.expect_download() as d:await page.locator('#engine-log').click()
   log=out/'transient-browser.msl';await (await d.value).save_as(log)
   rows=list(csv.reader(io.StringIO(log.read_text()),delimiter='\t'));assert 'SIL 006' in rows[0][0] and len(rows[2])==145 and all(len(r)==145 for r in rows[3:])
   columns=dict(zip(rows[2],rows[-1]));assert columns['AeAvailable']=='1' and columns['AeMode']=='3'
   checks.append('Reduced host plant exposes synthetic acquisition-window observations and exports145-field MSL006 with available flag')
   await page.locator('#engine-transient-panel').screenshot(path=out/'transient-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   checks.append('Transient form and observations fit320/390/768/1440px')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors);(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/transient/ui');a=p.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
