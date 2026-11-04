#!/usr/bin/env python3
"""Acceptance tests for external-plant conservation, actuation and causality.

uv run --with 'fmpy==0.3.26' python tools/test_research_plant.py
"""
import copy
import math
import unittest
from engine_research_plant import ResearchPlant
from compare_engine_controllers import benchmark_tune,run


class ResearchPlantAcceptance(unittest.TestCase):
    def plant(self):
        plant=ResearchPlant();self.addCleanup(plant.close);return plant

    def balances(self,plant):
        ledger=plant.ledger()
        for key,tolerance in [('fuel_residual_mg',1e-7),('chemical_residual_j',1e-5),
                              ('shaft_residual_j',1e-5),('air_residual_kg',1e-8),('air_energy_residual_j',.02)]:
            self.assertLess(abs(ledger[key]),tolerance,(key,ledger))
        return ledger

    def test_rest_starter_coast_restart(self):
        p=self.plant();maxima=[]
        for n in range(16000):
            t=n*.00025;p.integrate(t,.00025,starter=(.5<=t<1.5 or 3<=t<4))
            if n in (1999,5999,11999,15999):maxima.append(p.rpm)
        self.assertEqual(maxima[0],0);self.assertGreater(maxima[1],200)
        self.assertEqual(maxima[2],0);self.assertGreater(maxima[3],200)
        self.assertEqual(p.combustion_shaft_j,0);self.balances(p)

    def test_fuel_at_rest_creates_no_work(self):
        p=self.plant();p.edge(0,True,0)
        for n in range(2000):p.integrate(n*.00025,.00025)
        p.edge(0,False,.5)
        self.assertGreater(p.fuel_mg,1000);self.assertEqual(p.rpm,0)
        self.assertEqual(p.burned_chemical_j,0);self.assertFalse(p.lambda_valid);self.balances(p)

    def test_fuel_without_ignition_exits_unburned(self):
        p=self.plant()
        for n in range(12000):
            t=n*.00025
            if n%400==0:
                for ch in range(4):p.edge(ch,True,t)
            if n%400==16:
                for ch in range(4):p.edge(ch,False,t)
            p.integrate(t,.00025,starter=True)
        self.assertEqual(p.combustion_shaft_j,0);self.assertGreater(p.unburned_mg,100)
        self.assertGreater(sum(p.port_mg)+sum(p.charge_mg),0);self.balances(p)

    def test_ignition_without_fuel_creates_no_work(self):
        p=self.plant()
        for n in range(8000):
            t=n*.00025
            if n%400==0:p.edge(4,True,t)
            if n%400==12:p.edge(4,False,t)
            p.integrate(t,.00025,starter=True)
        self.assertGreater(p.sparks,10);self.assertEqual(p.burned_chemical_j,0)
        self.assertFalse(p.lambda_valid);self.balances(p)

    def test_trapped_air_is_frozen_after_intake_closing(self):
        p=self.plant()
        for n in range(6000):p.integrate(n*.00025,.00025,starter=True)
        trapped=copy.deepcopy(p.air_charge_mg)
        self.assertGreater(max(trapped),0)
        # A step at fixed shaft angle changes manifold state, not an already
        # closed cylinder. No full intake-close event is crossed in0.25ms.
        p.tps=100;p.integrate(1.5,.00025,starter=True)
        self.assertEqual(p.air_charge_mg,trapped)

    def test_actual_fuel_and_spark_change_free_shaft(self):
        base=run('ours','warm_start',6,250)
        lean=benchmark_tune();lean['maps']['ve']['cells']=[20]*256
        lean_result=run('ours','warm_start',6,250,tune=lean)
        late=benchmark_tune();late['maps']['spark']['cells']=[-5]*256
        late_result=run('ours','warm_start',6,250,tune=late)
        self.assertGreater(base['summary']['final_rpm'],700)
        self.assertLess(lean_result['summary']['final_rpm'],base['summary']['final_rpm']*.5)
        self.assertLess(late_result['summary']['ledger']['combustion_shaft_j'],base['summary']['ledger']['combustion_shaft_j']*.75)

    def test_halving_coupling_step_converges(self):
        coarse=run('ours','warm_start',6,250)['summary'];fine=run('ours','warm_start',6,125)['summary']
        for key in ('final_rpm','fuel_in_mg'):
            a=coarse[key] if key in coarse else coarse['ledger'][key]
            b=fine[key] if key in fine else fine['ledger'][key]
            self.assertLess(abs(a-b)/max(abs(b),1),.02,(key,a,b))
        self.assertLess(fine['max_trigger_quantization_deg'],.02)


if __name__=='__main__':unittest.main(verbosity=2)
