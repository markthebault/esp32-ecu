"""Independent arithmetic/logic/DC-connectivity probe for a proposed architecture.

This is not SPICE, a device switching model, a routed-netlist audit, or physical
qualification. Its graph treats all input-side conductors as connected and
intentionally excludes optical transfer and capacitance from DC connectivity.
"""
import hashlib,itertools,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
R=HERE.parents[2]

def reachable(edges,a,b):
    seen={a};todo=[a]
    while todo:
        p=todo.pop()
        for x,y in edges:
            q=y if x==p else x if y==p else None
            if q is not None and q not in seen:seen.add(q);todo.append(q)
    return b in seen

def run():
    corners=[]
    for ref,r1,r2,iadj in itertools.product((1.225,1.270),(120*.99,120*1.01),(374*.99,374*1.01),(0,100e-6)):
        corners.append(dict(vref=ref,r1=r1,r2=r2,iadj=iadj,vout=ref*(1+r2/r1)+iadj*r2))
    low=min(x['vout'] for x in corners);high=max(x['vout'] for x in corners)
    load=1.225/(120*1.01)
    assert low>4.85 and high<5.5 and load>.010 and 9-high>3
    truth=[]
    for pwm,run,good in itertools.product((False,True),repeat=3):
        pwm_n=not pwm;run_n=not run;ina=not(pwm_n or run_n);ena=good;out=ina and ena
        assert out==(pwm and run and good)
        truth.append(dict(pwm=pwm,run=run,power_good=good,opto_pwm_n=pwm_n,opto_run_n=run_n,driver_ina=ina,driver_ena=ena,output=out))
    old=[('Q_SOURCE','ACT_GND'),('ACT_GND','CARRIER_GND'),('CARRIER_GND','J1_RETURN')]
    new=[('Q_SOURCE','ACT_GND'),('ACT_GND','REGULATOR_GND'),('REGULATOR_GND','OPTO_OUTPUT_GND'),('OPTO_LED_RETURN','CARRIER_GND'),('CARRIER_GND','J1_RETURN'),('CARRIER_GND','INPUT_NPN_EMITTER')]
    assert reachable(old,'Q_SOURCE','J1_RETURN')
    assert not reachable(new,'Q_SOURCE','J1_RETURN')
    assert reachable(new+[('ACT_GND','CARRIER_GND')],'Q_SOURCE','J1_RETURN')
    led_min=(4.75-1.7-.3)/(357*1.01);led_max=5.25/(357*.99)
    assert .0075<=led_min<=led_max<=.015
    # Upper bound includes a conservative base-emitter short and R47's load.
    run_output_load=5.25/(1800*.95)+5.25/(10000*.95)
    assert run_output_load<.004
    sources=['hardware/idle-accessory/net_contract.json','hardware/idle-accessory/idle.kicad_sch','hardware/idle-accessory/idle.kicad_pcb','hardware/a4-n16r8/net_contract.json','firmware/include/ecu/idle_hardware.hpp','reports/engine/idle-control/reviews/hardware/pass2/review.md']
    return dict(scope=__doc__,base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),
        assumptions=dict(led_vf_max_v=1.7,npn_vce_sat_max_v=.3,carrier_5v_range=[4.75,5.25],resistor_tolerance_led=.01,loaded_gpio_voltage_guaranteed=False,npn_full_temperature_saturation_guaranteed=False),
        regulator=dict(corners=corners,minimum_output_v=low,maximum_output_v=high,minimum_divider_load_a=load,minimum_headroom_at_9v_v=9-high,maximum_logic_rail_margin_v=5.5-high),
        supervisor=dict(part='MCP100-485DI/TO',trip_min_v=4.60,trip_max_v=4.85,static_brownout_margin_above_4p5_v=.10,minimum_regulator_minus_max_trip_v=low-4.85,release_delay_ms=[150,700],assertion_delay_typ_us=10,assertion_delay_max_us=None,hysteresis_typ_mv=50,hysteresis_max_mv=None,arbitrary_rapid_brownout_fail_low_proven=False),
        led=dict(resistor_ohm=357,minimum_current_a=led_min,conservative_maximum_current_a=led_max,switching_table_test_current_a=.0075),
        logic=dict(initial_hct14_falling_threshold_min_v=.5,opto_low_max_v=.6,initial_hct14_margin_v=-.1,revised_hct02_vil_max_v=.8,revised_hct02_margin_v=.2,truth_table=truth),
        run_driver=dict(direct_required_minimum_led_a=.005,direct_hct_guaranteed_voh_test_current_a=.004,direct_drive_supported=False,buffered_maximum_output_load_including_R47_a=run_output_load),
        dc_graph=dict(old_return_path=True,new_return_path=False,negative_control_added_bridge_returns_path=True,assumes_no_external_conductive_bridge=True,proves_isolation_voltage_or_transient_behavior=False),
        source_sha256={p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in sources},
        unresolved=['Actual new netlist and routed copper not reviewed in this architecture probe','Opto/NPN/gate and supervisor transient timing not validated','Loaded GPIO voltage and actual module eFuse/routing unknown','Regulator transient overshoot, thermal and startup behavior unmeasured','Physical barrier, mounting and enclosure conductive bridges unmeasured','External protected/fused switched actuator branch and actual valve unselected'])
if __name__=='__main__':
    d=run();(HERE/'architecture-probe.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:d[k] for k in ['regulator','supervisor','led','run_driver','dc_graph']},indent=2))
