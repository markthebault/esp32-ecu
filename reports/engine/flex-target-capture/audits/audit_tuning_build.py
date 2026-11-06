#!/usr/bin/env python3
"""Bind USB transport ownership/source placement to a selected development ELF.

Static inspection only. No USB bus, runtime stack/heap, flash-stall or interrupt
latency measurement is inferred from these checks.
"""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def audit(environment):
 root=R/'firmware';build=BUILD_ROOT/environment
 config=(root/('sdkconfig.'+environment)).read_text()
 commands=json.loads((build/'compile_commands.json').read_text())
 component=root/'components/esp_driver_usb_serial_jtag';metadata=json.loads((component/'upstream.json').read_text())
 hashes={name:digest(component/name) for name in metadata['original_sha256']}
 if any(hashes[name]!=(metadata['patched_source_sha256'] if name=='src/usb_serial_jtag.c' else original) for name,original in metadata['original_sha256'].items()):raise RuntimeError('Pinned component differs beyond recorded patch')
 sdk=Path.home()/'.platformio/packages/framework-espidf/components/esp_driver_usb_serial_jtag'
 if any(digest(sdk/name)!=original for name,original in metadata['original_sha256'].items()):raise RuntimeError('Installed SDK differs from recorded unpatched source')
 driver=[c for c in commands if Path(c['file'])==component/'src/usb_serial_jtag.c']
 if len(driver)!=1:raise RuntimeError('Project-local USB driver override not selected')
 source=(component/'src/usb_serial_jtag.c').read_text()
 if not re.search(r'tx_ring_buf\s*=.*?;\s*if\s*\(p_usb_serial_jtag_obj->tx_ring_buf\s*==\s*NULL\)',source,re.S):raise RuntimeError('TX allocation guard missing')
 if 'esp_intr_alloc(ETS_USB_SERIAL_JTAG_INTR_SOURCE, 0,' not in source:raise RuntimeError('USB ISR allocation flags changed; review required')
 if not all(line in config.splitlines() for line in ['CONFIG_ESP_CONSOLE_UART_DEFAULT=y','CONFIG_ESP_CONSOLE_UART_NUM=0','CONFIG_ESP_CONSOLE_SECONDARY_NONE=y']):raise RuntimeError('USB binary ownership is not exclusive')
 compiler=Path.home()/'.platformio/packages/toolchain-xtensa-esp-elf/bin'
 listing=subprocess.check_output([str(compiler/'xtensa-esp32s3-elf-objdump'),'-t',str(build/'firmware.elf')],text=True)
 isr=[line for line in listing.splitlines() if line.endswith('usb_serial_jtag_isr_handler_default')]
 if len(isr)!=1 or '.flash.text' not in isr[0]:raise RuntimeError('USB ISR placement changed; review required')
 return dict(environment=environment,elf_sha256=digest(build/'firmware.elf'),binary_sha256=digest(build/'firmware.bin'),sdkconfig_sha256=digest(root/('sdkconfig.'+environment)),
  exclusive_usb=True,console='UART0 only',project_driver_source=str(Path(driver[0]['file']).relative_to(R)),project_driver_sha256=hashes['src/usb_serial_jtag.c'],sdk_original_retained=True,
  usb_isr_symbol=isr[0].strip(),usb_isr_cache_safe=False,usb_isr_flags=0,
  source_budgets=dict(rx_ring_bytes=1024,tx_ring_bytes=1024,read_slice_bytes=64,task_stack_bytes=12288,task_cpu=0,task_priority=1,mandatory_yield_ticks=1,send_retry_budget_us=2000),
  qualification='Static ELF/config/source checks only. USB ISR can pause during flash work. Runtime stack/heap, boot/panic traffic, enumeration, driver RX drops, sustained load and physical timing remain unmeasured.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('environment');p.add_argument('output',type=Path);a=p.parse_args();r=audit(a.environment);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
