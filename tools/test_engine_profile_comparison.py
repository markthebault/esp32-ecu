"""Coupled1..8-cylinder project/production-reference research comparisons.

Both controllers drive independent copies of the same declared physical plant.
Fallbacks unable to represent that geometry are explicit diagnostic controls.
No controller or plant is fitted to match the other's resulting RPM trace.
"""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from compare_engine_controllers import run,benchmark_tune
from engine_geometry import EngineGeometry,channel_kind

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=None;BINARY=None;RESULTS={}
MODES=('batch_wasted','semi_sequential','sequential')


def profile(count,strategy):
    t=benchmark_tune();t['engine'].update(cylinders=count,displacement_cc=500*count)
    t['strategy']=strategy;t['timing']['firing_order']=[1,*range(count,1,-1),*([0]*(8-count))]
    return t


def execute(n,mode,controller,scenario='warm_start',duration=4,step=250,**extra):
    tune=profile(n,mode);geometry=EngineGeometry.from_tune(tune)
    options=(dict(tune=tune,target_dispatcher=True)if controller=='ours'else
        dict(reference_profile_fixture=BINARY,sequential=mode=='sequential',semi_sequential=mode=='semi_sequential'))
    return run(controller,scenario,duration,step,plant_geometry=geometry,**options,**extra)


