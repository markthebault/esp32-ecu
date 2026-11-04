"""Chrome per-cylinder edit/save, migration and complete debug exports."""
import argparse,asyncio,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import R
from engine_msq import import_msq
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 checks=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#cylinder-trims-enabled').wait_for()
   await page.locator('#cylinder-trims-enabled').click();await page.locator('#toast').filter(has_text='Select sequential mode').wait_for();assert not await page.locator('#cylinder-trims-enabled').is_checked();checks.append('Enable requires explicit sequential strategy')
   await page.locator('#eng-strategy').select_option('sequential_4cyl');await page.locator('#cylinder-trims-enabled').check();await page.locator('#cylinder-spark-2').fill('-3');await page.locator('#cylinder-spark-2').dispatch_event('change')
   await page.locator('#cylinder-fuel-map').select_option('1');assert await page.locator('[data-trim-cell]').count()==36
   for input_ in await page.locator('[data-trim-cell]').all():await input_.fill('120');await input_.dispatch_event('change')
   await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for();assert device.engine.tune['cylinder_trims']['fuel_maps'][1]['cells']==[120]*36;checks.append('Cylinder2 map and signed spark offset save through shared validator')
   await page.locator('#engine-run').click();await page.locator('#engine-run-result').filter(has_text='"wrong_stroke_sparks": 0').wait_for();await page.locator('#cylinder-live').filter(has_text='Trims active').wait_for();assert not device.engine.latest['faults'];checks.append('Sequential SIL runs with distinct physical-cylinder proposals')
   async with page.expect_download() as d:await page.locator('#engine-msq').click()
   path=out/'ui-cylinder.msq';await (await d.value).save_as(path);tune=import_msq(path.read_bytes());assert tune==device.engine.tune;checks.append('004 single-page browser MSQ preserves all four trim maps')
   legacy=(R/'tuning/examples/tunerstudio-sequential-roundtrip.msq').read_text()
   parsed=await page.evaluate('text=>engineFromMsq(text,engineTune)',legacy);assert not parsed['cylinder_trims']['enabled'];assert parsed['cylinder_trims']['spark_deg']==[0]*4;assert all(m['cells']==[100]*36 for m in parsed['cylinder_trims']['fuel_maps']);checks.append('002 import into enabled workspace resets absent trim fields to neutral')
   legacy_json=json.loads((R/'config/engine/defaults-v2.json').read_text());parsed=await page.evaluate('value=>upgradeLegacyEngine(value,engineTune)',legacy_json);assert not parsed['cylinder_trims']['enabled'];checks.append('Legacy JSON migration never inherits live trims')
   await page.locator('#engine-data-start').click();await page.wait_for_function('()=>window.EcuEngineLogger.inspect().rows>=119&&!window.EcuEngineLogger.inspect().collecting')
   async with page.expect_download() as d:await page.locator('#engine-data-msl').click()
   path=out/'ui-cylinder.msl';await (await d.value).save_as(path);lines=path.read_text().splitlines();assert len(lines[2].split('\t'))==126 and 'C2FuelTrim' in lines[2];checks.append('Controller log exports per-cylinder demands, masks and base scalars separately')
   await page.locator('#cylinder-live').scroll_into_view_if_needed();await page.screenshot(path=out/'cylinder-desktop.png')
   await page.locator('#cylinder-fuel-map').select_option('1');bad=page.locator('[data-trim-cell="0"]');await bad.fill('151');await bad.dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='Invalid engine tune').wait_for();assert device.engine.tune['revision']==2;checks.append('Out-of-range cylinder trim cannot change persisted tune')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   await page.set_viewport_size({'width':390,'height':1000});await page.locator('#cylinder-fuel-grid').scroll_into_view_if_needed();await page.screenshot(path=out/'cylinder-mobile.png');checks.append('Cylinder controls and grids fit320/390/768/1440 widths')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors);(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=R/'.cache/engine/cylinder-ui');a=parser.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
