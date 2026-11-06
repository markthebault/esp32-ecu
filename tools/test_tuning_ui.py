"""Actual Chrome own012/legacy import, CAS and read-only transport diagnostics."""
import argparse,asyncio,copy,json,struct,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import R
from engine_msq import export_msq,import_msq
from engine_protocol import Stream,envelope
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 checks=[];errors=[];stream=Stream(device.engine)
 try:
  async with async_playwright() as p:
   browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
   try:
    page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#engine-tuning-status').filter(has_text='native_host_development').wait_for()
    assert 'not measured' in await page.locator('#engine-tuning-status').inner_text();checks.append('Host diagnostics never claim target USB or application presence')
    corrupt=envelope(b'Q');stream.feed(corrupt[:-1]+bytes([corrupt[-1]^1]))
    stream.feed(envelope(b'M'+struct.pack('<BBHH',0,1,640,4)+struct.pack('<f',86)))
    await page.wait_for_function("()=>document.querySelector('#engine-tuning-status').textContent.includes('Staged editsyes')")
    checks.append('Actual native session staging and protocol errors are visible')
    async with page.expect_download() as download:await page.locator('#engine-tuning-export').click()
    file=out/'tuning-diagnostics.json';await (await download.value).save_as(file);data=json.loads(file.read_text());assert data['wire']['crc_errors']=='1' and data['session']['dirty'] and data['driver_rx_drop_count'] is None;checks.append('Diagnostics export preserves counters, source and unknown driver drops')
    tune=copy.deepcopy(device.engine.tune);tune['revision']=999;tune['maps']['ve']['cells'][0]=91.25
    current_msq=export_msq(tune);assert 'ESP32ECU DEV 012 INHIBITED' in current_msq
    await page.locator('#engine-import-file').set_input_files(dict(name='own012.msq',mimeType='application/xml',buffer=current_msq.encode()))
    await page.locator('#engine-save-state').filter(has_text='File origin 999, editor base 1').wait_for();assert await page.evaluate('engineTune.revision')==1
    await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 2').wait_for();assert device.engine.tune['maps']['ve']['cells'][0]==91.25;checks.append('Own012 file origin is metadata, explicit Save uses loaded editor CAS')
    async with page.expect_download() as download:await page.locator('#engine-msq').click()
    file=out/'browser012.msq';await (await download.value).save_as(file);decoded=import_msq(file.read_bytes());assert decoded==device.engine.tune and decoded['schema_version']==11 and 'nPages="1"' in file.read_text() and 'ESP32ECU DEV 012 INHIBITED' in file.read_text()
    import xml.etree.ElementTree as ET
    units={node.get('name'):node.get('units') for node in ET.fromstring(file.read_bytes()).iter() if node.tag.endswith('constant')}
    assert all(units[name]=='' for name in ('boost_pressure_enabled','boost_mode','boost_activation'))
    checks.append('Browser own012 complete-page MSQ roundtrips through native validation with unitless boost choices')
    external=copy.deepcopy(device.engine.tune);external['maps']['ve']['cells'][0]=88;assert device.engine.save(json.dumps(external).encode())[0]==200
    tune['revision']=1000;tune['maps']['ve']['cells'][0]=93
    await page.locator('#engine-import-file').set_input_files(dict(name='another012.msq',mimeType='application/xml',buffer=export_msq(tune).encode()))
    await page.locator('#engine-save-state').filter(has_text='File origin 1000, editor base 2').wait_for();await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='revision changed').wait_for();assert device.engine.tune['revision']==3 and device.engine.tune['maps']['ve']['cells'][0]==88 and await page.evaluate('engineTune.revision')==2;checks.append('Concurrent writer is never silently rebased during file import')
    app=(R/'tuning/examples/tunerstudio-development-roundtrip.msq').read_bytes()
    await page.locator('#engine-import-file').set_input_files(dict(name='actual-app004.msq',mimeType='application/xml',buffer=app))
    await page.locator('#engine-save-state').filter(has_text='File origin unavailable, editor base 2').wait_for();await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='revision changed').wait_for();assert device.engine.tune['revision']==3
    checks.append('Historical own004 application file may omit its origin; missing metadata never rebases stale editor')
    await page.locator('#engine-reload').click();await page.locator('#engine-save-state').filter(has_text='Revision 3').wait_for()
    for name in ('tunerstudio-roundtrip.msq','tunerstudio-sequential-roundtrip.msq','tunerstudio-cylinder-roundtrip.msq','tunerstudio-flex-roundtrip.msq'):
     text=(R/'tuning/examples'/name).read_text();candidate=await page.evaluate('text=>engineFromMsq(text,engineTune)',text);assert candidate['schema_version']==11
     assert candidate['boost_control']['mode']=='off' and not candidate['boost_control']['pressure_enabled']
    checks.append('Historical own001/002/003/010 application-authored MSQs migrate to schema11 with boost disabled')
    app011=(R/'tuning/examples/tunerstudio-boost-roundtrip.msq').read_bytes()
    await page.locator('#engine-import-file').set_input_files(dict(name='actual-app011.msq',mimeType='application/xml',buffer=app011))
    await page.locator('#engine-save-state').filter(has_text='File origin unavailable, editor base 3').wait_for()
    expected=import_msq(app011,base_revision=4)
    await page.locator('#engine-save').click();await page.locator('#engine-save-state').filter(has_text='Revision 4').wait_for()
    assert device.engine.tune==expected
    async with page.expect_download() as download:await page.locator('#engine-msq').click()
    file=out/'browser-actual-app011.msq';await(await download.value).save_as(file)
    assert import_msq(file.read_bytes())==expected
    checks.append('Actual own011 application-edited three-table file imports, saves with editor CAS and exports with every calibration field preserved')
    await page.locator('#engine-tuning-status').scroll_into_view_if_needed();await page.screenshot(path=out/'tuning-desktop.png')
    for width in (320,390,768,1440):
     await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
    checks.append('Diagnostics and own012/legacy import UI fit320/390/768/1440px')
    assert not errors,errors
   finally:await browser.close()
 finally:stream.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors);(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/tuning-ui');a=p.parse_args();a.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,a.report_dir))
  finally:server.shutdown();thread.join(2)
