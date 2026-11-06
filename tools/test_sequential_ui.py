"""Chrome validation of sequential settings, diagnostics and tuning migration."""
import argparse,asyncio,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import R
from engine_msq import import_msq
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 errors=[];checks=[]
 async with async_playwright() as playwright:
  browser=await playwright.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#eng-strategy').wait_for()
   await page.locator('#eng-strategy').select_option('sequential');await page.locator('#eng-order').fill('1, 3, 3, 2');await page.locator('#eng-order').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='Firing order').wait_for();assert device.engine.tune['strategy']=='batch_wasted';checks.append('Duplicate order rejected before publication')
   await page.locator('#eng-order').fill('1, 3, 4, 2');await page.locator('#eng-order').dispatch_event('change');await page.locator('#eng-injection_end_deg').fill('535');await page.locator('#eng-injection_end_deg').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for();assert device.engine.tune['strategy']=='sequential';checks.append('Sequential strategy, order and timing save through native schema')
   await page.locator('#engine-run').click();await page.locator('#engine-run-result').filter(has_text='"wrong_stroke_sparks": 0').wait_for();await page.locator('#engine-live').filter(has_text='phase_locked').wait_for();assert device.engine.latest['phase_synced'];assert device.engine.latest['phase_losses']==0;checks.append('Sequential SIL establishes phase; live diagnostics expose it')
   async with page.expect_download() as download:await page.locator('#engine-msq').click()
   path=out/'ui-sequential.msq';await (await download.value).save_as(path);tune=import_msq(path.read_bytes());assert tune['strategy']=='sequential' and tune['timing']['injection_end_deg']==535
   async with page.expect_download() as download:await page.locator('#engine-log').click()
   path=out/'ui-sequential.msl';await (await download.value).save_as(path);assert 'PhaseSync' in path.read_text();checks.append('007 MSQ and phase-aware MSL exports retain source and configuration')
   await page.screenshot(path=out/'sequential-ui-desktop.png')
   await page.locator('[data-page="triggers"]').click();await page.locator('#trigger-start').click();await page.locator('#trigger-json').wait_for(state='visible');await page.wait_for_function('()=>!document.querySelector("#trigger-json").disabled')
   async with page.expect_download() as download:await page.locator('#trigger-json').click()
   path=out/'ui-sequential-trigger.json';await (await download.value).save_as(path);frame=json.loads(path.read_text());assert frame['includes_cam'] and not frame['includes_falling_edges'];assert any(row['channel']=='cam' for row in frame['records']);checks.append('Synthetic trigger replay includes actual generated cam edges')
   await page.locator('[data-page="engine"]').click();await page.locator('#eng-strategy').wait_for()
   legacy=(R/'tuning/examples/tunerstudio-roundtrip.msq').read_text();decoded=await page.evaluate('text=>engineFromMsq(text,engineTune)',legacy);assert decoded['strategy']=='batch_wasted' and decoded['timing']['injection_end_deg']==540;checks.append('001 migration uses fixed batch defaults even from a sequential editor')
   assert await page.evaluate('()=>{const x=structuredClone(engineTune);x.schema_version=8;try{engineImportShape(x,engineTune);return false}catch{return true}}');checks.append('Unsupported import schema rejected before showing edits')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   checks.append('Sequential forms fit320/390/768/1440 widths')
   assert not errors,errors
  finally:await browser.close()
 report=dict(browser='Installed Chrome via Playwright',checks=checks,page_errors=errors,passed=True);(out/'sequential-ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=R/'.cache/engine/sequential-ui');a=parser.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
