"""Actual Chrome paired-screen diagnostics from native radio service fixtures.

Fixtures execute sender code through SDK API models; no real radio or LED.
"""
import argparse,asyncio,hashlib,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from web_server import R,Device,Handler,load_bridge

async def run(url,fixtures,out):
 results=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="screens"]').click();await page.locator('#radio-engine-status').filter(has_text='No ESP-NOW packets').wait_for()
   results.append('Host fixture explicitly discloses no ESP-NOW transmission')
   current=json.loads((fixtures/'partial.json').read_text())
   async def route(request):await request.fulfill(status=200,content_type='application/json',body=json.dumps(current))
   await page.route('**/api/radio',route)
   for name in ('partial','complete','engine-ack-missing','held-expired'):
    current=json.loads((fixtures/(name+'.json')).read_text());await page.evaluate('refreshRadio()');text=await page.locator('#radio-peers').inner_text()
    assert 'Link connected' in text
    if name in ('partial','engine-ack-missing'):assert 'no complete engine observation acknowledged' in text
    else:assert 'complete engine observation ACK ' in text
    if name=='partial':assert 'base submitted, flex submission pending' in text
    if name in ('held-expired','engine-ack-missing'):assert current['led']=='red_blink'
    results.append(name+': link ACK, complete-engine ACK and partial submission are distinct')
   for name in ('schema6-partial-base','schema6-partial-flex','schema6-complete','schema6-downgraded'):
    current=json.loads((fixtures/(name+'.json')).read_text());await page.evaluate('refreshRadio()');text=await page.locator('#radio-peers').inner_text()
    if name=='schema6-downgraded':
     assert 'needs screen schema6' in text and 'sensor stream fallback' in text and 'no complete engine observation acknowledged' in text
    else:
     assert 'engine schema6 / 3 datagrams per observation' in text
     if name=='schema6-complete':assert 'complete engine observation ACK ' in text
     else:
      assert 'no complete engine observation acknowledged' in text
      assert 'last reply' not in text
      assert ('base submitted, flex and boost submission pending' if name.endswith('base') else 'base and flex submitted, boost submission pending') in text
    results.append(name+': complete three-part receipt and legacy upgrade state remain distinct')
   negative=await page.evaluate('''p=>{
    const cases=[];
    for(const [key,value] of [['engine_connected','true'],['last_engine_ack_ms',-1],['last_engine_ack_ms',3000],['last_engine_ack_ms',0.5],['engine_parts_per_observation',1],['engine_pair_pending','false'],['engine_base_submitted',true],['engine_schema',6],['engine_telemetry','true']]){
     const x=structuredClone(p);x[key]=value;cases.push(radioEnginePeerText(x).includes('unknown'));
    }
    const x=structuredClone(p);x.engine_connected=false;cases.push(radioEnginePeerText(x).includes('unknown'));
    cases.push(radioLinkText({...p,connected:'true'}).includes('unknown'));
    cases.push(radioLinkText({...p,connected:true,last_ack_ms:-1}).includes('unknown'));
    cases.push(radioLinkText({...p,connected:false,last_ack_ms:0}).includes('unknown'));
    cases.push(radioLinkText({...p,connected:false,last_ack_ms:18446744073709552000}).includes('unknown'));
    return {count:cases.length,passed:cases.every(Boolean)};
   }''',json.loads((fixtures/'complete.json').read_text())['peers'][0]);assert negative['passed'],negative
   results.append(str(negative['count'])+' malformed ACK/schema/part states stay unknown')
   negative=await page.evaluate('''p=>{
    const cases=[];
    for(const patch of [{engine_next_part:'boost'},{engine_next_part:null},{engine_parts_per_observation:2},{engine_schema:7},{engine_pair_pending:true},{engine_pair_pending:true,engine_base_submitted:true,engine_next_part:'base'},{engine_pair_pending:true,engine_base_submitted:false,engine_next_part:'flex'}])cases.push(radioEnginePeerText({...p,...patch}).includes('unknown'));
    return {count:cases.length,passed:cases.every(Boolean)};
   }''',json.loads((fixtures/'schema6-complete.json').read_text())['peers'][0]);assert negative['passed'],negative
   results.append(str(negative['count'])+' malformed schema6 next-part states stay unknown')
   current=json.loads((fixtures/'complete.json').read_text());current['peers'][0]['name']='<img src=x onerror="window.radioMarkup=true">';await page.evaluate('refreshRadio()');assert not await page.locator('#radio-peers img').count();assert not await page.evaluate('window.radioMarkup||false');results.append('Peer text remains escaped')
   current=json.loads((fixtures/'schema6-partial-flex.json').read_text());await page.evaluate('refreshRadio()');await page.locator('#page').screenshot(path=out/'radio-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
   await page.set_viewport_size({'width':390,'height':1000});await page.locator('#page').screenshot(path=out/'radio-mobile.png')
   await page.unroute('**/api/radio');await page.route('**/api/radio',lambda r:r.abort());await page.evaluate('refreshRadio()')
   assert 'unavailable' in await page.locator('#radio-indicator-status').inner_text();assert 'unknown' in await page.locator('#radio-engine-status').inner_text()
   peer_text=await page.locator('#radio-peers').inner_text();assert 'unknown' in peer_text;assert 'Link connected' not in peer_text;assert 'complete engine observation ACK ' not in peer_text
   results.append('HTTP failure clears readback and engine status;320/390/768/1440px fit')
   assert not errors,errors
  finally:await browser.close()
 report=dict(passed=True,qualification=__doc__.strip(),checks=results,page_errors=errors,fixture_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in fixtures.glob('*.json')},source_sha256={name:hashlib.sha256((R/name).read_bytes()).hexdigest() for name in ('web/index.html','tools/test_flex_radio_ui.py')})
 (out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 with tempfile.TemporaryDirectory() as d,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(d)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(run(f'http://127.0.0.1:{server.server_address[1]}',a.fixtures,a.output))
  finally:server.shutdown();thread.join(2)