def record(name,result,category):
    RESULTS[name]=dict(category=category,summary=result['summary'])
    (OUTPUT/(name+'.json.gz')).write_bytes(gzip.compress(json.dumps(result,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    return result['summary']


class ComparisonTests(unittest.TestCase):
    def ledger_and_shutdown(self,r):
        s=r['summary'];self.assertFalse(s['physical_outputs_enabled']);self.assertEqual(s['final_outputs_high'],0)
        for key,limit in (('fuel_residual_mg',1e-7),('chemical_residual_j',1e-5),('shaft_residual_j',1e-5),('air_residual_kg',1e-8),('air_energy_residual_j',.02)):
            self.assertLess(abs(s['ledger'][key]),limit,(key,s['ledger']))
        self.assertAlmostEqual(sum(s['cylinder_fuel_mg']),s['ledger']['fuel_in_mg'],delta=1e-7)
        self.assertTrue(all(channel_kind(row[1])is not None for row in r['edges']))

    def test_01_all24_requested_profiles_use_independent_free_shaft_plants(self):
        for n in range(1,9):
            for mode in MODES:
                for controller in ('ours','speeduino'):
                    with self.subTest(cylinders=n,mode=mode,controller=controller):
                        mismatch=controller=='speeduino'and n in (2,7)and mode!='sequential'
                        extra=dict(reference_allow_geometry_mismatch=True)if mismatch else {}
                        r=execute(n,mode,controller,**extra)
                        s=record(f'baseline-{n}-{mode}-{controller}',r,'unsupported_reference_geometry_diagnostic'if mismatch else'normal_profile')
                        self.ledger_and_shutdown(r)
                        self.assertEqual(s['plant_geometry'],EngineGeometry.from_tune(profile(n,mode)).summary())
                        if mismatch:
                            self.assertTrue(s['reference_profile']['physical_geometry_issues'])
                            if n==7:self.assertLess(len({row[1]for row in r['edges']}),14)
                        else:
                            self.assertGreater(s['final_rpm'],500)
                            self.assertTrue(all(v>0 for v in s['cylinder_burned_mg']))
                            self.assertTrue(all(v>0 for v in s['cylinder_shaft_j']))
                            # Our scheduler has its own bound. Production
                            # timing is measured comparison data, not forced
                            # to satisfy an invented common transient bound.
                            # Static geometry/phase is checked independently
                            # by test_speeduino_profiles.py.
                            if controller=='ours':self.assertLess(s['max_spark_error_after_3s_deg'],1.5)
                        if controller=='ours':
                            self.assertLessEqual(s['max_injector_high_us'],15000);self.assertLessEqual(s['max_dwell_high_us'],3500)
                            self.assertFalse(s['protection_stops'])

    def test_02_incompatible_fallbacks_require_explicit_diagnostic_opt_in(self):
        for n in (2,7):
            for mode in ('batch_wasted','semi_sequential'):
                with self.assertRaisesRegex(ValueError,'explicit diagnostic opt-in'):execute(n,mode,'speeduino',duration=1)
        with self.assertRaises(ValueError):
            run('speeduino',plant_geometry=EngineGeometry(8,tuple(range(1,9)),4000),duration=1)

    def test_03_faults_cut_extended_project_channels_and_keep_reference_behavior_visible(self):
        for scenario in ('trigger_dropout','sensor_short','cam_dropout'):
            for controller in ('ours','speeduino'):
                r=execute(8,'sequential',controller,scenario,duration=6)
                s=record(f'fault-8-{scenario}-{controller}',r,'fault_comparison')
                self.ledger_and_shutdown(r)
                self.assertTrue(any(row[1]==17 for row in r['edges']))
                if controller=='ours':
                    self.assertTrue(s['project_fault_mask_seen']or s['protection_stops'])
                    self.assertLessEqual(s['max_injector_high_us'],15000);self.assertLessEqual(s['max_dwell_high_us'],3500)
                    if scenario=='trigger_dropout':
                        deadline=s['dropout_accepted_crank_watchdog']['deadline_us'];end=s['dropout_raw_gap_us'][1]
                        self.assertFalse(any(row[2]for row in r['edges']if deadline<row[0]<end))

    def test_04_fixed_physical_geometry_reveals_wrong_controller_order_and_reference_wiring(self):
        tune=profile(8,'sequential');g=EngineGeometry.from_tune(tune)
        wrong=copy.deepcopy(tune);wrong['timing']['firing_order']=list(range(1,9))
        for controller in ('ours','speeduino'):
            r=(run('ours','warm_start',4,250,tune=wrong,target_dispatcher=True,plant_geometry=g)if controller=='ours'else
               execute(8,'sequential','speeduino',reference_wiring_order=tuple(range(1,9))))
            s=record('wrong-wiring-8-'+controller,r,'fixed_geometry_causal_control');self.ledger_and_shutdown(r)
            baseline=RESULTS['baseline-8-sequential-'+controller]['summary']
            self.assertEqual(s['plant_geometry'],baseline['plant_geometry'])
            self.assertEqual(s['plant_air_parameters'],baseline['plant_air_parameters'])
            self.assertGreater(s['max_spark_error_deg'],80)
            self.assertLess(s['ledger']['combustion_shaft_j'],baseline['ledger']['combustion_shaft_j']*.8)

    def test_05_step_refinement_bounds_numerical_sensitivity(self):
        for n,mode in ((1,'batch_wasted'),(7,'sequential'),(8,'sequential')):
            for controller in ('ours','speeduino'):
                previous=RESULTS[f'baseline-{n}-{mode}-{controller}']['summary']
                for step in (125,100):
                    r=execute(n,mode,controller,step=step)
                    s=record(f'refine-{step}-{n}-{mode}-{controller}',r,'numerical_refinement');self.ledger_and_shutdown(r)
                    for key in ('final_rpm','mean_final_second_rpm'):
                        self.assertLess(abs(s[key]-previous[key])/max(abs(previous[key]),1),.03 if step==125 else .01,(n,mode,controller,step,key))
                    self.assertLess(abs(s['ledger']['combustion_shaft_j']-previous['ledger']['combustion_shaft_j'])/max(previous['ledger']['combustion_shaft_j'],1),.04 if step==125 else .02)
                    previous=s


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args,rest=parser.parse_known_args();BINARY=args.executable.resolve();OUTPUT=args.output.resolve()
    OUTPUT.mkdir(parents=True,exist_ok=False)
    names=('tools/test_engine_profile_comparison.py','tools/compare_engine_controllers.py','tools/speeduino_profiles_runtime.py',
           'tools/speeduino_profiles_sim.cpp','scripts/build_speeduino_profiles.py','tools/engine_geometry.py',
           'tools/engine_research_plant.py','tools/engine_runtime.py','tools/target_runtime.py')
    sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in names}
    result=unittest.main(argv=[__file__,*rest],verbosity=2,exit=False).result
    unchanged=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in sources.items())
    summary=dict(passed=result.wasSuccessful()and unchanged,source_unchanged=unchanged,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),cases=RESULTS,source_sha256=sources,
        fixture_manifest=json.loads(BINARY.with_name('build-manifest.json').read_text()),
        profile_air_manifest=json.loads((ROOT/'.cache/engine/modelica-mvem/airpath-profiles/manifest.json').read_text()),
        scope='Actual native project target dispatcher and production Speeduino on independent uncalibrated MVEM/free-shaft plants; explicit unsupported fallback, fixed geometry causal, fault and numerical controls; no hardware or engine qualification')
    (OUTPUT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    raise SystemExit(not summary['passed'])
