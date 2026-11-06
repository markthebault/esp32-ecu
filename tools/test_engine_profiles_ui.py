"""Actual Chrome profile editing, retained calibration, migration and8-row logs."""
import argparse,asyncio,copy,csv,io,json,math,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import R
from engine_protocol import pages
from engine_msq import import_msq,export_msq
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 checks=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#eng-strategy').wait_for()
   count=page.locator('[data-eng-key="cylinders"]');assert await count.locator('option').count()==8
   await count.select_option('8');await page.locator('#cylinder-spark-8').wait_for();await page.locator('#eng-strategy').select_option('sequential');await page.locator('#cylinder-trims-enabled').check()
   await page.locator('#eng-order').fill('1, 8, 4, 3, 6, 5, 7, 2');await page.locator('#eng-order').dispatch_event('change')
   await page.locator('#cylinder-spark-8').fill('2.5');await page.locator('#cylinder-spark-8').dispatch_event('change');await page.locator('#cylinder-fuel-map').select_option('7')
   await page.locator('[data-trim-cell="17"]').fill('124.25');await page.locator('[data-trim-cell="17"]').dispatch_event('change')
   assert await page.evaluate('engineTune.cylinder_trims.fuel_maps[7].cells[17]')==124.25
   await count.select_option('3');await page.wait_for_function('()=>engineTune.engine.cylinders===3&&document.querySelector("#cylinder-spark-3")&&!document.querySelector("#cylinder-spark-4")')
   assert await page.evaluate('engineTune.cylinder_trims.spark_deg[7]')==2.5;assert await page.evaluate('engineTune.cylinder_trims.fuel_maps[7].cells[17]')==124.25
   await count.select_option('8');await page.locator('#cylinder-spark-8').wait_for();assert await page.locator('#cylinder-spark-8').input_value()=='2.5'
   await page.locator('#eng-order').fill('1, 8, 4, 3, 6, 5, 7, 2');await page.locator('#eng-order').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   tune=copy.deepcopy(device.engine.tune);assert tune['engine']['cylinders']==8 and tune['cylinder_trims']['fuel_maps'][7]['cells'][17]==124.25 and tune['cylinder_trims']['spark_deg'][7]==2.5
   checks.append('Actual count/order/trims editor saves8 cylinders and retains inactive C8 calibration across8→3→8')
   async def download(button,name):
    async with page.expect_download() as result:await page.locator(button).click()
    path=out/name;await(await result.value).save_as(path);return path
   exported=await download('#engine-msq','eight-profile.msq');decoded=import_msq(exported.read_bytes());assert pages(decoded)==pages(tune);assert decoded==tune
   checks.append('Browser own012 full MSQ preserves all223 constants and12288 native page bytes including C8')
   malformed=exported.read_text().replace('name="c8FuelTable" units="%" rows="6" cols="6"','name="c8FuelTable" units="%" rows="1" cols="36"')
   assert malformed!=exported.read_text();failure=await page.evaluate('(text)=>{try{engineFromMsq(text,engineTune);return false;}catch(e){return e.message;}}',malformed);assert 'dimensions' in failure
   for n in range(1,9):
    await count.select_option(str(n));await page.wait_for_function('(n)=>engineTune.engine.cylinders===n&&document.querySelectorAll("#cylinder-fuel-map option").length===n',arg=n)
    assert await page.locator('#eng-order').input_value()==', '.join(str(v) for v in (await page.evaluate('engineTune.timing.firing_order'))[:n])
   checks.append('All eight count choices expose only active editors; malformed declared table dimensions are rejected')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   await page.locator('#engine-run').click();await page.locator('#engine-run-result').filter(has_text='"executor_stopped": true').wait_for();assert device.engine.last_run['summary']['cylinder_sparks'][7]>0
   await page.locator('#engine-data-start').click();await page.wait_for_function('()=>window.EcuEngineLogger.inspect().rows>=119&&!window.EcuEngineLogger.inspect().collecting')
   json_path=await download('#engine-data-json','eight-collected.json');browser_msl=await download('#engine-data-msl','eight-browser.msl');native_msl=await download('#engine-data-retained','eight-native.msl')
   observation=json.loads(json_path.read_text());a=list(csv.reader(io.StringIO(browser_msl.read_text()),delimiter='\t'));b=list(csv.reader(io.StringIO(native_msl.read_text()),delimiter='\t'))
   assert a[2]==b[2] and a[3]==b[3] and len(a[2])==265
   for x,y in zip(a[4:],b[4:]):
    assert len(x)==len(y)==265
    for left,right in zip(x,y):
     assert left==right=='NaN' if left=='NaN' or right=='NaN' else math.isclose(float(left),float(right),rel_tol=2e-8,abs_tol=1e-6)
   last=observation['records'][-1]['sample'];assert last['cylinders']['count']==8 and last['cylinders']['valid_mask']==255 and last['cylinders']['proposals'][7]['fuel_pct'] is not None
   assert 'no fitted drivers' in await page.locator('#page .banner').inner_text()
   checks.append('UI executes eight-cylinder native SIL and browser/native coherent exports agree across265 fields')
   for file in sorted((R/'config/engine').glob('defaults-v*.json')):
    original=json.loads(file.read_text());expected=device.engine.canonical(json.dumps(original).encode())
    candidate=await page.evaluate('(old)=>upgradeLegacyEngine(old,engineTune)',original)
    assert pages(candidate)==pages(expected),file.name
   checks.append('Every preserved legacy JSON default migrates to the same native calibration bytes in Chrome and C++')
   await page.screenshot(path=out/'profiles-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'),width
   await page.set_viewport_size({'width':390,'height':1000});await page.screenshot(path=out/'profiles-mobile.png');checks.append('Eight-cylinder editor and live/log controls fit320/390/768/1440px')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors,physical_outputs_enabled=False)
 (out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,args.output))
  finally:server.shutdown();thread.join(2)
