"""Prescribed-shaft GPIO acceptance for the expanded genuine reference fixture.

This is a shaft stimulus, not an engine-plant simulation. All observed edge
bytes, requested/effective modes, wiring and scope limits are retained.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import unittest
from engine_geometry import EngineGeometry,channel_kind
from speeduino_profiles_runtime import SpeeduinoProfilesRuntime,NATIVE_PINS
from speeduino_runtime import ROOT,SpeeduinoRuntime

BINARY=None;OUTPUT=None;CASES={}


def prescribed(runtime,rpm=1000,until_us=600000,cam=False,period_us=250):
    events=[(us,0)for us in range(period_us,until_us+1,period_us)]
    index=1
    while round(index*1e6/rpm)<=until_us:
        if index%60<58:events.append((round(index*1e6/rpm),1))
        index+=1
    if cam:
        angle=540
        while round(angle*1e6/(rpm*6))<=until_us:
            events.append((round(angle*1e6/(rpm*6)),2));angle+=720
    edges=[]
    for us,kind in sorted(events):
        if kind==2:edges+=runtime.input_edge(us,1,True)+runtime.input_edge(us,1,False)
        else:edges+=runtime.advance(us,tooth=kind==1)
    if runtime.now<until_us:edges+=runtime.advance(until_us)
    return edges


def analyze(runtime,edges,rpm=1000):
    high={};widths=[];phase=[];closing=[]
    for us,ch,value,_,_ in edges:
        if value:
            if ch in high:raise AssertionError('Duplicate rise')
            high[ch]=us
        else:
            if ch not in high:raise AssertionError('Fall without rise')
            width=us-high.pop(ch);widths.append([ch,width])
            kind,index=channel_kind(ch);mode=runtime.edge_modes[(us,ch,False)]
            if us>=400000:
                if kind=='coil':
                    error=math.remainder(runtime.geometry.compression_tdc_deg[index]-us*rpm*6e-6-10,
                                         720 if mode['effective_sequential']else 360)
                    phase.append([us,ch,error])
                else:
                    goal=runtime.geometry.compression_tdc_deg[index]+(540 if runtime.sequential else 180)
                    closing.append([us,ch,math.remainder(us*rpm*6e-6-goal,720 if runtime.sequential else 360)])
    return dict(high_at_stop=sorted(high),widths_us=widths,spark_error_deg=phase,
                injection_closing_error_deg=closing,max_spark_error_deg=max((abs(r[2])for r in phase),default=None))


class ProfilesTests(unittest.TestCase):
    def test_all24_profiles_observe_distinct_outputs_modes_and_global_low(self):
        for n in range(1,9):
            geometry=EngineGeometry(n,(1,*range(n,1,-1)),500*n)
            for mode in ('sequential','wasted_cop','semi'):
                with self.subTest(cylinders=n,mode=mode):
                    r=SpeeduinoProfilesRuntime(BINARY,geometry,mode)
                    try:
                        initial=r.profile['effective_before_start']
                        self.assertEqual(tuple(initial['native_output_pins']),NATIVE_PINS)
                        self.assertEqual(len(set(zip(initial['native_port_ids'],initial['native_port_masks']))),16)
                        edges=prescribed(r,cam=mode=='sequential');state=r.status();metrics=analyze(r,edges)
                        self.assertEqual(state['rpm'],1000)
                        self.assertEqual(state['sync'],2)
                        used={row[1]for row in edges}
                        expected=set(geometry.injector_channels+geometry.coil_channels)
                        if n==7 and mode!='sequential':
                            expected={r.pin_map[p]for p in NATIVE_PINS[:3]+NATIVE_PINS[8:11]}
                        self.assertEqual(used,expected)
                        self.assertTrue(metrics['spark_error_deg'])
                        if r.profile['representable_ignition_geometry']:
                            self.assertLess(metrics['max_spark_error_deg'],6.1 if n==7 else 1)
                        else:self.assertGreater(metrics['max_spark_error_deg'],30)
                        if n in (4,6,8) and mode=='sequential':
                            self.assertTrue(any(m['sync_status']==1 and m['ignition_span_deg']==360 and m['effective_injection_layout']==1 for m in r.mode_history))
                            self.assertEqual(state['reference_effective']['effective_injection_layout'],3)
                            self.assertEqual(state['reference_effective']['ignition_span_deg'],720)
                        if n in (1,2,3,5,7)and mode!='sequential':
                            self.assertEqual(initial['configured_spark_mode'],0)
                        falls=r.halt();self.assertEqual({ch for _,ch,_ in falls},set(metrics['high_at_stop']))
                        self.assertTrue(all(us==600000 and not high for us,ch,high in falls))
                        self.assertEqual(r.advance(620000),[])
                        name=f'{n}-{mode}'
                        CASES[name]=dict(profile=r.profile,metrics=metrics,status=state,edges=edges,
                                         halt=falls,scope='Prescribed1000rpm shaft, not a coupled engine run')
                    finally:r.close()

    def test_three_historical_four_cylinder_modes_have_exact_same_edges(self):
        for mode in ('sequential','wasted_cop','semi'):
            old=SpeeduinoRuntime(sequential=mode=='sequential',semi_sequential=mode=='semi')
            new=SpeeduinoProfilesRuntime(BINARY,EngineGeometry(),mode)
            try:
                a=prescribed(old,cam=mode=='sequential');b=prescribed(new,cam=mode=='sequential')
                self.assertEqual(a,b)
                astate=old.status();bstate=new.status()
                self.assertEqual(astate,{k:bstate[k]for k in astate})
                self.assertEqual(old.halt(),new.halt())
            finally:old.close();new.close()

    def test_invalid_profile_clock_and_unimplemented_ipc_are_rejected(self):
        for geometry in (EngineGeometry(8,tuple(range(1,9)),5000),EngineGeometry(tooth1_tdc_deg=120)):
            with self.assertRaises(ValueError):SpeeduinoProfilesRuntime(BINARY,geometry)
        for count,mode,command in (('0','sequential',''),('9','semi',''),('8','unknown',''),
                ('8','sequential','advance -1\n'),('8','sequential','advance 60000001\n'),
                ('8','sequential','trimconfig 1\n')):
            p=subprocess.run([str(BINARY),count,mode],input=command,text=True,capture_output=True,timeout=4)
            self.assertEqual(p.returncode,2)

    def test_high_rpm_limit_cuts_the_production_schedulers(self):
        r=SpeeduinoProfilesRuntime(BINARY,EngineGeometry(8,tuple(range(1,9)),4000))
        try:
            edges=prescribed(r,7000,800000,cam=True);s=r.status()
            self.assertLessEqual(abs(s['rpm']-7000),2)
            self.assertEqual(s['fuel_channels'],0);self.assertEqual(s['ignition_channels'],0)
            self.assertFalse(any(high for us,_,high,_,_ in edges if us>300000))
            r.halt()
        finally:r.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args,rest=parser.parse_known_args();BINARY=args.executable.resolve();OUTPUT=args.output.resolve()
    OUTPUT.mkdir(parents=True,exist_ok=False)
    result=unittest.main(argv=[__file__,*rest],verbosity=2,exit=False).result
    for name,case in CASES.items():
        (OUTPUT/(name+'.json.gz')).write_bytes(gzip.compress(json.dumps(case,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    sources=('tools/test_speeduino_profiles.py','tools/speeduino_profiles_runtime.py','tools/speeduino_profiles_sim.cpp','scripts/build_speeduino_profiles.py','tools/engine_geometry.py')
    summary=dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        cases={name:dict(max_spark_error_deg=c['metrics']['max_spark_error_deg'],effective_before_start=c['profile']['effective_before_start'],
                        geometry_issues=c['profile']['physical_geometry_issues'],mode_history=c['profile']['mode_history'])for name,c in CASES.items()},
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in sources},
        binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
        scope='Actual16GPIO native prescribed-shaft acceptance and exact original4-cylinder compatibility; no engine-plant or physical qualification')
    (OUTPUT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    raise SystemExit(not result.wasSuccessful())
