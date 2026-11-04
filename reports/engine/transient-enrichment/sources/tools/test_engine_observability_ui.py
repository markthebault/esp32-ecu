"""Actual Chrome engine logger collection, exports, identities and gap handling."""
import argparse,asyncio,csv,io,json,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from engine_runtime import R
from web_server import Device,Handler,load_bridge

async def check(url,device,out):
 checks=[];errors=[]
 async with async_playwright() as playwright:
  browser=await playwright.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#engine-data-start').wait_for()
   await page.wait_for_function('()=>!document.querySelector("#engine-data-start").disabled')
   await page.locator('#engine-data-start').click();await page.locator('#toast').filter(has_text='Run a SIL scenario').wait_for();checks.append('No fabricated host log before a completed SIL result')
   await page.locator('#engine-run').click();await page.locator('#engine-run-result').filter(has_text='"executor_stopped": true').wait_for()
   await page.locator('#engine-data-sample').filter(has_text='completed historical replay').wait_for();assert not await page.evaluate('()=>window.EcuEngineLogger.inspect().collecting');checks.append('Coherent completed SIL sample retains historical and age labels')
   await page.locator('#engine-data-start').click();await page.wait_for_function('()=>window.EcuEngineLogger.inspect().rows>=119&&!window.EcuEngineLogger.inspect().collecting')
   count=await page.evaluate('()=>window.EcuEngineLogger.inspect().rows');assert 119<=count<=120;checks.append('100ms native replay collected without gaps through bounded16-row pages')
   async def save(button,name):
    async with page.expect_download() as download:await page.locator(button).click()
    path=out/name;await (await download.value).save_as(path);return path
   msl=await save('#engine-data-msl','browser-collected.msl');data_path=await save('#engine-data-json','browser-collected.json');retained=await save('#engine-data-retained','device-retained.msl')
   collected=json.loads(data_path.read_text());assert not collected['gaps'];assert len(collected['records'])==count
   a=list(csv.reader(io.StringIO(msl.read_text()),delimiter='\t'));b=list(csv.reader(io.StringIO(retained.read_text()),delimiter='\t'))
   assert a[2]==b[2] and a[3]==b[3] and len(a[2])==105 and len(a)==len(b)==count+4
   for x,y in zip(a[4:],b[4:]):
    assert len(x)==len(y)==105
    for left,right in zip(x,y):
     if left=='NaN' or right=='NaN':assert left==right
     else:assert abs(float(left)-float(right))<max(1e-6,abs(float(right))*2e-8),(left,right)
   assert all(row['sample']['source_code']==2 for row in collected['records']);checks.append('Actual browser and native MSL exports agree across105 fields; unknown values stay NaN')
   await page.locator('#engine-data-period').select_option('20');await page.locator('#engine-data-start').click()
   await page.wait_for_function('()=>window.EcuEngineLogger.inspect().identity.log_id===2&&window.EcuEngineLogger.inspect().rows===256&&!window.EcuEngineLogger.inspect().collecting')
   state=await page.evaluate('()=>window.EcuEngineLogger.inspect()');assert state['gaps'][0][0]==1 and state['gaps'][0][1]>=340
   await save('#engine-data-json','browser-gapped.json');await save('#engine-data-msl','browser-gapped.msl');checks.append('20ms replay exposes overwritten prefix and exports exact gap ranges')
   pending=asyncio.Event();release=asyncio.Event();finished=asyncio.Event();held=False
   async def delayed_page(route):
    nonlocal held
    if held:return await route.continue_()
    held=True;response=await route.fetch();pending.set();await release.wait();await route.fulfill(response=response);finished.set()
   await page.route('**/api/engine/data-log?*',delayed_page)
   await page.locator('#engine-data-start').click();await asyncio.wait_for(pending.wait(),5)
   await page.locator('[data-page="diagnostics"]').click();release.set();await asyncio.wait_for(finished.wait(),5)
   await page.wait_for_function('()=>window.EcuEngineLogger.inspect().rows===256&&!window.EcuEngineLogger.inspect().collecting')
   assert await page.locator('#title').inner_text()=='Diagnostics';assert not await page.locator('#engine-data-summary').count()
   await page.unroute('**/api/engine/data-log?*',delayed_page);checks.append('Collection continues across navigation without replacing the current page')
   await page.locator('[data-page="engine"]').click();await page.locator('#engine-data-start').wait_for()
   pending.clear();release.clear();finished.clear();held=False
   await page.route('**/api/engine/data-log?*',delayed_page)
   await page.locator('#engine-data-period').select_option('20');await page.locator('#engine-data-start').click();await asyncio.wait_for(pending.wait(),5)
   h=device.engine.data_log_header();code,new=device.engine.data_log_command(b'{"action":"start","period_ms":20,"duration_s":12}',h['boot_id']);assert code==200
   await page.locator('#engine-data-follow').click();await page.wait_for_function('(id)=>window.EcuEngineLogger.inspect().identity.log_id===id',arg=new['log_id'])
   assert await page.evaluate('()=>window.EcuEngineLogger.inspect().rows')==0
   release.set();await asyncio.wait_for(finished.wait(),5);await page.wait_for_function('()=>window.EcuEngineLogger.inspect().rows===256&&!window.EcuEngineLogger.inspect().collecting')
   race_path=await save('#engine-data-json','identity-race.json');race=json.loads(race_path.read_text());assert all(r['log_id']==new['log_id'] for r in race['records'])
   await page.unroute('**/api/engine/data-log?*',delayed_page);checks.append('Delayed old-log response cannot join a newly followed session')
   # A fully parsed page is committed atomically, even if its last row is bad.
   result=await page.evaluate('''async()=>{
    const x=window.EcuEngineLogger,h=await api('/api/engine/data-log'),p=await api('/api/engine/data-log?log_id='+h.log_id+'&after=0',{headers:{'X-ECU-Log-Boot':h.boot_id}});
    const bad=[];for(const change of [q=>q.boot_id='0'.repeat(32),q=>q.records.at(-1).row_sequence++,q=>q.records.at(-1).sample.control_us='18446744073709551615',q=>q.records.at(-1).sample.sequence='0']){
     x.adopt(h);const q=structuredClone(p);change(q);try{x.acceptPage(q);bad.push(false)}catch{bad.push(x.inspect().rows===0&&x.inspect().cursor===0)}
    }
    x.adopt(h);const q=structuredClone(p);for(let i=0;i<q.records.length;i++)q.records[i].sample.sequence=String(9007199254740993n+BigInt(i));x.acceptPage(q);
    return {bad,exact:x.exportMsl().includes('9007199254740993'),count:x.inspect().rows};
   }''')
   assert all(result['bad']) and result['exact'] and result['count']==16;checks.append('Mixed identities, tail corruption and future observations reject the whole page;64-bit IDs remain exact')
   await page.locator('#engine-data-follow').click();await page.wait_for_function('()=>window.EcuEngineLogger.inspect().rows===256')
   await page.locator('#engine-data-summary').scroll_into_view_if_needed();await page.screenshot(path=out/'engine-log-desktop.png')
   for width in (320,390,768,1440):
    await page.set_viewport_size({'width':width,'height':1000});await page.evaluate('()=>new Promise(requestAnimationFrame)');assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth')
   await page.set_viewport_size({'width':390,'height':1000});await page.locator('#engine-data-summary').scroll_into_view_if_needed();await page.screenshot(path=out/'engine-log-mobile.png');checks.append('Logger and gap controls fit320/390/768/1440 widths')
   await page.locator('[data-page="screens"]').click();await page.locator('#radio-engine-status').filter(has_text='No ESP-NOW packets').wait_for();assert not await page.locator('#engine-data-summary').count();checks.append('Page navigation detaches sample polling; radio fixture does not claim RF sends')
   assert not errors,errors
  finally:await browser.close()
 report=dict(browser='Installed Chrome via Playwright',checks=checks,page_errors=errors,passed=True);(out/'ui-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--report-dir',type=Path,default=R/'.cache/engine/observability-ui');args=parser.parse_args();args.report_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  server.device=Device(Path(directory)/'profile.json',load_bridge());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,args.report_dir))
  finally:server.shutdown();thread.join(2)
