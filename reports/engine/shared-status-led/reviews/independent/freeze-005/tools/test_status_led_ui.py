"""Owned Chrome replay of actual-service mocked-I2C fixtures and bad payloads."""
import argparse
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.async_api import async_playwright
from web_server import Device, Handler, load_bridge


async def check(url, device, fixtures, output):
    errors, results = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 1050})
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(url)
            await page.locator('[data-page="screens"]').click()
            await page.wait_for_function("document.querySelector('#radio-indicator-status')?.textContent.includes('Host fixture')")
            assert device.radio.status()["indicator"]["source"] == "host_no_target_i2c"
            results.append("Host fixture explicitly has no measured LED/expander")
            base = device.radio.status()
            base.update(simulator=False, available=True, storage_ok=True, engine_data_source="native_SDK_model_fixture")
            response = copy.deepcopy(base)

            async def route(request):
                await request.fulfill(status=200, content_type="application/json", body=json.dumps(response, allow_nan=False))

            await page.route("**/api/radio", route)
            for name in ("green_ready", "led_timeout", "led_recovered", "shared_bus_fault", "bus_recovered", "stale_latch"):
                response = copy.deepcopy(base)
                response["indicator"] = json.loads((fixtures / (name + ".json")).read_text())
                await page.evaluate("refreshRadio()")
                text = await page.locator("#radio-indicator-status").inner_text()
                if name in ("green_ready", "led_recovered", "bus_recovered"):
                    assert "Expander latch verified green" in text, (name, text)
                else:
                    assert "Expander latch verified" not in text and "Historical latch" in text, (name, text)
                assert "Advisory" in text and "unproven" in text
                results.append({"fixture": name, "text": text})
            target = copy.deepcopy(base)
            target["indicator"] = json.loads((fixtures / "green_ready.json").read_text())
            corruptions = await page.evaluate("""r=>{
              const mutations=[
                ['ready_string',i=>i.ready='true'],['fresh_string',i=>i.fresh='true'],
                ['known_string',i=>i.known='true'],['allocated_string',i=>i.device_allocated='true'],
                ['error_string',i=>i.sdk_error='0'],['error_nan',i=>i.sdk_error=NaN],
                ['error_range',i=>i.sdk_error=2147483648],['fault_contradiction',i=>i.fault='configuration_mismatch'],
                ['prototype',i=>i.requested_pattern='__proto__'],['constructor',i=>i.serviced_pattern='constructor'],
                ['object_pattern',i=>i.requested_pattern={}],['wrong_pattern_color',i=>i.serviced_pattern=i.requested_pattern='blue_blink'],
                ['bad_mask',i=>i.last_verified_latch=5],['string_mask',i=>i.requested_rgb='2'],
                ['unverified_write',i=>i.last_written_rgb=0],['wrong_phase',i=>i.phase='retry_wait'],
                ['numeric_time',i=>i.observed_us=Number(i.observed_us)],['leading_zero',i=>i.observed_us='0'+i.observed_us],
                ['u64_overflow',i=>i.snapshot_us='18446744073709551616'],
                ['future_read',i=>i.observed_us=(BigInt(i.snapshot_us)+1n).toString()],
                ['future_completion',i=>i.read_completed_us=(BigInt(i.snapshot_us)+1n).toString()],
                ['reversed_completion',i=>i.read_completed_us=(BigInt(i.observed_us)-1n).toString()],
                ['stale_ready',i=>i.snapshot_us=(BigInt(i.observed_us)+250001n).toString()],
                ['wrong_contract',i=>i.contract='other'],['wrong_source',i=>i.source='host_no_target_i2c']
              ];
              return mutations.map(([name,mutate])=>{const copy=structuredClone(r);mutate(copy.indicator);return {name,text:radioIndicatorText(copy)}});
            }""", target)
            assert all("Expander latch verified" not in row["text"] for row in corruptions)
            results.append({"rejected_malformed_ready_payloads": corruptions})
            huge = copy.deepcopy(target)
            huge["indicator"].update(observed_us="9007199254740993", read_completed_us="9007199254742593", snapshot_us="9007199254742993")
            assert "verified green, 2.0 ms" in await page.evaluate("r=>radioIndicatorText(r)", huge)
            legacy = await page.evaluate("()=>radioIndicatorText({simulator:false,led:'green'})")
            assert "Hardware readback is unavailable" in legacy and "verified" not in legacy
            unknown = copy.deepcopy(target)
            unknown["indicator"].update(known=False, ready=False, fresh=False)
            assert "Latch unknown" in await page.evaluate("r=>radioIndicatorText(r)", unknown)
            # Display text remains literal, even for an unexpected fault string.
            response = copy.deepcopy(target)
            response["indicator"].update(ready=False, fresh=False, fault='<img src=x onerror="window.badLED=true">')
            await page.evaluate("refreshRadio()")
            assert not await page.locator("#radio-indicator-status img").count()
            assert not await page.evaluate("Boolean(window.badLED)")
            response = copy.deepcopy(target)
            await page.evaluate("refreshRadio()")
            await page.evaluate("""()=>{const note=document.createElement('div');note.textContent='UI replay: actual service with mocked I2C SDK. No hardware or optical measurement.';note.style.cssText='background:#ffd966;color:#191919;padding:12px;font-weight:700';document.body.prepend(note)}""")
            await page.screenshot(path=str(output / "led-desktop.png"), full_page=True)
            await page.set_viewport_size({"width": 390, "height": 844})
            assert await page.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
            await page.screenshot(path=str(output / "led-mobile.png"), full_page=True)
            await page.unroute("**/api/radio", route)
            async def unavailable(request):
                await request.abort()
            await page.route("**/api/radio", unavailable)
            await page.evaluate("refreshRadio()")
            assert "Previous latch status is unverified" in await page.locator("#radio-indicator-status").inner_text()
            assert await page.locator("#pair-open").is_disabled()
            assert not errors, errors
            results.append("U64 ages, unknown/legacy sources, literal fault markup, failed-poll clearing and mobile overflow passed")
        finally:
            await browser.close()
    (output / "results.json").write_text(json.dumps({"passed": True, "scope": "native_SDK_model_UI_replay_not_physical_LED", "results": results, "page_errors": errors}, indent=2) + "\n")
    print("Actual-service mocked-I2C fixtures,25 malformed payloads and owned Chrome desktop/mobile checks passed")


def main(fixtures, output):
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="ecu-led-ui-") as temporary:
        device = Device(Path(temporary) / "state.json", load_bridge())
        class OwnedHandler(Handler):
            pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), OwnedHandler)
        server.device = device
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            asyncio.run(check("http://127.0.0.1:" + str(server.server_port), device, fixtures, output))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    main(arguments.fixtures, arguments.output)
