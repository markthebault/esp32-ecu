#!/usr/bin/env python3
"""Actual Chrome boost editor, file exchange and persistent CAS transactions."""
import argparse,asyncio,hashlib,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import R
from engine_msq import import_msq
from web_server import Device,Handler,load_bridge

SOURCES=('web/index.html','web/boost_control.js','web/boost_control_logic.js','web/idle_control.js','web/idle_control_logic.js','web/load_model.js','web/secondary_tables.js','config/interface-guide.json','config/interface-guide-development.json','tools/engine_msq.py','tools/test_boost_ui.py')
def hashes():return {name:hashlib.sha256((R/name).read_bytes()).hexdigest() for name in SOURCES}

async def check(url,device,out):
 before=hashes();checks=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#boost-mode').wait_for()
   assert not await page.locator('#boost-pressure_enabled').is_checked();assert await page.locator('#boost-mode').input_value()=='off'
   assert await page.locator('[data-boost-cell]').count()==64;checks.append('New and migrated defaults retain NA protection and disabled valve control')
   await page.locator('#engine-boost-panel details summary').first.click()
   panel=await page.locator('#engine-boost-panel').inner_text()
   assert 'boost telemetry format6' in panel and 'The screen format needs an extension' not in panel
   assert 'J21 ZH5' in panel and 'J3 VH6' in panel and 'physical boost writes disabled' in panel
   guide=(await (await page.request.get(url+'/api/guide')).json())
   assert guide['guide_version']=='1.11'
   boost_guide=next(row for row in guide['services'] if row['title']=='Boost valve connection and diagnostics')
   assert any('pins5,2,3,4' in text for text in boost_guide['checks'])
   await page.locator('[data-page="guides"]').click()
   await page.locator('#guide-select').select_option(boost_guide['connector'])
   await page.get_by_role('heading',name='Boost valve connection and diagnostics',exact=True).wait_for()
   await page.locator('[data-page="engine"]').click()
   await page.locator('#boost-mode').wait_for()
   checks.append('Actual boost and connector-guide views agree on the A7 shared harness, inhibition and current boost-capable screen format')
   await page.locator('#boost-pressure_enabled').check();await page.locator('#boost-mode').select_option('open_loop')
   assert await page.locator('[data-axis="load"]').last.get_attribute('max')=='300'
   await page.locator('[data-axis="load"]').last.fill('250');await page.locator('[data-axis="load"]').last.dispatch_event('change')
   await page.locator('[data-boost-cell="0"]').fill('25.5');await page.locator('[data-boost-cell="0"]').dispatch_event('change')
   await page.locator('[data-boost-cell="17"]').fill('43.75');await page.locator('[data-boost-cell="17"]').dispatch_event('change')
   await page.locator('#boost-table-kind').select_option('target');await page.locator('[data-boost-cell="9"]').fill('160.25');await page.locator('[data-boost-cell="9"]').dispatch_event('change')
   await page.locator('#boost-table-kind').select_option('feedforward');await page.locator('[data-boost-cell="38"]').fill('22.5');await page.locator('[data-boost-cell="38"]').dispatch_event('change')
   await page.locator('#sec-fuel-condition').select_option('map_kpa');await page.locator('#sec-fuel-threshold').fill('180');await page.locator('#sec-fuel-threshold').dispatch_event('change')
   await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   saved=device.engine.tune;assert saved['schema_version']==10 and saved['boost_control']['pressure_enabled'];assert saved['maps']['ve']['load'][-1]==250
   assert saved['boost_control']['open_duty']['cells'][17]==43.75 and saved['boost_control']['target']['cells'][9]==160.25 and saved['boost_control']['feedforward']['cells'][38]==22.5
   assert saved['secondary_tables']['fuel']['threshold']==180;checks.append('All three boost tables, contextual fuel axis and secondary MAP threshold persist through the native whole-tune validator')
   async with page.expect_download() as pending:await page.locator('#engine-msq').click()
   msq=out/'browser-boost.msq';await (await pending.value).save_as(msq);assert import_msq(msq.read_bytes())==saved
   checks.append('Browser own011 MSQ passes native import with row/column orientation and all boost settings preserved')
   await page.locator('#boost-cut_kpa').evaluate('(e)=>e.dataset.reloadMarker=1');await page.locator('#engine-reload').click();await page.locator('#boost-cut_kpa:not([data-reload-marker])').wait_for();assert await page.locator('#boost-pressure_enabled').is_checked()
   await page.locator('#boost-cut_kpa').fill('150');await page.locator('#boost-cut_kpa').dispatch_event('change');await page.locator('#engine-save').click()
   rejection=await page.locator('#toast').inner_text();assert 'axes must ascend and cells must respect pressure/duty limits' in rejection,rejection;assert device.engine.tune==saved
   checks.append('Inconsistent target/cut calibration is rejected while active tune and stored bytes stay unchanged')
   await page.locator('#boost-cut_kpa').evaluate('(e)=>e.dataset.reloadMarker=1');await page.locator('#engine-reload').click();await page.locator('#boost-cut_kpa:not([data-reload-marker])').wait_for();assert await page.locator('#boost-cut_kpa').input_value()=='220'
   legacy=json.loads((R/'config/engine/defaults-v9.json').read_text());legacy['revision']=2;legacy_path=out/'legacy-schema9.json';legacy_path.write_text(json.dumps(legacy))
   await page.locator('#engine-import-file').set_input_files(legacy_path);await page.locator('#engine-save-state').filter(has_text='Imported edits.').wait_for()
   assert not await page.locator('#boost-pressure_enabled').is_checked();assert await page.locator('#boost-mode').input_value()=='off';assert device.engine.tune==saved
   await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 3').wait_for();assert not device.engine.tune['boost_control']['pressure_enabled']
   checks.append('Legacy JSON import explicitly resets boost and keeps source bytes, then saves with the loaded CAS revision')
   await page.locator('#engine-import-file').set_input_files(msq);await page.locator('#engine-save-state').filter(has_text='Imported edits.').wait_for();assert await page.locator('#boost-pressure_enabled').is_checked()
   # Another writer wins while these imported edits retain their loaded origin.
   other=dict(device.engine.tune);code,_=device.engine.save(json.dumps(other).encode());assert code==200;active=device.engine.tune;stored=device.engine.path.read_bytes()
   await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='revision').wait_for();assert device.engine.tune==active and device.engine.path.read_bytes()==stored
   assert await page.locator('#boost-pressure_enabled').is_checked();checks.append('Stale save cannot overwrite another writer or silently rebase imported boost edits')
   await page.locator('#engine-boost-panel').scroll_into_view_if_needed();await page.screenshot(path=out/'boost-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   await page.set_viewport_size({'width':390,'height':1000});await page.locator('#engine-boost-panel').scroll_into_view_if_needed();await page.screenshot(path=out/'boost-mobile.png');checks.append('Boost controls and horizontally scrollable tables fit 320/390/768/1440px')
   assert not errors,errors
  finally:await browser.close()
 assert hashes()==before,'Browser sources changed during acceptance run'
 report=dict(passed=True,browser='Installed Chrome via Playwright',qualification=__doc__.strip(),checks=checks,page_errors=errors,source_sha256=before)
 (out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 with tempfile.TemporaryDirectory() as d,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(d)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,args.output))
  finally:server.shutdown();thread.join(2)
