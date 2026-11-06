from helpers import *
import asyncio,copy,json,struct,tempfile,threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright
from engine_msq import export_msq,import_msq
from engine_protocol import SIGNATURE,IDLE_SIGNATURE,pages
from web_server import Device,Handler,Reading
cb=ctypes.CDLL(str(OUT/'libconfig.so'));cb.validate_profile.argtypes=[ctypes.c_char_p];cb.validate_profile.restype=ctypes.c_int
cb.evaluate_profile.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_double),ctypes.POINTER(Reading)];cb.evaluate_profile.restype=ctypes.c_int
compact=lambda x:json.dumps(x,separators=(',',':'),allow_nan=False).encode()
async def probe(url,device,path,raw):
 errors=[];checks=[];requests=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  try:
   page=await browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append((r.method,r.url)))
   await page.goto(url);await page.locator('[data-page="engine"]').click();await page.locator('#idle-frequency_hz').wait_for()
   assert path.read_bytes()==raw and await page.evaluate('()=>engineTune.schema_version===5&&engineTune.revision===37&&engineTune.settings.idle_enabled&&engineTune.cylinder_trims.enabled')
   expected_trims=await page.evaluate('()=>structuredClone(engineTune.cylinder_trims)');expected_idle=await page.evaluate('()=>structuredClone(engineTune.idle_control)')
   # Importing schema4 preserves enabled idle/trims and never writes automatically.
   await page.locator('#engine-import-file').set_input_files({'name':'legacy4.json','mimeType':'application/json','buffer':raw})
   await page.wait_for_function('()=>engineDirty&&engineTune.revision===37&&engineTune.schema_version===5')
   assert await page.evaluate('()=>engineTune.cylinder_trims')==expected_trims and await page.evaluate('()=>engineTune.idle_control')==expected_idle and path.read_bytes()==raw
   checks.append('Schema4 import/load upgrades only the in-memory schema and preserves enabled idle, nonneutral trims, revision and raw file')
   await page.locator('#eng-strategy').select_option('semi_sequential_4cyl')
   assert await page.locator('#cylinder-trims-enabled').is_checked() and await page.evaluate('()=>engineTune.cylinder_trims')==expected_trims
   await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='Invalid engine tune').wait_for()
   assert device.engine.tune['revision']==37 and device.engine.tune['strategy']=='sequential_4cyl' and path.read_bytes()==raw
   assert await page.evaluate('()=>engineDirty&&engineTune.cylinder_trims.enabled&&engineTune.strategy==="semi_sequential_4cyl"')
   checks.append('Switch to semi never silently disables enabled trims or loses maps; Save rejects and retains active/file state plus local edits')
   await page.locator('#cylinder-trims-enabled').uncheck();await page.locator('#engine-save').click();await page.wait_for_function('()=>!engineDirty&&engineTune.revision===38')
   assert device.engine.tune['strategy']=='semi_sequential_4cyl' and not device.engine.tune['cylinder_trims']['enabled']
   assert device.engine.tune['cylinder_trims']['fuel_maps']==expected_trims['fuel_maps'] and device.engine.tune['cylinder_trims']['spark_deg']==expected_trims['spark_deg']
   checks.append('Explicit trim disabling commits semi37→38 while retaining all stored nonneutral trim data')
   browser_msq=await page.evaluate('()=>engineToMsq(engineTune)');assert SIGNATURE.decode() in browser_msq and 'Semi-sequential' in browser_msq
   imported=import_msq(browser_msq);assert pages(imported)==pages(device.engine.tune)
   checks.append('Browser006 export passes native MSQ validation and preserves all4992 mapped bytes')
   # Synthetic005 complete tune changes every idle/cylinder field that could be reset accidentally.
   seq=copy.deepcopy(device.engine.tune);seq['strategy']='sequential_4cyl';seq['cylinder_trims']['enabled']=True;seq['revision']=99
   seq['idle_control']['frequency_hz']=90;seq['idle_control']['run_pct'][4]=17.25
   old_msq=export_msq(seq).replace(SIGNATURE.decode(),IDLE_SIGNATURE.decode())
   await page.locator('#engine-import-file').set_input_files({'name':'old005.msq','mimeType':'application/xml','buffer':old_msq.encode()})
   await page.wait_for_function('()=>engineDirty&&engineTune.revision===38&&engineTune.idle_control.frequency_hz===90&&engineTune.cylinder_trims.enabled')
   assert await page.evaluate('()=>engineTune.idle_control.run_pct[4]')==17.25 and await page.evaluate('()=>engineTune.cylinder_trims')==seq['cylinder_trims']
   await page.locator('#engine-save-state').filter(has_text='File origin 99, editor base 38').wait_for()
   await page.locator('#engine-save').click();await page.wait_for_function('()=>!engineDirty&&engineTune.revision===39')
   checks.append('Own005 keeps full idle and trim settings, treats origin as metadata, and saves against the loaded editor CAS base')
   # Only006 may claim the new enum, regardless of otherwise identical pages.
   bad005=browser_msq.replace(SIGNATURE.decode(),IDLE_SIGNATURE.decode())
   assert await page.evaluate('text=>{try{engineFromMsq(text,engineTune);return false}catch(e){return true}}',bad005)
   bad4=json.loads(raw);bad4['strategy']='semi_sequential_4cyl'
   assert await page.evaluate('v=>{try{upgradeLegacyEngine(v,engineTune);return false}catch(e){return true}}',bad4)
   checks.append('Browser rejects enum2 under005 and semi strategy under legacy JSON4')
   # A006 import cannot refresh its loaded editor revision after another writer.
   session=tr.Session(device.engine);assert session.command(b'M'+struct.pack('<BBHH',0,1,640,4)+struct.pack('<f',93))==b'\0';assert session.command(b'b\0\1')==b'\4' and device.engine.tune['revision']==40
   gets=sum(m=='GET' and u.endswith('/api/engine/config') for m,u in requests)
   await page.locator('#engine-import-file').set_input_files({'name':'current006.msq','mimeType':'application/xml','buffer':browser_msq.encode()})
   await page.wait_for_function('()=>engineDirty&&engineTune.revision===39&&engineTune.strategy==="semi_sequential_4cyl"')
   assert sum(m=='GET' and u.endswith('/api/engine/config') for m,u in requests)==gets
   await page.locator('#engine-save').click();await page.locator('#toast').filter(has_text='revision changed').wait_for();assert device.engine.tune['revision']==40 and device.engine.tune['maps']['ve']['cells'][0]==93
   session.close();checks.append('Own006 stale editor CAS remains39 after import and conflicts against native tuning writer40, without hidden fetch/rebase')
   assert not errors,errors
  finally:await browser.close()
 report={'passed':True,'checks':checks,'page_errors':errors,'server_scope':'Private ephemeral localhost port and temporary files, separate from root server; isolated native libraries'}
 (OUT/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
 old=json.loads((R/'config/engine/defaults-v4.json').read_text());old['revision']=37;old['strategy']='sequential_4cyl';old['cylinder_trims']['enabled']=True
 old['settings']['idle_enabled']=True;old['idle_control']['frequency_hz']=80;old['idle_control']['run_pct']=[31,29,27,25,23,21]
 old['cylinder_trims']['spark_deg']=[1.25,-2.5,3.75,-4]
 for i,m in enumerate(old['cylinder_trims']['fuel_maps']):m['cells']=[95+i*5+(c%4)*.25 for c in range(36)]
 with tempfile.TemporaryDirectory(prefix='semi-ui-review-') as td,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
  profile=Path(td)/'profile.json';path=profile.with_name(profile.name+'.engine');raw=json.dumps(old,indent=1).encode();path.write_bytes(raw)
  server.device=Device(profile,cb);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:asyncio.run(probe(f'http://127.0.0.1:{server.server_address[1]}',server.device,path,raw))
  finally:server.shutdown();thread.join(2)
