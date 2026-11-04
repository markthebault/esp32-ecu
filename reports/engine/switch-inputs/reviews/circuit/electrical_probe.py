#!/usr/bin/env python3
"""Independent conditional corner arithmetic, not semiconductor guarantees.

All supplies share the stated ground. Vdiode=.4..1 and VBE=.55...95 are
assumptions. A .2V collector is an assumed load point, not a transferred VCEsat
guarantee. Physical leakage, ramps, dynamic injection and thermal tests remain.
"""
import argparse,itertools,json,math
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report-dir',type=Path,required=True);args=parser.parse_args()
out=args.report_dir.resolve();out.mkdir(parents=True,exist_ok=False)
corners=[]
for vdd,vd,vbe,r_bias,r_in,r_be,r_col,r_iso in itertools.product(
 (2.97,3.63),(.4,1),(.55,.95),(2178,2222),(9880.2,10079.8),(99000,101000),(4653,4747),(990,1010)):
 ib=(vdd-vd-vbe)/(r_bias+r_in)-vbe/r_be
 ic=(vdd-.2)/r_col+1e-6
 # Transistor-off resistor divider. Semiconductor current is omitted so this
 # does not establish actual cutoff, only the resistor-derived base bias.
 contact=100
 branch=r_in+r_be;parallel=contact*branch/(contact+branch)
 closed_base=vdd*parallel/(r_bias+parallel)*r_be/branch
 high=vdd-1e-6*(r_col+r_iso)
 corners.append(dict(vdd=vdd,ib=ib,assumed_ic=ic,forced_ratio=ic/ib,closed_base=closed_base,closed_gp_assuming_zero_Qleak=high,high_margin=high-.8*vdd,
  negative_fault_bias_current=(vdd+18)/r_bias,negative_fault_bias_power=(vdd+18)**2/r_bias))
assert len(corners)==256 and min(c['ib'] for c in corners)>0
assert max(c['forced_ratio'] for c in corners)<8.2
assert max(c['closed_base'] for c in corners)<.146
assert min(c['high_margin'] for c in corners)>.588
assert max(c['negative_fault_bias_power']for c in corners)<.215
# Distinct additions in this draft: a mandatory1k bleed,100k reset pullup and
#100ohm SDA/SCL series resistors. Independent resistor-only conservative sums.
vmax=3.63
branches=dict(two_bias=2*vmax/2178,two_collector=2*vmax/4653,bleeder=vmax/990,
 loop=vmax/(990+99000),reset_asserted=vmax/99000,expander_test_bound=.001,
 supervisor_active_test_bound=.00002,gpio_leak_budget=7e-6)
normal=sum(branches.values());i2c=2*vmax/(4653+99)
negative=normal-branches['two_bias']+2*(vmax+18)/2178
# Bus-only steady injection bound assuming no negative diode forward drop,
# no other sources, intact ground and no device sink. This says nothing about
# whether an actual unpowered IC remains reset or its register behavior.
bus_only_rail=vmax*(2*1010)/(4653+99+2*1010)
assert bus_only_rail<1.084
trip_min=2.857
rst_pullup_at_trip=trip_min/99000
assert rst_pullup_at_trip<.0005
report=dict(passed_declared_arithmetic=True,corners=len(corners),physical_qualification=False,
 assumed_open_base_uA=[min(c['ib']for c in corners)*1e6,max(c['ib']for c in corners)*1e6],
 max_required_collector_base_ratio=max(c['forced_ratio']for c in corners),
 max_closed_base_resistor_divider_v=max(c['closed_base']for c in corners),
 min_high_margin_assuming_zero_Q_leak_v=min(c['high_margin']for c in corners),
 negative18_bias_current_per_channel_ma=max(c['negative_fault_bias_current']for c in corners)*1000,
 negative18_bias_power_per_channel_w=max(c['negative_fault_bias_power']for c in corners),
 conservative_normal_branch_sum_ma=normal*1000,branch_terms_ma={k:v*1000 for k,v in branches.items()},
 two_i2c_pullups_low_additional_ma=i2c*1000,
 conservative_two_negative18_branch_sum_ma=negative*1000,
 bus_only_poweroff_rail_upper_bound_under_idealized_assumptions_v=bus_only_rail,
 reset_pullup_current_at_trip_min_uA=rst_pullup_at_trip*1e6,
 reset_low_at1V_specification_load_uA=10,actual100k_lowest_R_pullup_at1V_zero_reset_approx_uA=1/99000*1e6,actual100k_lowest_R_pullup_at1V_point2V_reset_uA=.8/99000*1e6,
 nominal_collector_tau_us=47,nominal_zero_to_0_8vdd_us=-47*math.log(.2),
 caveats=[
  'Input diode and B-E voltage assumptions are not exact-part full-temperature bounds',
  'Forced ratio does not transfer onsemi VCEsat guarantees to sub-mA/full-temperature operation',
  'No Q leakage in closed GP high calculation; actual cutoff/high margin is unqualified',
  'Normal sum deliberately combines mutually exclusive extrema and uses specified chip test-point bounds; no target peak or thermal headroom measurement',
  '±18V remains a proposed common-ground steady bench characterization envelope, not automotive or input qualification',
  'Bus-only floating-rail bound omits contact-related or other injection; actual unpowered IC behavior and loaded reset remain unknown',
  'MCP1210.1uA open-drain leakage is typical only; no guaranteed all-corner released RESET high proof',
  'Revised100k pullup matches the supervisor datasheet test condition; unknown expander RESET leakage and actual ramp/noise margins remain physical holds',
  'MCP23008 at3.3V is limited to the documented -40..85C domain, regardless of E/P marking',
  'I2C100ohm series additions need loaded VOL/rise/fall measurement with actual carrier/harness'
 ])
(out/'electrical-probe.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k]for k in ('passed_declared_arithmetic','corners','conservative_normal_branch_sum_ma','conservative_two_negative18_branch_sum_ma','bus_only_poweroff_rail_upper_bound_under_idealized_assumptions_v')}))
