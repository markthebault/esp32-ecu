#!/usr/bin/env python3
"""Integration checks against the actual non-UNIT_TEST reference executable."""
import subprocess
import unittest
from speeduino_runtime import ROOT,SpeeduinoRuntime


def constant_speed(runtime,rpm,until_us=300000):
    events=[(us,False) for us in range(250,until_us+1,250)]
    tooth=1
    while round(tooth*1e6/rpm)<=until_us:
        us=round(tooth*1e6/rpm)
        if tooth%60<58:events.append((us,True))
        tooth+=1
    edges=[]
    for us,is_tooth in sorted(events):edges+=runtime.advance(us,tooth=is_tooth)
    return edges


class ProductionSpeeduinoAcceptance(unittest.TestCase):
    def test_bad_input_channel_rejected_before_mutating_live_child(self):
        runtime=SpeeduinoRuntime();self.addCleanup(runtime.close)
        for channel in (False,True,0.0,1.0,'0',2,-1,None):
            with self.assertRaises(ValueError):runtime.input_edge(1000,channel,True)
            self.assertEqual(runtime.now,0);self.assertIsNone(runtime.process.poll())
        runtime.input_edge(1000,0,True);self.assertEqual(runtime.now,1000);self.assertIsNone(runtime.process.poll())
    def runtime(self,per_tooth=False):
        runtime=SpeeduinoRuntime(per_tooth);self.addCleanup(runtime.close);return runtime

    def test_constant_speed_sync_edges_and_repeatability(self):
        all_edges=[]
        for _ in range(2):
            runtime=self.runtime();edges=constant_speed(runtime,1000)
            status=runtime.status();self.assertEqual(status['rpm'],1000)
            self.assertEqual(status['sync'],2);self.assertEqual(status['pulse_us'],5445)
            high={};widths=[]
            for us,ch,value,_,_ in edges:
                if value:self.assertNotIn(ch,high);high[ch]=us
                else:widths.append((ch,us-high.pop(ch)))
            self.assertTrue(widths)
            self.assertEqual({w for ch,w in widths if ch<4},{5444})
            self.assertEqual({w for ch,w in widths if ch>=4},{2800})
            all_edges.append(edges);runtime.close()
        self.assertEqual(all_edges[0],all_edges[1])

    def test_enabled_fixed_hard_limit_cuts_real_schedulers(self):
        for per_tooth in (False,True):
            runtime=self.runtime(per_tooth)
            edges=constant_speed(runtime,7000,800000)
            status=runtime.status()
            self.assertLessEqual(abs(status['rpm']-7000),2)
            self.assertEqual(status['fuel_channels'],0);self.assertEqual(status['ignition_channels'],0)
            self.assertFalse(any(value for us,ch,value,_,_ in edges if us>300000))
            runtime.close()

    def test_halt_closes_actually_high_injectors_and_coils(self):
        runtime=self.runtime();edges=constant_speed(runtime,1000,71000)
        high=set()
        for _,ch,value,_,_ in edges:
            if value:high.add(ch)
            else:high.remove(ch)
        self.assertGreaterEqual(len(high),6)
        falls=runtime.halt()
        self.assertEqual({ch for _,ch,value in falls if not value},high)
        self.assertTrue(all(us==71000 and not value for us,ch,value in falls))

    def test_invalid_native_clock_is_bounded(self):
        executable=ROOT/'.cache/engine/speeduino-sim/speeduino-sim'
        for value in ('-1','60000001'):
            result=subprocess.run([str(executable)],input=f'advance {value}\n',text=True,capture_output=True,timeout=2)
            self.assertEqual(result.returncode,2)
            self.assertIn('60s bound',result.stderr)


if __name__=='__main__':unittest.main(verbosity=2)
