"""Actual Chrome idle settings, safe legacy migration, save rejection and SIL observations."""
import argparse,asyncio,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_msq import import_msq
from engine_runtime import R
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 errors=[];checks=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#idle-algorithm').wait_for()
   await page.locator('#idle-idle_enabled').check();await page.locator('#idle-algorithm').select_option('open_loop')
   for selector,value in [('#idle-frequency_hz','80'),('#idle-tps_closed_pct','1.5'),('[data-idle-array="run_pct"][data-idle-index="4"]','24')]:
    await page.locator(selector).fill(value);await page.locator(selector).dispatch_event('change')
   await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   saved=device.engine.tune;assert saved['settings']['idle_enabled'] and saved['idle_control']['frequency_hz']==80 and saved['idle_control']['run_pct'][4]==24
   checks.append('Enable, mode, frequency, throttle threshold and table edits persist through native whole-tune validation')
   async with page.expect_download() as d:await page.locator('#engine-msq').click()
   path=out/'idle-browser.msq';await (await d.value).save_as(path);decoded=import_msq(path.read_bytes());assert decoded==saved;checks.append('Browser own005 MSQ preserves all idle settings and explicit physical gain units')
   await page.locator('#engine-import-file').set_input_files(R/'tuning/examples/tunerstudio-idle-roundtrip.msq')
   await page.locator('#engine-save-state').filter(has_text='File origin unavailable, editor base 2').wait_for()
   assert await page.locator('#idle-frequency_hz').input_value()=='90' and await page.locator('[data-idle-array="run_pct"][data-idle-index="4"]').input_value()=='17.01'
   assert device.engine.tune==saved;checks.append('Actual application-authored own005 MSQ imports its curve edit and retains the loaded editor CAS base')
   old=json.loads((R/'config/engine/defaults-v3.json').read_text());old['revision']=2;old['settings']['idle_enabled']=True
   await page.locator('#engine-import-file').set_input_files(dict(name='legacy3.json',mimeType='application/json',buffer=json.dumps(old).encode()))
   await page.locator('#engine-save-state').filter(has_text='Imported edits').wait_for()
   assert not await page.locator('#idle-idle_enabled').is_checked() and await page.locator('#idle-frequency_hz').input_value()=='100'
   assert device.engine.tune==saved;checks.append('Legacy JSON disables former virtual idle and restores fixed defaults without inheriting enabled editor values or saving automatically')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   await page.locator('#idle-frequency_hz').fill('');await page.locator('#idle-frequency_hz').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='enter a finite value').wait_for()
   assert device.engine.tune==saved;checks.append('Blank numeric input cannot silently become a saved zero')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   await page.locator('#idle-max_pct').fill('10');await page.locator('#idle-max_pct').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='Invalid engine tune').wait_for()
   assert device.engine.tune==saved and await page.locator('#idle-max_pct').input_value()=='10';checks.append('Invalid duty/curve relationship rejects atomically and retains local edits for correction')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   await page.locator('#engine-run').click();await page.locator('#engine-run-result').filter(has_text='"idle_valve"').wait_for(timeout=60000)
   await page.locator('#idle-observation').filter(has_text='SYNTHETIC valve opening').wait_for();text=await page.locator('#idle-observation').inner_text()
   assert 'Cycle-latched high time' in text and 'Proposed duty' in text
   assert device.engine.last_run['summary']['idle_valve']['edges']>0 and not device.engine.status()['physical_outputs_enabled']
   checks.append('Enabled host SIL uses actual PWM edges; UI separates controller terms, dispatcher observations and synthetic valve state')
   await page.locator('#engine-idle-panel').scroll_into_view_if_needed();await page.screenshot(path=out/'idle-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   checks.append('Idle panel and curve table fit320/390/768/1440px without document overflow')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,checks=checks,page_errors=errors,browser='Installed Chrome via Playwright');(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/idle/idle-ui');a=p.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
