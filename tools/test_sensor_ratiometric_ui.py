"""Actual Chrome calibration editor, legacy runtime and migration checks."""
import argparse
import asyncio
import copy
import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright
from test_sensor_ratiometric import legacy
from web_server import Device, Handler, load_bridge


async def check(url,device,out):
    checks=[];errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
        try:
            page=await browser.new_page(viewport={'width':1440,'height':1100})
            page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(url);await page.locator('#ratiometric').wait_for()
            assert not await page.locator('#ratiometric').is_checked()
            assert await page.locator('#confirmed').is_checked()
            await page.locator('#ratiometric').check()
            assert not await page.locator('#confirmed').is_checked()
            assert 'EDITOR UNCONFIRMED' in await page.locator('#calbadge').inner_text()
            checks.append('Optional ratio mode starts Off and changing basis clears calibration confirmation')
            # Freeze this owned page's polling and inject a source-labelled UI
            # observation. Conversion itself is tested against the actual C++.
            await page.evaluate('''()=>{clearTimeout(pollTimer);online=true;lastReceived=performance.now();
                status.fresh=status.adc_ok=true;status.sample_age_ms=0;status.sensor_5v=4.8;
                status.sensors.find(x=>x.id==='map').sensor_v=2.016;updateLive();}''')
            await page.locator('#f-reference_supply_v').fill('5.1')
            await page.locator('[data-capture="v0"]').click()
            assert await page.locator('#f-v0').input_value()=='2.142'
            await page.locator('#f-reference_supply_v').fill('5')
            await page.locator('[data-capture="v0"]').click()
            assert await page.locator('#f-v0').input_value()=='2.1'
            assert '2.1000 V at 5.00 V supply' in await page.locator('#curve-voltage').inner_text()
            checks.append('Live capture uses unsaved ratio/reference settings, not the old saved conversion basis')
            for mutation in ('lastReceived=performance.now()-2000','status.sensor_5v=0','status.adc_ok=false'):
                await page.evaluate('''mutation=>{lastReceived=performance.now();status.sensor_5v=4.8;status.adc_ok=true;eval(mutation)}''',mutation)
                await page.locator('[data-capture="v0"]').click()
                assert await page.locator('#f-v0').input_value()=='2.1'
                assert 'No fresh ADC sample' in await page.locator('#toast').inner_text()
            checks.append('Stale samples, invalid supply and ADC failure block capture without a raw-voltage fallback')
            await page.locator('#f-v0').fill('.5');await page.locator('#confirmed').check()
            await page.locator('#save').click()
            await page.locator('#toast').filter(has_text='Profile validated and saved').wait_for()
            assert device.profile['schema_version']==2 and device.profile['sensors'][0]['ratiometric']
            assert device.profile['sensors'][0]['confirmed']
            exported=await page.evaluate('()=>structuredClone(profile)')
            (out/'browser-profile2.json').write_text(json.dumps(exported,indent=2)+'\n')
            assert exported==device.profile
            checks.append('A complete ratio calibration persists and roundtrips as sensor profile2')
            old=legacy(device.profile)
            await page.locator('#import-file').set_input_files(dict(name='legacy-profile.json',mimeType='application/json',buffer=json.dumps(old).encode()))
            assert not await page.locator('#ratiometric').is_checked()
            imported=await page.evaluate('()=>structuredClone(profile)')
            assert imported['schema_version']==2 and all(not s['ratiometric'] and s['reference_supply_v']==5 for s in imported['sensors'])
            checks.append('Importing profile1 into an enabled editor explicitly resets every ratio setting to Off')
            await page.locator('#mode').select_option('table');await page.locator('#ratiometric').check()
            assert await page.locator('#f-reference_supply_v').input_value()=='5'
            await page.locator('#mode').select_option('voltage')
            assert await page.locator('#ratiometric').count()==0
            assert not await page.evaluate('()=>profile.sensors[0].ratiometric')
            await page.locator('[data-sensor="clt"]').click();await page.locator('#mode').select_option('linear')
            await page.locator('#ratiometric').check();await page.locator('#mode').select_option('ntc_beta')
            assert not await page.evaluate('()=>profile.sensors[2].ratiometric')
            checks.append('Table mode offers ratio conversion; voltage/NTC transitions clear it to prevent double compensation')
            await page.locator('[data-sensor="map"]').click();await page.locator('#mode').select_option('linear')
            await page.locator('#ratiometric').check()
            await page.locator('#f-unit').fill('kPa')
            assert await page.locator('label[for="f-y0"]').inner_text()=='Point 1 / value (kPa)'
            assert not await page.locator('#confirmed').is_checked()
            await page.locator('#toast').wait_for(state='hidden')
            await page.locator('#conversion').screenshot(path=out/'calibration-desktop.png')
            for width in (320,390,768,1440):
                await page.set_viewport_size({'width':width,'height':1100})
                await page.evaluate('()=>new Promise(requestAnimationFrame)')
                assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'),width
            await page.set_viewport_size({'width':390,'height':1100})
            await page.locator('#conversion').screenshot(path=out/'calibration-mobile.png')
            checks.append('Calibration controls fit320/390/768/1440px without page overflow')
            await page.close()
            # An old running backend can serve the updated HTML while retaining
            # its in-memory profile1/old bridge. Exercise its wire contract.
            old=legacy(device.profile);sent=[]
            async def legacy_wire(route):
                if route.request.method=='PUT':
                    document=route.request.post_data_json;sent.append(document)
                    assert document['schema_version']==1
                    assert all('ratiometric' not in s and 'reference_supply_v' not in s for s in document['sensors'])
                    response=copy.deepcopy(document);response['revision']+=1
                else:response=old
                await route.fulfill(status=200,content_type='application/json',body=json.dumps(response))
            page=await browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            await page.route('**/api/config',legacy_wire);await page.route('**/api/defaults',legacy_wire)
            await page.goto(url);await page.locator('#mode').wait_for()
            assert await page.locator('#ratiometric').count()==0
            await page.locator('#f-y0').fill('11');await page.locator('#save').click()
            await page.locator('#toast').filter(has_text='Profile validated and saved').wait_for()
            assert len(sent)==1
            await page.locator('#import-file').set_input_files(dict(name='profile2.json',mimeType='application/json',buffer=json.dumps(device.profile).encode()))
            assert 'does not support sensor profile2' in await page.locator('#toast').inner_text()
            assert len(sent)==1
            checks.append('An old profile1 backend gets legacy-only saves and rejects profile2 import before sending')
            assert not errors,errors
        finally:await browser.close()
    result=dict(passed=True,browser='Installed Chrome via Playwright',checks=checks,page_errors=errors)
    (out/'ui-tests.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);args=p.parse_args()
    args.report_dir.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as folder,ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
        server.device=Device(Path(folder)/'profile.json',load_bridge())
        profile=copy.deepcopy(server.device.profile);profile['sensors'][0].update(mode='linear',unit='kPa',confirmed=True,y0=10,y1=110)
        assert server.device.save(json.dumps(profile).encode())[0]==200
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:asyncio.run(check(f'http://127.0.0.1:{server.server_address[1]}',server.device,args.report_dir))
        finally:server.shutdown();thread.join(2)
