"""Differentially replay absolute profiles against the published pre-ratio code."""
import argparse
import copy
import ctypes
import gzip
import hashlib
import json
import random
import struct
import subprocess
from pathlib import Path
from web_server import R, Reading, load_bridge
from test_sensor_ratiometric import legacy

BASE='1050d9276e89f4289cfe4ad1e275d604485c6243'
FILES=['firmware/include/ecu/config.hpp','firmware/include/ecu/json.hpp',
       'firmware/main/config_json.hpp','tools/config_bridge.cpp']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class OldReading(ctypes.Structure):
    _fields_=[('value',ctypes.c_double),('sensor_v',ctypes.c_double),
              ('adc_v',ctypes.c_double),('valid',ctypes.c_int),('fault',ctypes.c_char*64)]


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    current=load_bridge()
    names=FILES+['config/defaults.json','tools/compare_sensor_calibration.py','tools/web_server.py','tools/test_sensor_ratiometric.py']
    inputs={name:sha(R/name) for name in names}
    for name in names:
        p=out/'current'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/name).read_bytes())
    baseline={}
    for name in FILES:
        data=subprocess.check_output(['git','show',BASE+':'+name],cwd=R)
        p=out/'baseline'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);baseline[name]=sha(p)
    cjson=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
    commands=[['cc','-O2','-fPIC','-c',str(cjson/'cJSON.c'),'-o',str(out/'cJSON.o')],
        ['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
         '-I'+str(cjson),'-I'+str(out/'baseline/firmware/main'),'-I'+str(out/'baseline/firmware/include'),
         str(out/'baseline/tools/config_bridge.cpp'),str(out/'cJSON.o'),'-o',str(out/'baseline.so')]]
    for i,command in enumerate(commands):
        with (out/f'build-{i}.log').open('xb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    old=ctypes.CDLL(str(out/'baseline.so'))
    old.evaluate_profile.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_double),ctypes.POINTER(OldReading)]
    old.evaluate_profile.restype=ctypes.c_int
    base=json.loads((R/'config/defaults.json').read_text());mixed=copy.deepcopy(base)
    mixed['sensors'][0].update(mode='linear',y0=10,y1=110)
    mixed['sensors'][1].update(mode='linear',y0=100,y1=0)
    for i in (2,3):mixed['sensors'][i].update(mode='ntc_beta',pullup_fitted=True)
    mixed['sensors'][4].update(mode='table',points=[dict(v=.1,value=.5),dict(v=2.5,value=1),dict(v=5.1,value=1.6)])
    mixed['sensors'][5].update(mode='linear',y0=110,y1=10)
    rng=random.Random(0xA6505);transcript=[];readings=0
    for profile in (base,mixed):
        body=json.dumps(profile,separators=(',',':')).encode();prior=json.dumps(legacy(profile),separators=(',',':')).encode()
        for n in range(1024):
            raw=[rng.randrange(4096) for _ in range(8)]
            # Include raw and independently delayed display voltages, open/short
            # faults, invalid supply, curve endpoints and NTC loading paths.
            filtered=[v*3.3/4095/.6 if n%2 else rng.uniform(0,5.5) for v in raw[:6]]
            x=(ctypes.c_uint*8)(*raw);f=(ctypes.c_double*6)(*filtered)
            a=(OldReading*6)();b=(Reading*6)()
            assert old.evaluate_profile(prior,x,f,a)==1 and current.evaluate_profile(body,x,f,b)==1
            actual=[]
            for left,right in zip(a,b):
                for field in ('value','sensor_v','adc_v'):
                    assert struct.pack('d',getattr(left,field))==struct.pack('d',getattr(right,field)),(n,field)
                assert left.valid==right.valid and left.fault==right.fault
                actual.append(dict(value=right.value.hex(),sensor_v=right.sensor_v.hex(),adc_v=right.adc_v.hex(),valid=right.valid,fault=right.fault.decode()))
                readings+=1
            transcript.append(dict(profile='voltage' if profile is base else 'mixed',raw=raw,filtered=[v.hex() for v in filtered],readings=actual))
    (out/'profiles.json').write_text(json.dumps([base,mixed],indent=2)+'\n')
    body=''.join(json.dumps(row,separators=(',',':'))+'\n' for row in transcript).encode()
    (out/'transcript.jsonl.gz').write_bytes(gzip.compress(body,mtime=0))
    assert inputs=={name:sha(R/name) for name in names},'source changed during replay'
    result=dict(passed=True,baseline_commit=BASE,baseline_sources=baseline,current_sources=inputs,
        commands=commands,seed='0xA6505',profiles=2,raw_vectors=2048,compared_readings=readings,
        comparison='bit-identical value/sensor_v/adc_v doubles, validity and fault strings with ratio Off',
        transcript_sha256=sha(out/'transcript.jsonl.gz'),baseline_binary_sha256=sha(out/'baseline.so'),
        current_binary_sha256=sha(Path(current._name)),cjson_sha256=sha(cjson/'cJSON.c'),
        physical_qualification=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,compared_readings=readings,raw_vectors=2048)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
