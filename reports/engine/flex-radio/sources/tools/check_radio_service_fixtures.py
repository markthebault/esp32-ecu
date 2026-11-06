#!/usr/bin/env python3
"""Process actual native sender/handler fixture bytes with the reference receiver."""
import argparse,json
from pathlib import Path
from engine_receiver import EngineReceiver

def run(directory,output):
 # Public deterministic API-model peer values from radio_service_test.cpp.
 r=EngineReceiver('02:EC:00:00:00:01',bytes(range(16)))
 query=r.query(100,bytes([1])*16);assert query==(directory/'query-request.bin').read_bytes()
 r.receive_reply((directory/'query-reply.bin').read_bytes(),r.ecu_mac,110)
 update=r.update(True,120,bytes([2])*16);assert update==(directory/'update-request.bin').read_bytes()
 r.receive_reply((directory/'update-reply.bin').read_bytes(),r.ecu_mac,125)
 assert r.receive((directory/'base.bin').read_bytes(),r.ecu_mac,140) is None
 assert r.latest is None
 data=r.receive((directory/'flex.bin').read_bytes(),r.ecu_mac,190)
 assert data['complete_observation'] and data['source_code']==1
 assert data['flex_fuel']['source_code']==1 and data['flex_fuel']['ethanol_pct']==50 and data['flex_fuel']['fuel_temp_c']==42.5
 assert r.acknowledgement()==(directory/'engine-ack.bin').read_bytes()
 assert r.status(190)['flex_raw_capture_qualified']
 assert not r.status(380)['flex_value_qualified']
 report=dict(passed=True,qualification=__doc__+' Native SDK API model only; no target/RF or actual screen.',decoded=data,status_at_380_ms=r.status(380))
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n');print('Actual native sender/handler and reference receiver bytes agree')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args();run(a.directory,a.output)
