"""Physical intake/pulse boundaries, causal fuel transfer and atomic rollback."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import unittest
from engine_geometry import EngineGeometry
from engine_research_plant import ResearchPlant,next_intake_closing
from boost_research_plant import BoostResearchPlant

ROOT=Path(__file__).resolve().parents[1]
CASES=[]


class ConstantAir:
    def __init__(self,geometry,time=0.):
        self.geometry=geometry;self.time=time;self.calls=[]
        self.initial=dict(map_kpa=100.,temperature_k=298.15,cylinder_air_kg_s=.01,
            inventory_kg=0.,inventory_j=0.,accumulated_inlet_kg=0.,accumulated_outlet_kg=0.,
            accumulated_inlet_j=0.,accumulated_outlet_j=0.)
    def step(self,t,dt,*args):
        self.calls.append((t,dt));self.time=t+dt;return dict(self.initial)
    def close(self):pass


def fixture(angle=629.999,time=.0009):
    geometry=EngineGeometry(1,(1,),500)
    plant=ResearchPlant(air_path=ConstantAir(geometry,time),geometry=geometry)
    plant.rpm=1000.;plant.angle=angle
    plant.edge(0,True,0.)
    plant.starter_j=.5*plant.rotor_inertia*(plant.rpm*math.pi/30)**2
    return plant


def analytic_crossing(degrees):
    # Direct integration of I*omega'=-17-b*omega. No production solver call.
    omega=1000*math.pi/30;b=.006*30/math.pi;equilibrium=-17/b;k=b/.18
    def angle(t):return equilibrium*t+(omega-equilibrium)*(-math.expm1(-k*t))/k
    low,high=0.,.001
    for _ in range(60):
        mid=(low+high)/2
        if angle(mid)<degrees*math.pi/180:low=mid
        else:high=mid
    return high


class IntakeTests(unittest.TestCase):
    def test_fuel_after_closing_stays_out_of_frozen_charge(self):
        crossing=analytic_crossing(.001);flow=300*.745/60*1000
        expected=flow*crossing-.05*flow*.05*(-math.expm1(-crossing/.05))
        for step in (.0005,.00025):
            p=fixture();p.integrate(.0009,step,False,5.)
            self.assertEqual(len(p.intake_events),1)
            self.assertAlmostEqual(p.charge_mg[0],expected,delta=1e-10)
            self.assertLessEqual(p.charge_mg[0],flow*crossing+1e-10)
            self.assertGreater(p.port_mg[0],p.charge_mg[0]*1000)
            event=p.intake_events[0]
            self.assertAlmostEqual(event['time_s'],.0009+crossing,delta=1e-13)
            self.assertAlmostEqual(event['shaft_angle_deg'],630.,delta=1e-8)
            frozen=p.charge_mg[0];p.integrate(.0009+step,step)
            self.assertEqual(p.charge_mg[0],frozen)
            self.assertLess(abs(p.ledger()['fuel_residual_mg']),1e-10)
            CASES.append(dict(kind='causal_intake',step_s=step,expected_trapped_fuel_mg=expected,
                              event=event,post_close_port_fuel_mg=p.port_mg[0]))

    def test_deadtime_after_closing_cannot_supply_the_charge(self):
        p=fixture(angle=629.9,time=.0008)
        p.integrate(.0008,.0005)
        self.assertEqual(len(p.intake_events),1)
        self.assertLess(p.intake_events[0]['time_s'],.0009)
        self.assertEqual(p.charge_mg[0],0.)
        self.assertGreater(p.port_mg[0],1.)
        self.assertTrue(any(abs(t-.0009)<1e-15 for t,_ in p.air.calls))

    def test_wall_film_has_the_constant_source_analytical_solution(self):
        results=[];flow=300*.745/60*1000
        for count in (1,2,4,8):
            p=fixture();p.rpm=0.;p.angle=0.
            p.wall_mg[0]=7.;p.port_mg[0]=3.;p.fuel_mg=10.;p.cylinder_fuel_mg[0]=10.
            for index in range(count):p.integrate(.0009+index*.001/count,.001/count)
            decay=-math.expm1(-.001/.05)
            expected=7*(1-decay)+.05*flow*.05*decay
            self.assertAlmostEqual(p.wall_mg[0],expected,delta=2e-12)
            self.assertAlmostEqual(p.port_mg[0],3+flow*.001+7-expected,delta=2e-12)
            self.assertLess(abs(p.ledger()['fuel_residual_mg']),1e-11)
            results.append((p.wall_mg[0],p.port_mg[0]))
        for left in results[1:]:
            for a,b in zip(left,results[0]):self.assertAlmostEqual(a,b,delta=2e-12)

    def test_combustion_power_stops_at_its_declared_endpoint(self):
        values=[]
        for count in (1,5):
            p=fixture(angle=0.,time=0.);p.injector_on=[None];p.rpm=50*30/math.pi
            p.combustions=[dict(start=0.,end=.0002,rate=5000.,remaining=1.,cylinder=0)]
            for index in range(count):p.integrate(index*.001/count,.001/count)
            self.assertFalse(p.combustions)
            self.assertAlmostEqual(p.combustion_shaft_j,1.,delta=1e-13)
            self.assertAlmostEqual(p.air.calls[0][1],.0002,delta=1e-15)
            values.append((p.rpm,p.angle,p.combustion_shaft_j))
        for a,b in zip(*values):self.assertAlmostEqual(a,b,delta=1e-11)

    def test_turbo_failure_after_closing_cannot_leak_intake_history(self):
        p=BoostResearchPlant(geometry=EngineGeometry(1,(1,),500));self.addCleanup(p.close)
        p.rpm=1000.;p.angle=629.9;p.starter_j=.5*p.rotor_inertia*(p.rpm*math.pi/30)**2
        before=copy.deepcopy(p.ledger());state=list(p.air.state);original=p.air.rates;calls=0
        def failure(*args):
            nonlocal calls
            calls+=1
            # Four RK stages and the validated candidate complete the first
            # gas interval. The sixth call occurs after its intake record.
            if calls==6:raise ValueError('Failure after first intake closing')
            return original(*args)
        p.air.rates=failure
        with self.assertRaisesRegex(ValueError,'first intake'):p.integrate(0,.0005)
        self.assertEqual(p.ledger(),before);self.assertEqual(p.air.state,state)
        self.assertEqual(p.intake_events,[]);self.assertEqual(p.air.time,0.)

    def test_split_duration_preserves_pending_energy_at_large_absolute_time(self):
        p=BoostResearchPlant(geometry=EngineGeometry(1,(1,),500));self.addCleanup(p.close)
        p.air.time=20.;p.rpm=1000.;p.angle=629.999
        p.starter_j=.5*p.rotor_inertia*(p.rpm*math.pi/30)**2
        # Authored pending inventory from an earlier exchange, not a claim of
        # reachable engine pumping work during this one-microsecond interval.
        p.pumping_work_j=p.pending_pumping_j=100.
        p.integrate(20.,1e-6)
        ledger=p.ledger()
        residual=ledger['pumping_work_j']-ledger['turbo_gas']['pumping']-ledger['pending_pumping_exchange_j']
        self.assertLess(abs(residual),1e-10)
        self.assertEqual(len(p.intake_events),1)
        self.assertLess(abs(ledger['coupled_energy_residual_j']),1e-6)

    def test_fractional_closing_is_neither_repeated_nor_skipped(self):
        for n in range(1,9):
            geometry=EngineGeometry(n,(1,*range(n,1,-1)),500*n)
            for tdc in geometry.compression_tdc_deg:
                phase=tdc-180
                for cycle in range(1,21):
                    boundary=phase+720*cycle
                    for angle in (math.nextafter(boundary,-math.inf),boundary,math.nextafter(boundary,math.inf)):
                        expected=min(phase+720*k for k in range(cycle-2,cycle+4)if phase+720*k>angle)
                        self.assertEqual(next_intake_closing(angle,phase),expected)
        starts=((7,1144.2857142857142,0),(7,835.7142857142857,1),
                (7,8241.42857142857,0),(8,1979.9999999999998,1))
        for n,angle,count in starts:
            geometry=EngineGeometry(n,(1,*range(n,1,-1)),500*n)
            p=ResearchPlant(air_path=ConstantAir(geometry),geometry=geometry);p.rpm=1000.;p.angle=angle
            original=p._shaft_interval;calls=0
            def bounded(*args):
                nonlocal calls
                calls+=1
                if calls>200:raise AssertionError('Non-advancing intake boundary')
                return original(*args)
            p._shaft_interval=bounded;p.integrate(0.,1e-6)
            self.assertEqual(len(p.intake_events),count)
            self.assertGreater(p.angle,angle)
            CASES.append(dict(kind='fractional_boundary',cylinders=n,initial_angle_deg=angle,
                              expected_closings=count,actual_closings=len(p.intake_events),solver_calls=calls))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args,rest=parser.parse_known_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    names=('tools/test_intake_integration.py','tools/shaft_dynamics.py','tools/engine_research_plant.py',
           'tools/boost_research_plant.py','tools/engine_geometry.py')
    sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in names}
    result=unittest.main(argv=[__file__,*rest],exit=False,verbosity=2).result
    unchanged=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in sources.items())
    (out/'cases.json').write_text(json.dumps(CASES,indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(passed=result.wasSuccessful()and unchanged,
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),source_unchanged=unchanged,
        source_sha256=sources,scope='Authored causal boundary/transport/rollback fixtures, not physical engine qualification'),indent=2)+'\n')
    raise SystemExit(not(result.wasSuccessful()and unchanged))
