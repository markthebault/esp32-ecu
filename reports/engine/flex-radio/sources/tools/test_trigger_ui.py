#!/usr/bin/env python3
"""Actual Chrome tests for input recording, paging, exports and navigation."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import R
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 errors=[];checks=[]
 async with async_playwright() as playwright:
  browser=await playwright.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport=dict(width=1440,height=1100));page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url+'/#triggers');await page.locator('#trigger-status').filter(has_text='Run a SIL scenario').wait_for()
   assert await page.locator('#trigger-start').is_disabled();checks.append('No synthetic signal is invented before a completed SIL run')
   assert (await asyncio.to_thread(device.engine.run,dict(scenario='warm_start',duration_s=3)))[0]==200
   await page.locator('#trigger-reload').click();await page.locator('#trigger-start').wait_for(state='visible')
   await page.wait_for_function("() => !document.querySelector('#trigger-start').disabled")
   await page.locator('#trigger-samples').select_option('512');await page.locator('#trigger-start').click()
   await page.locator('#trigger-status').filter(has_text='512 / 512').wait_for();await page.wait_for_function("() => !document.querySelector('#trigger-json').disabled")
   assert 'COMPLETED SYNTHETIC SIL' in await page.locator('#trigger-source').inner_text()
   assert 'Not simulated' in await page.locator('#trigger-scope').text_content()
   async with page.expect_download() as download:await page.locator('#trigger-json').click()
   capture=out/'ui-trigger-capture.json';await (await download.value).save_as(capture);frame=json.loads(capture.read_text())
   assert len(frame['records'])==512 and not frame['includes_falling_edges'] and not frame['includes_cam']
   assert [row['sequence'] for row in frame['records']]==list(range(1,513))
   assert all(row['raw_counter'] is None for row in frame['records'])
   checks.append('Eight bounded record pages assemble into a complete source-labelled 512-edge export')
   async with page.expect_download() as download:await page.locator('#trigger-msl').click()
   msl=out/'ui-trigger-capture.msl';await (await download.value).save_as(msl);lines=msl.read_text().splitlines()
   assert len(lines)==516 and 'COMPLETED SYNTHETIC SIL' in lines[1] and all(len(row.split('\t'))==10 for row in lines[4:])
   assert all(row.split('\t')[3:5]==['NaN','NaN'] for row in lines[4:])
   checks.append('MSL export preserves unknown levels and labels synthetic signal provenance')
   await page.locator('#trigger-zoom').evaluate("e => { e.value='6';e.dispatchEvent(new Event('input')); }")
   await page.locator('#trigger-pan').evaluate("e => { e.value='50';e.dispatchEvent(new Event('input')); }")
   assert 'View ' in await page.locator('#trigger-window').inner_text();checks.append('Zoom and pan redraw both diagnostic charts')
   await page.locator('#trigger-zoom').evaluate("e => { e.value='1';e.dispatchEvent(new Event('input')); }")
   await page.screenshot(path=out/'trigger-ui-desktop.png',full_page=True)
   for width in (320,390,768,1440):
    await page.set_viewport_size(dict(width=width,height=1100));await page.evaluate('() => new Promise(requestAnimationFrame)')
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
   await page.set_viewport_size(dict(width=390,height=1100));await page.screenshot(path=out/'trigger-ui-mobile.png',full_page=True)
   checks.append('320/390/768/1440px layouts contain charts and the raw table without document overflow')
   # Replace the recorder after page0 was fetched, before page1 is read.
   replaced=False
   async def replace_mid_download(route):
    nonlocal replaced
    response=await route.fetch()
    if not replaced:
     replaced=True;code,_=device.engine.trigger_command(b'{"action":"start","samples":16,"timeout_ms":1000}');assert code==200
    await route.fulfill(response=response)
   await page.route('**/api/engine/trigger-log?*',replace_mid_download);await page.locator('#trigger-reload').click()
   await page.locator('#trigger-status').filter(has_text='Recorder unavailable').wait_for();assert await page.locator('#trigger-json').is_disabled()
   checks.append('Rearm during paged read disables export instead of mixing frames')
   await page.unroute('**/api/engine/trigger-log?*',replace_mid_download);await page.locator('#trigger-reload').click()
   await page.locator('#trigger-status').filter(has_text='16 / 16').wait_for()
   pending=asyncio.Event();release=asyncio.Event();finished=asyncio.Event()
   async def delayed_metadata(route):
    response=await route.fetch();pending.set();await release.wait();await route.fulfill(response=response);finished.set()
   await page.route('**/api/engine/trigger-log',delayed_metadata);await page.locator('#trigger-reload').click();await asyncio.wait_for(pending.wait(),5)
   await page.locator('[data-page="calibration"]').click();release.set();await asyncio.wait_for(finished.wait(),5)
   await page.evaluate('() => new Promise(requestAnimationFrame)');assert await page.locator('#title').inner_text()=='Sensor calibration'
   assert await page.locator('#trigger-scope').count()==0;checks.append('Delayed capture response cannot replace a different page')
   await page.unroute('**/api/engine/trigger-log',delayed_metadata)
   # Deliberately injected target-shaped fixture, never hardware evidence.
   hardware=dict(frame,frame_id=900,count=0,requested=32,state='armed',records=[],simulator=False,available=True,
                 includes_cam=True,includes_falling_edges=True,data_source='injected_target_ui_test',
                 qualification='INJECTED UI TEST FRAME. No hardware measurement.',diagnostic_interrupts_enabled=True)
   rows=[];levels=dict(crank=False,cam=False)
   for n in range(16):
    stamp=1000+n*200;channel='cam' if n%3==0 else 'crank';levels[channel]=not levels[channel]
    rows.append(dict(sequence=n+1,captured_us=stamp,callback_us=stamp+4,raw_counter=stamp*80,
                     configuration_epoch=7,channel=channel,high=levels[channel],timebase_valid=True))
   async def target_fixture(route):
    if route.request.method=='POST':
     assert route.request.post_data_json==dict(action='stop',frame_id=900);hardware.update(state='stopped',count=16,diagnostic_interrupts_enabled=False)
    body=dict(hardware)
    if '?' in route.request.url:body.update(records=rows,returned=16,offset=0)
    else:body.update(records=[],returned=0,offset=0)
    await route.fulfill(status=200,content_type='application/json',body=json.dumps(body))
   await page.route('**/api/engine/trigger-log**',target_fixture);await page.locator('[data-page="triggers"]').click()
   await page.wait_for_function("() => !document.querySelector('#trigger-stop').disabled")
   await page.locator('#trigger-stop').click();await page.locator('#trigger-state').filter(has_text='STOPPED').wait_for()
   await page.wait_for_function("() => document.querySelectorAll('#trigger-scope path').length === 2")
   assert 'INJECTED UI TEST' in await page.locator('#trigger-source').inner_text()
   assert not await page.locator('#trigger-json').is_disabled();await page.screenshot(path=out/'injected-target-ui.png',full_page=True)
   checks.append('Injected target frame exercises stop, both input channels and falling-edge level display')
   await page.unroute('**/api/engine/trigger-log**',target_fixture)
   assert not errors,errors
  finally:await browser.close()
 report=dict(browser='Installed Google Chrome via Playwright',checks=checks,page_errors=errors,passed=True,
             source_scope='Host completed SIL plus explicitly injected target-shaped UI fixture; no physical board')
 (out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=R/'.cache/engine/trigger-ui');args=parser.parse_args();out=args.report_dir;out.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory:
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.device=Device(Path(directory)/'profile.json',load_bridge())
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,out))
  finally:server.shutdown();server.server_close();thread.join(2)
if __name__=='__main__':main()
