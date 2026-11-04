"""Select exclusive binary USB ownership in the two development web builds.

Only generated Linux sdkconfigs are normalized. Original bytes are retained in
the ignored task cache; tracked defaults provide the same choice to fresh builds.
"""
Import('env')
from pathlib import Path
import hashlib
if env['PIOENV'] in ('compact_n16r8_web','compact_a3_web','compact_n16r8_flex_dev'):
 root=Path(env['PROJECT_DIR']);path=root/('sdkconfig.'+env['PIOENV'])
 if path.is_symlink():raise RuntimeError('Preserve legacy sdkconfig symlinks and select a fresh Linux generated sdkconfig before USB tuning')
 if path.exists():
  data=path.read_bytes();text=data.decode()
  if 'CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y' in text:
   backup=root.parent/'.cache/engine/tuning-sdkconfigs';backup.mkdir(parents=True,exist_ok=True)
   saved=backup/(path.name+'-'+hashlib.sha256(data).hexdigest()+'.before')
   if not saved.exists():saved.write_bytes(data)
   text=text.replace('CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y','# CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG is not set').replace('# CONFIG_ESP_CONSOLE_SECONDARY_NONE is not set','CONFIG_ESP_CONSOLE_SECONDARY_NONE=y')
   if 'CONFIG_ESP_CONSOLE_SECONDARY_NONE=y' not in text:text+='\nCONFIG_ESP_CONSOLE_SECONDARY_NONE=y\n'
   path.write_text(text)
