"""Exercise real pairing controls on an owned synthetic host, without RF/devices."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from web_server import Device,Handler,load_bridge


async def check(url,device,output):
    errors=[];checks=[]
    async with async_playwright()as api:
        browser=await api.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
        try:
            page=await browser.new_page(viewport={'width':1440,'height':1050})
            page.on('pageerror',lambda error:errors.append(str(error)))
            await page.goto(url)
            await page.locator('[data-page="screens"]').click()
            await page.wait_for_function('()=>radioState && !document.querySelector("#pair-open").disabled')
            assert device.radio.status()['simulator']is True
            assert device.radio.status()['led']=='green'
            assert not device.radio.peers
            checks.append('Owned host starts with no peers and explicitly synthetic radio/LED status')
            await page.locator('#pair-open').click()
            await page.wait_for_function('()=>radioState?.pairing===true')
            assert device.radio.status()['led']=='blue_blink'
            await page.locator('#pair-cancel').click()
            await page.wait_for_function('()=>radioState?.pairing===false')
            assert device.radio.status()['led']=='green'and device.radio.status()['setup_key']==''
            checks.append('UI opens/cancels pairing; requested blue blink and normal green agree with backend')
            await page.locator('#pair-open').click()
            await page.wait_for_function('()=>radioState?.pairing===true')
            await page.locator('#sim-screen').click()
            await page.locator('#pair-confirm').wait_for()
            await page.locator('#pair-confirm').click()
            await page.wait_for_function('()=>radioState?.peers?.length===1 && radioState.pairing===false')
            peer=device.radio.status()['peers'][0]
            assert peer['connected']is False
            checks.append('Candidate confirmation stores one peer without claiming a physical connection')
            await page.reload()
            await page.locator('[data-page="screens"]').click()
            await page.wait_for_function('()=>radioState?.peers?.length===1')
            assert len(device.radio.peers)==1
            await page.screenshot(path=str(output/'paired-desktop.png'),full_page=True)
            await page.set_viewport_size({'width':390,'height':844})
            assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
            await page.screenshot(path=str(output/'paired-mobile.png'),full_page=True)
            await page.locator('#radio-peers [data-unpair]').click()
            await page.wait_for_function('()=>radioState?.peers?.length===0')
            assert device.radio.peers==[]
            await page.reload()
            await page.locator('[data-page="screens"]').click()
            await page.wait_for_function('()=>radioState && radioState.peers.length===0')
            assert not errors,errors
            checks.append('Reload retains the saved peer; UI unpair persists and desktop/mobile controls work')
        finally:await browser.close()
    (output/'results.json').write_text(json.dumps(dict(passed=True,checks=checks,page_errors=errors,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        qualification=__doc__),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='ecu-checkpoint-radio-')as directory,ThreadingHTTPServer(('127.0.0.1',0),Handler)as server:
        server.device=Device(Path(directory)/'profile.json',load_bridge())
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:asyncio.run(check(f'http://127.0.0.1:{server.server_port}',server.device,args.output))
        finally:server.shutdown();thread.join(5)
