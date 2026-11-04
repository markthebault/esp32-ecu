#!/usr/bin/python3
"""Conditional RUN source arithmetic; explicitly not a full operating bound."""
from pathlib import Path
import json
out={}
for r in [1800,2200]:
 v=5.25;R47=9500;R50=950;R53=9500;iq=.0005;hct=.00001
 base=v/(r*.99);bleed=v/R47;main=v/(R50+R53)+iq*R53/(R50+R53);total=base+bleed+main+hct
 out[str(r)]=dict(base_emitter_short_a=base,R47_a=bleed,R50_branch_a=main,ten_HCT_inputs_a=hct,total_a=total,margin_to_4mA_a=.004-total)
r=dict(vrun_v=5.25,existing_resistor_tolerance=.05,accessory_R2_tolerance=.01,Q7_current_proxy_a=.0005,Q7_proxy_guaranteed_at_design_voltage_or_full_temperature=False,ST_test_conditions='VIN10V,VDS0V,Tcase25C; fault sink20mA atVIN5V',rows=out)
Path(__file__).with_name('run-loading-probe.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
