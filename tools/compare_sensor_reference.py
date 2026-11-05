"""Actual production Speeduino MAP acquisition versus shared ECU conversion.

The supplied raw counts model declared voltage/reference relationships. This
does not emulate an AVR ADC, power distribution or either physical ECU.
"""
import argparse
import copy
import ctypes
import hashlib
import json
import math
from pathlib import Path
import subprocess
from web_server import R, Reading, load_bridge


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(binary,out):
    out.mkdir(parents=True,exist_ok=False);binary=binary.resolve()
    manifest=binary.parent/'build-manifest.json';m=json.loads(manifest.read_text())
    assert m['scope']=='production_loop_raw_adc_map_calibration' and not m['unit_test']
    assert sha(binary)==m['binary_sha256']
    inputs=m['locked_original_input_hashes']
    assert all(sha(Path(name))==value for name,value in inputs.items())
    bridge=load_bridge();profile=json.loads((R/'config/defaults.json').read_text())
    profile['sensors'][0].update(mode='linear',unit='kPa',confirmed=True,v0=0,y0=10,v1=5,y1=110)
    cases=[]
    for supply in (4.8,4.9,5.,5.1,5.2):cases.append(dict(kind='common_reference',sensor_supply_v=supply,speeduino_avcc_v=supply))
    for supply in (4.8,4.9,5.):cases.append(dict(kind='sensor_only_drop',sensor_supply_v=supply,speeduino_avcc_v=5.))
    for i,c in enumerate(cases):
        signal=.42*c['sensor_supply_v'];c['signal_v']=signal;c['true_map_kpa']=52.
        c['speeduino_raw_adc']=math.floor(1024*signal/c['speeduino_avcc_v'])
        c['time_us']=10000000+i*100000
    commands=''.join(f"adc {c['time_us']} {c['speeduino_raw_adc']}\n" for c in cases)+'quit\n'
    (out/'reference-input.txt').write_text(commands)
    result=subprocess.run([str(binary)],input=commands,text=True,capture_output=True,check=True,timeout=60)
    (out/'reference-output.jsonl').write_text(result.stdout);(out/'reference-stderr.log').write_text(result.stderr)
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    assert rows[0]['kind']=='ready' and rows[0]['time_us']<cases[0]['time_us']
    observed=rows[1:];assert len(observed)==len(cases)
    for c,row in zip(cases,observed):
        assert row['kind']=='sample' and row['time_us']==c['time_us'] and row['raw_map_adc']==c['speeduino_raw_adc']
        assert row['rpm']==0 and not row['physical_execution']
        c['production_speeduino_map_kpa']=row['map_kpa']
        adc=lambda v:math.floor(4096*v/3.3)
        raw=(ctypes.c_uint*8)(adc(c['signal_v']*.6),*[adc(2*.6)]*5,adc(14/13),adc(c['sensor_supply_v']*.6))
        c['ecu_raw_adc']=list(raw)
        for enabled in (False,True):
            p=copy.deepcopy(profile);p['sensors'][0]['ratiometric']=enabled
            body=json.dumps(p).encode();basis=(ctypes.c_double*6)();previous=(ctypes.c_double*6)();output=(Reading*6)()
            assert bridge.filter_profile(body,raw,previous,0,True,True,basis)==1
            assert bridge.evaluate_profile(body,raw,basis,output)==1 and output[0].valid
            c['ecu_ratiometric_kpa' if enabled else 'ecu_absolute_kpa']=output[0].value
    common=[c for c in cases if c['kind']=='common_reference'];isolated=[c for c in cases if c['kind']=='sensor_only_drop']
    assert len({c['production_speeduino_map_kpa'] for c in common})==1
    assert all(abs(c['production_speeduino_map_kpa']-52)<=1.1 for c in common)
    assert isolated[0]['production_speeduino_map_kpa']<isolated[-1]['production_speeduino_map_kpa']
    assert all(abs(c['ecu_ratiometric_kpa']-52)<.08 for c in cases)
    assert cases[0]['ecu_absolute_kpa']<50.5
    names=['firmware/include/ecu/config.hpp','firmware/main/config_json.hpp','tools/config_bridge.cpp',
           'tools/web_server.py','config/defaults.json','tools/compare_sensor_reference.py']
    for name in names:
        p=out/'sources'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/name).read_bytes())
    assert sha(binary)==m['binary_sha256'] and all(sha(Path(name))==value for name,value in inputs.items())
    report=dict(passed=True,production_speeduino_sha=m['speeduino_sha'],binary_sha256=sha(binary),
        build_manifest_sha256=sha(manifest),ecu_bridge_sha256=sha(Path(bridge._name)),
        source_sha256={name:sha(R/name) for name in names},cases=cases,
        assertions=['Production loop MAP stays constant for authored common-reference counts',
            'A sensor-only supply drop is not cancelled by a separate unchanged AVCC',
            'Shared ECU ratio conversion preserves the known52kPa fixture within12-bit quantization',
            'Legacy absolute conversion retains its supply-dependent behavior'],
        source_context='Pinned Speeduino sensors.cpp selects AVCC on AVR (ADMUX_DEFAULT_CONFIG0x40). Native analogRead receives authored10-bit counts; this fixture does not execute that ADC hardware.',
        limits=['MAP acquisition/conversion only, no engine or actuator comparison in this fixture',
            'The common-reference case applies only when the signal and ADC reference share the declared supply relationship',
            'It does not imply all Speeduino boards cancel a separate sensor fuse/wiring drop',
            'No AVR/ESP32 timing, ADC electrical accuracy, supply or vehicle qualification'],physical_qualification=False)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(cases),common_reference_outputs=[c['production_speeduino_map_kpa'] for c in common])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.binary,args.output.resolve())
