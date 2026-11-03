#!/usr/bin/env python3
"""Actual Chrome UI regression. Run: uv run --with playwright python tools/test_engine_ui.py"""
import asyncio
import argparse
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_msq import import_msq
from engine_runtime import R
from web_server import Device,Handler,load_bridge


async def check(url,device,report_dir):
 errors=[];checks=[]
 async with async_playwright() as playwright:
  browser=await playwright.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100})
   page.on('pageerror',lambda error:errors.append(str(error)))
   await page.goto(url)
   await page.locator('[data-page="engine"]').click()
   await page.locator('[data-cell]').first.wait_for()
   assert await page.locator('[data-cell]').count()==256
   await page.locator('#engine-import-file').set_input_files(R/'tuning/examples/tunerstudio-roundtrip.msq')
   await page.locator('#engine-save-state').filter(has_text='Imported edits.').wait_for()
   assert await page.locator('[data-cell="0"]').input_value()=='86'
   checks.append('Actual TunerStudio-authored MSQ imports with map orientation preserved')
   await page.locator('#engine-save').click()
   await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   async with page.expect_download() as download:
    await page.locator('#engine-msq').click()
   exported=R/'.cache/engine/ui-export.msq';await (await download.value).save_as(exported)
   decoded=import_msq(exported.read_bytes());assert decoded['revision']==2 and decoded['maps']['ve']['cells'][53]==92.5
   checks.append('Saved browser-exported MSQ passes native validator and lossless revision check')
   await page.locator('#engine-import-file').set_input_files(R/'tuning/examples/tunerstudio-roundtrip.msq')
   await page.locator('#toast').filter(has_text='base revision differs').wait_for()
   checks.append('Stale MSQ is rejected without replacing edits')
   pending=asyncio.Event();release=asyncio.Event();finished=asyncio.Event()
   async def delayed_save(route):
    if route.request.method!='PUT':return await route.continue_()
    response=await route.fetch();pending.set();await release.wait();await route.fulfill(response=response);finished.set()
   await page.route('**/api/engine/config',delayed_save)
   await page.locator('[data-cell="0"]').fill('87');await page.locator('[data-cell="0"]').dispatch_event('change')
   await page.locator('#engine-save').click();await asyncio.wait_for(pending.wait(),5)
   await page.locator('[data-page="diagnostics"]').click();release.set();await asyncio.wait_for(finished.wait(),5)
   await page.locator('#toast').filter(has_text='Engine tune validated and saved').wait_for()
   assert await page.evaluate('() => !engineDirty && engineTune.revision===3')
   assert await page.locator('#title').inner_text()=='Diagnostics'
   assert await page.locator('#engine-save').count()==0
   checks.append('Delayed save response cannot replace another page')
   await page.unroute('**/api/engine/config',delayed_save)
   await page.locator('[data-page="engine"]').click();await page.locator('#engine-reload').wait_for()
   pending.clear();release.clear();finished.clear()
   async def delayed_reload(route):
    response=await route.fetch();pending.set();await release.wait();await route.fulfill(response=response);finished.set()
   await page.route('**/api/engine/config',delayed_reload)
   await page.locator('#engine-reload').click();await asyncio.wait_for(pending.wait(),5)
   await page.locator('[data-page="calibration"]').click();release.set();await asyncio.wait_for(finished.wait(),5)
   await page.evaluate('() => new Promise(requestAnimationFrame)')
   assert await page.locator('#title').inner_text()=='Sensor calibration'
   assert await page.locator('#engine-save').count()==0
   await page.unroute('**/api/engine/config',delayed_reload)
   checks.append('Delayed reload response preserves navigation')
   await page.locator('[data-page="engine"]').click();await page.locator('#engine-run').click()
   await page.locator('#engine-run-result').filter(has_text='"executor_stopped": true').wait_for()
   await page.locator('#engine-live').filter(has_text='Completed SIL snapshot').wait_for()
   async with page.expect_download() as download:
    await page.locator('#engine-log').click()
   msl=R/'.cache/engine/ui-export.msl';await (await download.value).save_as(msl)
   assert 'UNVALIDATED REDUCED-ORDER SIMULATION' in msl.read_text()
   checks.append('SIL runs through UI, historical status is explicit, MSL downloads')
   await page.locator('#engine-timing').filter(has_text='completed_native_sil').wait_for()
   async with page.expect_download() as timing_download:
    await page.locator('#engine-timing-export').click()
   timing_file=report_dir/'ui-timing-export.json';await (await timing_download.value).save_as(timing_file)
   timing=json.loads(timing_file.read_text())
   assert timing['data_source']=='completed_synthetic_sil' and timing['timing']['physical_high_mask']==0
   assert 0<len(timing['events'])<=128
   assert all(a['sequence']<b['sequence'] for a,b in zip(timing['events'],timing['events'][1:]))
   checks.append('Timing trace export is bounded, ordered and explicitly synthetic on host')
   async def target_fault(route):
    response=await route.fetch();body=await response.json()
    body['timing'].update(available=True,mode='hardware_timer_virtual_outputs',fault='late_interrupt',physical_high_mask=0)
    await route.fulfill(response=response,json=body)
   await page.route('**/api/engine/status',target_fault)
   await page.locator('#engine-timing [role="alert"]').filter(has_text='late_interrupt').wait_for()
   await page.screenshot(path=report_dir/'target-timing-fault.png')
   await page.unroute('**/api/engine/status',target_fault)
   checks.append('Target timer fault is visible while physical output mask stays zero')

   await page.screenshot(path=report_dir/'engine-ui-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000})
    await page.evaluate('() => new Promise(requestAnimationFrame)')
    assert await page.evaluate('() => document.documentElement.scrollWidth<=innerWidth'),f'Overflow at {width}px'
   checks.append('320/390/768/1440px layouts have no document overflow')
   with device.engine.lock:device.engine.storage_ok=False;device.engine.error='Injected persistence error; saves blocked'
   await page.locator('#engine-live [role="alert"]').filter(has_text='saves blocked').wait_for()
   checks.append('Persistence failure is visible in engine diagnostics')
   assert not errors,errors
  finally:await browser.close()
 report=dict(browser='Installed Google Chrome via Playwright',checks=checks,page_errors=errors,passed=True)
 (report_dir/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=R/'reports/engine');args=parser.parse_args();args.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge())
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,args.report_dir))
  finally:server.shutdown();thread.join(2)
