#!/usr/bin/env python3
"""Shared finite recorder versus actual pinned Speeduino logger/IRQ wrappers.

Prescribed digital inputs test diagnostic fidelity, not a running engine plant
or real MCPWM/GPIO timing. The separate external-plant matrix tests actuation.
"""
import hashlib
import json
from pathlib import Path
from engine_runtime import load_engine_bridge
from trigger_capture import TriggerCapture
from speeduino_runtime import SpeeduinoRuntime

ROOT=Path(__file__).resolve().parents[1]

def signals(rpm,case):
 period=1_000_000/rpm;events=[]
 for index in range(440):
  if index%60>=58:continue
  rise=round((index+1)*period);fall=round((index+1.35)*period)
  if case=='jitter':rise+=(-30,0,25,10)[index%4];fall+=(-30,0,25,10)[index%4]
  shift=100000 if case=='dropout' and index>=190 else 0
  events.extend([(rise+shift,0,True),(fall+shift,0,False)])
  if case=='noise' and index in (185,205):
   glitch=round((index+1.6)*period);events.extend([(glitch,0,True),(glitch+3,0,False)])
 if case=='cam':
  for index in range(185,440,120):events.extend([(round((index+.6)*period),1,True),(round((index+3.6)*period),1,False)])
 return round(180*period),sorted(events)

def one_case(mode,rpm,case):
 arm,events=signals(rpm,case);reference=SpeeduinoRuntime(logger_cam=case=='cam')
 recorder=TriggerCapture(load_engine_bridge());expected=[]
 try:
  warm=[row for row in events if row[0]<arm];future=[row for row in events if row[0]>=arm]
  for time,channel,high in warm:reference.input_edge(time,channel,high)
  reference.advance(arm);profile=reference.logger_profile();reference.logger(mode)
  requested=127 if mode=='composite' else 512
  body=json.dumps(dict(action='start',samples=requested,timeout_ms=5000)).encode()
  if recorder.command(body,arm)!=200:raise RuntimeError('Recorder did not arm')
  for time,channel,high in future:
   reference.input_edge(time,channel,high);recorder.append(time,counter=(time*80)&0xffffffff,epoch=1,cam=bool(channel),high=high)
   expected.append((time,channel,high))
  recorder.expire(arm+5_000_000);native=reference.trigger_log();header=recorder.frame()
  rows=[]
  for offset in range(0,header['count'],64):rows+=recorder.frame(header['frame_id'],offset,64)['records']
  checks={};details={}
  if mode=='composite':
   actual=[(r['value'],int(bool(r['flags']&8)),bool(r['flags']&(2 if r['flags']&8 else 1))) for r in native['records']]
   ours=[(r['captured_us'],int(r['channel']=='cam'),r['high']) for r in rows]
   checks.update(all_source_edges_preserved=ours==expected[:127],production_composite_matches_raw_edges=actual==ours,
                 both_frames_frozen_at127=header['state']=='full' and native['full'] and native['count']==127)
   periods=[b[0]-a[0] for a,b in zip([r for r in ours if not r[1] and r[2]],[r for r in ours if not r[1] and r[2]][1:])]
   details.update(maximum_rising_interval_us=max(periods,default=0),cam_edges=sum(r[1] for r in ours))
   if case=='dropout':checks['declared_signal_gap_visible']=max(periods)>100000
   if case=='noise':checks['three_microsecond_glitch_visible']=any(b[0]-a[0]==3 for a,b in zip(ours,ours[1:]))
   if case=='cam':checks['both_cam_polarities_visible']=any(r[1] and r[2] for r in ours) and any(r[1] and not r[2] for r in ours)
  else:
   rising=[r['captured_us'] for r in rows if r['channel']=='crank' and r['high']]
   intervals=[b-a for a,b in zip(rising,rising[1:])]
   # The first Speeduino tooth interval begins before this recorder's window.
   # Compare the126 intervals with both ends inside the common recorded span.
   values=[r['value'] for r in native['records']]
   checks.update(native_tooth_frame_full=native['full'] and native['count']==127,
                 common_complete_tooth_intervals_match=values[1:]==intervals[:126])
   details.update(compared_complete_intervals=126,first_reference_interval_excluded=values[0])
  checks['reference_decoder_still_operates']=abs(reference.status()['rpm']-rpm)<=1
  result=dict(mode=mode,rpm=rpm,case=case,passed=all(checks.values()),checks=checks,details=details,
              reference_profile=profile,reference=native,project_header=header,project_records=rows,source_events=expected)
  return result
 finally:
  try:reference.logger('stop');reference.halt()
  finally:reference.close();recorder.close()

def validate():
 out=ROOT/'.cache/engine/trigger-loggers';out.mkdir(parents=True,exist_ok=True);cases=[]
 fixtures=[('composite',rpm,'clean') for rpm in (200,1000,6000)]
 fixtures += [('composite',1000,case) for case in ('jitter','noise','dropout','cam')]
 fixtures += [('tooth',rpm,'clean') for rpm in (200,1000,6000)]
 for mode,rpm,case in fixtures:
  result=one_case(mode,rpm,case);path=out/f'{mode}-{rpm}-{case}.json';path.write_text(json.dumps(result,separators=(',',':'))+'\n')
  summary={k:v for k,v in result.items() if k not in ('reference','project_records','source_events')};summary['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();cases.append(summary)
  print(mode,rpm,case,'PASS' if result['passed'] else result['checks'],flush=True)
 paths=['tools/compare_trigger_loggers.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp',
        'tools/speeduino_runtime.py','tools/trigger_capture.py','tools/trigger_capture_bridge.hpp',
        'firmware/include/ecu/trigger_log.hpp','firmware/include/ecu/trigger_log_json.hpp','scripts/build_speeduino_sim.py']
 manifest=json.loads((ROOT/'.cache/engine/speeduino-sim/build-manifest.json').read_text())
 report=dict(scope='Prescribed digital trigger streams; native recorder and production Speeduino logger/IRQ wrappers with virtual GPIO. No physical or engine-plant timing qualification.',
             passed=all(c['passed'] for c in cases),case_count=len(cases),cases=cases,
             source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
             reference_build=dict(speeduino_sha=manifest['speeduino_sha'],unit_test=manifest['unit_test'],binary_sha256=manifest['binary_sha256'],hal_changes=manifest['hal_changes']),
             limits=['No MCU capture latch overwrite, interrupt latency, analog conditioning or electrical test',
                     'Reference cam fixture enables sequential injection solely to configure a real secondary decoder pin; this project still has no720degree phase/sequential strategy',
                     'Compare timestamps, source channel and reported edge level; Speeduino sync/cycle flags are retained but not asserted equivalent',
                     'Reads actual production history buffers; does not establish TunerStudio online acceptance or serial logger framing',
                     'Clean tooth comparison excludes the first reference interval whose start precedes the project window'])
 (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
 report=validate()
 if not report['passed']:raise SystemExit(1)
