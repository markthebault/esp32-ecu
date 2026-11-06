"""Chrome semi strategy, migration, trim rejection, exports and source labels."""
import argparse,asyncio,copy,json,tempfile,threading
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
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#eng-strategy').wait_for()
   await page.locator('#eng-strategy').select_option('semi_sequential')
   contract=await page.locator('#engine-cycle-summary').inner_text()
   assert 'Logical injector / coil IDs' in contract and '540° repeats at 180°' in contract and 'Dead time is added once per opening' in contract
   assert await page.locator('#engine-cycle-summary tbody tr').count()==4
   phases=await page.locator('#engine-cycle-summary tbody tr').evaluate_all('(rows)=>rows.map(r=>[r.cells[1].textContent,r.cells[2].textContent])')
   assert phases==[['0.000°','0.000°'],['540.000°','180.000°'],['180.000°','180.000°'],['360.000°','0.000°']]
   await page.locator('#engine-live').filter(has_text='batch_wasted').wait_for();checks.append('Unsaved semi contract derives pairs and modulo360 reference separately from active strategy')
   await page.locator('#eng-injection_end_deg').fill('');await page.locator('#eng-injection_end_deg').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='enter a finite value').wait_for()
   assert device.engine.tune['strategy']=='batch_wasted'
   await page.locator('#eng-injection_end_deg').fill('540');await page.locator('#eng-injection_end_deg').dispatch_event('change');await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for()
   saved=copy.deepcopy(device.engine.tune);assert saved['schema_version']==11 and saved['strategy']=='semi_sequential'
   checks.append('Blank timing rejects without publication; explicit Save validates semi through native schema11')
   async with page.expect_download() as d:await page.locator('#engine-msq').click()
   msq=out/'semi-browser.msq';await (await d.value).save_as(msq);assert import_msq(msq.read_bytes())==saved and 'DEV 012' in msq.read_text()
   checks.append('Browser own012 complete-page MSQ retains mode and all settings through native roundtrip')
   await page.locator('#eng-strategy').select_option('sequential');await page.locator('#cylinder-trims-enabled').check()
   await page.locator('#cylinder-spark-2').fill('-3');await page.locator('#cylinder-spark-2').dispatch_event('change')
   await page.locator('#eng-strategy').select_option('semi_sequential');assert await page.locator('#cylinder-trims-enabled').is_checked()
   await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='Invalid engine tune').wait_for();assert device.engine.tune==saved
   await page.locator('#cylinder-trims-enabled').uncheck();await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 3').wait_for()
   assert device.engine.tune['cylinder_trims']['spark_deg'][1]==-3 and not device.engine.tune['cylinder_trims']['enabled']
   checks.append('Paired mode does not silently disable trims; rejection is atomic and explicit disable preserves stored trim values')
   legacy=(R/'tuning/examples/tunerstudio-idle-roundtrip.msq').read_text()
   candidate=await page.evaluate('text=>engineFromMsq(text,engineTune)',legacy)
   assert candidate['schema_version']==11 and candidate['idle_control']['frequency_hz']==90
   old=json.loads((R/'config/engine/defaults-v4.json').read_text());old['revision']=3;old['settings']['idle_enabled']=True;old['idle_control']['frequency_hz']=80
   await page.locator('#engine-import-file').set_input_files(dict(name='legacy4.json',mimeType='application/json',buffer=json.dumps(old).encode()))
   await page.locator('#engine-save-state').filter(has_text='Imported edits').wait_for();assert await page.locator('#idle-idle_enabled').is_checked() and await page.locator('#idle-frequency_hz').input_value()=='80'
   assert device.engine.tune['revision']==3;checks.append('Historical005 and JSON4 preserve idle values when migrating; file import does not save')
   await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 3').wait_for()
   await page.locator('#engine-run').click();await page.locator('#engine-run-result').filter(has_text='semi_sequential').wait_for(timeout=60000)
   await page.locator('#engine-live').filter(has_text='not required for current strategy').wait_for()
   assert not device.engine.latest['phase_required'] and device.engine.last_run['summary']['sync_acquired'] and not device.engine.last_run['cam_edges']
   for a,b in ((0,3),(1,2)):
    edges=device.engine.last_run['edges'];assert [(row[0],row[2]) for row in edges if row[1]==a]==[(row[0],row[2]) for row in edges if row[1]==b]
   async with page.expect_download() as d:await page.locator('#engine-log').click()
   msl=out/'semi-browser.msl';await (await d.value).save_as(msl);assert 'semi_sequential' in msl.read_text() and not device.engine.status()['physical_outputs_enabled']
   checks.append('Reduced host plant runs from paired executed edges without cam, exposes source/phase labels and exports MSL')
   await page.screenshot(path=out/'semi-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   await page.locator('[data-page="guides"]').click();await page.locator('#guide-select').select_option('J9 / J10 semi-sequential');guide=await page.locator('#page').inner_text()
   assert 'Never bridge' in guide and 'overlap above50' in guide and 'J19' in guide
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   checks.append('Strategy form and hardware/debug guide fit320/390/768/1440px')
   original=device.radio.status
   def old_screen():
    status=original();status['peers']=[dict(mac='02:EC:00:00:00:02',name='Synthetic old screen',connected=False,last_ack_ms=-1,engine_telemetry=True,engine_schema=1,engine_telemetry_blocked=True,engine_upgrade_needed=True,engine_parts_per_observation=1,engine_pair_pending=False,engine_base_submitted=False,engine_connected=False,last_engine_ack_ms=-1),dict(mac='02:EC:00:00:00:03',name='Synthetic new screen',connected=True,last_ack_ms=0,engine_telemetry=True,engine_schema=2,engine_telemetry_blocked=False,engine_upgrade_needed=False,engine_parts_per_observation=1,engine_pair_pending=False,engine_base_submitted=False,engine_connected=False,last_engine_ack_ms=-1)];return status
   device.radio.status=old_screen
   await page.locator('[data-page="screens"]').click();await page.locator('#radio-peers').filter(has_text='update screen firmware for current engine data').wait_for()
   assert 'engine schema2' in await page.locator('#radio-peers').inner_text() and (await page.locator('#radio-peers').inner_text()).count('update screen firmware')==1
   checks.append('Synthetic legacy-screen compatibility warning is visible separately from connection state')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors);(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/semi/ui');a=p.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
