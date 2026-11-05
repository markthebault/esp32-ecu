#!/usr/bin/env python3
"""Process actual native sender/handler fixture bytes with the reference receiver."""
import argparse,json
from pathlib import Path
from engine_receiver import EngineReceiver

def run(directory,output):
 # Public deterministic API-model peer values from radio_service_test.cpp.
 r=EngineReceiver('02:EC:00:00:00:01',bytes(range(16)),schema=5)
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
 legacy=dict(decoded=data,status_at_380_ms=r.status(380))
 r=EngineReceiver('02:EC:00:00:00:01',bytes(range(16)),schema=6)
 query=r.query(100,bytes([1])*16);assert query==(directory/'schema6-query-request.bin').read_bytes()
 r.receive_reply((directory/'schema6-query-reply.bin').read_bytes(),r.ecu_mac,110)
 update=r.update(True,120,bytes([2])*16);assert update==(directory/'schema6-update-request.bin').read_bytes()
 r.receive_reply((directory/'schema6-update-reply.bin').read_bytes(),r.ecu_mac,125)
 for name,when in (('base',140),('flex',190)):
  assert r.receive((directory/('schema6-'+name+'.bin')).read_bytes(),r.ecu_mac,when) is None
  assert r.latest is None and r.received_ms is None
  try:r.acknowledgement()
  except ValueError:pass
  else:raise AssertionError('Partial observation could be acknowledged')
 data=r.receive((directory/'schema6-boost.bin').read_bytes(),r.ecu_mac,240)
 assert data['complete_observation'] and data['datagrams_per_observation']==3
 assert data['inputs']['map_kpa']==150 and data['flex_fuel']['ethanol_pct']==50
 assert data['boost_control']['pressure_enabled'] and data['boost_control']['reason']=='ready' and not data['boost_control']['inhibit_engine']
 assert r.acknowledgement()==(directory/'schema6-engine-ack.bin').read_bytes()
 assert r.status(240)['boost_observation_fresh'] and not r.status(380)['flex_value_qualified']
 qos=json.loads((directory/'schema6-four-peers.json').read_text());assert qos['passed'] and qos['submitted_observations']==[5]*4 and not qos['RF_or_RTOS_measured']
 fairness=json.loads((directory/'schema6-fairness.json').read_text());assert fairness['passed'] and fairness['all_six_metadata_channels'] and fairness['maximum_assembly_us']==200000 and not fairness['RF_or_RTOS_measured']
 report=dict(passed=True,qualification=__doc__+' Native SDK API model only; no target/RF or actual screen.',legacy=legacy,boost=dict(decoded=data,status_at_380_ms=r.status(380)),sender_slots=qos,sender_fairness=fairness)
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n');print('Actual native sender/handler and reference receiver bytes agree')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args();run(a.directory,a.output)
