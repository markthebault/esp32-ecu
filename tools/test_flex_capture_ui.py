"""Actual Chrome diagnostics using fixtures from the actual native target services.

The API model does not measure a target or qualify physical capture timing.
"""
import argparse,asyncio,hashlib,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from web_server import R,Device,Handler,load_bridge

async def check(url,fixtures,out):
 results=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#flex-capture').wait_for()
   assert 'Host simulator: no target GPIO38 capture is measured.' in await page.locator('#flex-capture').inner_text()
   results.append('Host status discloses that GPIO38 is not measured')
   qualified=json.loads((fixtures/'qualified.json').read_text())
   for file in sorted(fixtures.glob('*.json')):
    fixture=json.loads(file.read_text())
    text=await page.evaluate('e=>{EcuFlexFuel.status(document.querySelector("#page"),e);return document.querySelector("#flex-capture").textContent}',fixture)
    fresh=file.stem in ('qualified','recovered','ethanol-only','capture-fault-recovered','deadline')
    assert ('publication is current.' in text)==fresh,(file.name,text)
    if file.stem=='capture-fault-unconsumed':assert 'pending low_pulse_width_out_of_range' in text,text
    results.append(file.stem+': qualification and provenance rendered from native service fixture')
   report=await page.evaluate('''e=>{
    const base=e.flex_capture,tests=[];
    const alter=(key,value)=>{const d=structuredClone(base);if(key.startsWith('p.'))d.publication[key.slice(2)]=value;else d[key]=value;return d;};
    for(const key of ['built','available','both_edges','has_hardware_fifo','required','confirmed','binding','active','armed','pending_fault','terminal','retry_holdoff'])tests.push(alter(key,'true'));
    for(const [key,value]of [['schema_version',2],['data_source','synthetic_edges'],['gpio',0],['capture_channel',1],['queued',65],['query_us',0],['query_us','18446744073709551616'],['context','01'],['p.sequence','0'],['p.source','synthetic_edges'],['p.producer_tune_revision',999],['p.context','999'],['p.ingress_generation','999'],['p.capture_generation','999'],['p.armed_after_us','999'],['p.published_us',String(BigInt(base.query_us)+1n)],['p.sample_us',String(BigInt(base.query_us)+1n)],['p.valid_until_us',String(BigInt(base.publication.valid_until_us)+1n)],['p.sample_valid',false],['p.pending_fault',true],['p.reason','stale'],['p.capture_reason','low_pulse_width_out_of_range'],['driver_error','ESP_ERR_INVALID_STATE'],['minimum_command_publication','18446744073709551615'],['fault_generation','1'],['context','0'],['requested_tune_revision',0],['requested_sensor_revision',0],['clock_uncertainty_us',0],['p.producer_calibration',{...base.publication.producer_calibration,low_hz:40}],['p.producer_calibration',null]])tests.push(alter(key,value));
    const checked=tests.map(d=>!EcuFlexFuel.captureText(d,false).includes('publication is current.'));
    const stale=structuredClone(base);stale.query_us=String(BigInt(stale.publication.published_us)+50001n);
    checked.push(EcuFlexFuel.captureText(stale,false).includes('publication is stale'));
    checked.push(EcuFlexFuel.captureText(null,false).includes('unavailable'));
    const injected=structuredClone(e);injected.flex_capture.driver_error='<img src=x onerror="window.flexCaptureMarkup=true">';injected.flex_capture.available=false;injected.flex_capture.active=false;injected.flex_capture.armed=false;
    EcuFlexFuel.status(document.querySelector('#page'),injected);
    checked.push(!document.querySelector('#flex-capture img')&&!window.flexCaptureMarkup);
    return {checks:checked.length,passed:checked.every(Boolean)};
   }''',qualified)
   assert report['passed'],report;results.append(str(report['checks'])+' malformed, stale, missing and escaped-text cases cannot claim a current publication')
   await page.route('**/api/engine/status',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(qualified)))
   await page.evaluate('pollEngine()');assert 'publication is current.' in await page.locator('#flex-capture').inner_text()
   await page.locator('#flex-capture').screenshot(path=out/'capture-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1100});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
   await page.set_viewport_size({'width':390,'height':1100});await page.locator('#flex-capture').screenshot(path=out/'capture-mobile.png')
   await page.unroute('**/api/engine/status');await page.route('**/api/engine/status',lambda route:route.abort())
   await page.evaluate('pollEngine()');assert 'offline; current qualification is unknown' in await page.locator('#flex-capture').inner_text()
   results.append('Actual polling clears current qualification on HTTP failure;320/390/768/1440px fit')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,browser='Installed Chrome via Playwright',qualification=__doc__.strip(),checks=results,page_errors=errors,fixture_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(fixtures.glob('*.json'))},source_sha256={name:hashlib.sha256((R/name).read_bytes()).hexdigest() for name in ('web/index.html','web/flex_fuel.js','web/flex_fuel_logic.js','tools/test_flex_capture_ui.py')})
 (out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--fixture-dir',type=Path,required=True);parser.add_argument('--report-dir',type=Path,required=True);args=parser.parse_args();args.report_dir.mkdir(parents=True,exist_ok=False)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',args.fixture_dir,args.report_dir))
  finally:server.shutdown();thread.join(2)
