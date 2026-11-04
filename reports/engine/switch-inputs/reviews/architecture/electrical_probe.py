"""Independent KCL/corner arithmetic for the owner's candidate; no device model qualification."""
import itertools,json,math
from pathlib import Path
out=Path(__file__).resolve().parent
corners=[]
for vdd,vd,vbe,rbias,rb1,rb2,rbe,rc in itertools.product((2.97,3.63),(0.4,1.0),(0.55,0.95),(2178,2222),(4940.1,5039.9),(4940.1,5039.9),(99000,101000),(4653,4747)):
 rb=rb1+rb2;ib=max(0,(vdd-vd-vbe)/(rbias+rb)-vbe/rbe)
 # VCE=.2 is an assumption for demand arithmetic, NOT a transferred saturation guarantee.
 ic=(vdd-.2)/rc;corners.append(dict(vdd=vdd,vd=vd,vbe=vbe,rbias=rbias,rb=rb,rbe=rbe,rc=rc,base_uA=ib*1e6,collector_uA=ic*1e6,forced_beta=ic/ib))
closed=[]
for vdd,vd,rbias,rb,rbe,rcontact in itertools.product((2.97,3.63),(0,1.0),(2178,2222),(9880.2,10079.8),(99000,101000),(0,100)):
 load=rb+rbe
 if rcontact:load=1/(1/load+1/rcontact)
 else:load=0
 vsw=(vdd-vd)*load/(rbias+load);vb=vsw*rbe/(rb+rbe);closed.append(dict(vdd=vdd,vd=vd,contact_ohm=rcontact,vsw=vsw,vbase=vb))
# Conservative fault bound intentionally gives the feed diode zero drop.
vmax=3.63;vin=18;rf=2178;rb=9880.2
negative=dict(vin=-vin,rail_current_per_channel_A=(vmax+vin)/rf,rail_current_two_A=2*(vmax+vin)/rf,rbias_power_W=(vmax+vin)**2/rf,base_clamp_current_bound_A=vin/rb,base_resistor_total_power_bound_W=vin*vin/rb)
positive=dict(vin=vin,base_current_upper_bound_A=vin/rb,bias_diode_reverse_voltage_upper_bound_V=vin,bias_diode_leak_25C_A=25e-9,bias_diode_leak_150C_A=50e-6)
# I2C30..70% rise: tr=.8473*Rp*C. Existing carrier pullups already4.7k.
bus=dict(rpull_ohm=4700,rise_at_200pF_s=.8473*4700*200e-12,cap_for_1us_rise_F=1e-6/(.8473*4700),cap_for_300ns_rise_F=300e-9/(.8473*4700),write_olat_27clocks_s=27/100000,read11_registers_126clocks_s=126/100000,read_iodir_guard_36clocks_s=36/100000,guarded_read_162clocks_s=162/100000,proposed_measured_acquisition_budget_s=.003,read_period_s=.010,source_freshness_s=.020)
loading=dict(normal_per_bias_branch_upper_A=vmax/rf,normal_per_collector_pullup_upper_A=vmax/4653,loop_high_static_A=vmax/(990+99000),two_bus_pullups_low_A=2*vmax/4653,normal_two_channels_conservative_upper_A=2*(vmax/rf+vmax/4653),scope='Mutually exclusive branches summed conservatively. Add MCP23008, reset, optional bleed and other-board consumption. This is resistor arithmetic, not a guaranteed complete supply budget.')
rc=dict(proposed_cap_F=10e-9,pullup_nominal_ohm=4700,tau_nominal_s=4700*10e-9,rise_from_zero_to_80percent_nominal_s=-math.log(.2)*4700*10e-9,scope='Illustrative RC only; capacitance/tolerance/temperature and actual transistor switching require selected-part review and measurement.')
# Static clamp-diode current into a fully disconnected local3V3 rail from two high bus lines.
# This is only a KCL model with assumed .6V clamp; actual diode I/V/reset behavior must be measured.
phantom=[]
for bleed in (math.inf,100000,10000,2200,1000):
 vleak=2*50e-6 # unrelated conservative leakage example, not a transistorB-C current bound
 vrail=None if math.isinf(bleed) else (2*(3.63-.6)/4700+vleak)/(2/4700+1/bleed)
 if vrail is not None and vrail>3.63-.6:vrail=vleak*bleed # bus diodes then switch off; never allow negative clamp current
 phantom.append(dict(bleed_ohm=None if math.isinf(bleed) else bleed,model_vrail_V=vrail,qualification='Two4.7k pullups and assumed .6V pin clamps plus100uA injected current; transistorB-C backfeed is an additional path, not bounded here'))
result=dict(passed_arithmetic=True,scope='Candidate resistor/corner arithmetic; no transistor, protection, temperature, poweroff or target acceptance',corner_count=len(corners),base_current_min_uA=min(c['base_uA'] for c in corners),base_current_max_uA=max(c['base_uA'] for c in corners),forced_beta_max=max(c['forced_beta'] for c in corners),worst_forced_beta_case=max(corners,key=lambda x:x['forced_beta']),closed_base_max_V=max(c['vbase'] for c in closed),negative_fault=negative,positive_fault=positive,bus=bus,loading=loading,rc=rc,phantom_kcl_examples=phantom,required_device_measurement='Establish actual VCE_LOW below0.2*VDD and leakage-compatible HIGH above0.8*VDD at procured transistor/temperature/voltage, plus B-C backfeed and rail/reset behavior. VCE=.2 used only for collector demand, not a proven value.')
assert result['base_current_min_uA']>70 and result['forced_beta_max']<10
assert result['closed_base_max_V']<.16 and negative['rbias_power_W']<.22
(out/'electrical-probe.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
