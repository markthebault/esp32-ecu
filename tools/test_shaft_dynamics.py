"""Analytical mechanics, stopping, boundary and energy checks for the research shaft."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import unittest

from shaft_dynamics import advance_shaft

ROOT = Path(__file__).resolve().parents[1]
CASES = []


class ShaftTests(unittest.TestCase):
    def energy(self, initial, result, inertia=.18):
        residual = (inertia/2*(result['omega_rad_s']**2-initial**2)-result['starter_j']+
                    result['friction_j']+result['load_j']-result['combustion_work_j'])
        self.assertLess(abs(residual), 2e-8)
        return residual

    def test_exact_linear_cranking_and_partition_independence(self):
        inertia = .18
        a, b = 38., (.006+55/350)*30/math.pi
        final = a/b*(-math.expm1(-b*.25/inertia))
        rotation = a/b*(.25+math.expm1(-b*.25/inertia)*inertia/b)
        for step_us in (125, 250, 500, 1000):
            omega = angle = 0.
            for _ in range(250000//step_us):
                result = advance_shaft(omega, step_us/1e6, inertia, 0., True, 5.)
                self.energy(omega, result)
                omega = result['omega_rad_s']; angle += result['rotation_rad']
            self.assertAlmostEqual(omega, final, delta=2e-12)
            self.assertAlmostEqual(angle, rotation, delta=2e-12)
            CASES.append(dict(kind='analytic_cranking', step_us=step_us,
                              omega_rad_s=omega, rotation_rad=angle,
                              expected_omega_rad_s=final, expected_rotation_rad=rotation))

    def test_stopping_has_no_reverse_rotation_or_work_at_rest(self):
        # I*dw/dt=-17-b*w, with an analytic zero-speed time and angle.
        initial, inertia, b = .1, .18, .006*30/math.pi
        stop = inertia/b*math.log1p(b*initial/17)
        rotation = inertia/b*(initial-17/b*math.log1p(b*initial/17))
        result = advance_shaft(initial, .1, inertia, 0., False, 5.)
        self.assertEqual(result['omega_rad_s'], 0.)
        self.assertAlmostEqual(result['rotation_rad'], rotation, delta=1e-13)
        self.energy(initial, result)
        self.assertLess(stop, .1)
        rest = advance_shaft(0., .1, inertia, .01, False, 5.)
        self.assertEqual(rest['omega_rad_s'], 0.)
        self.assertEqual(rest['rotation_rad'], 0.)
        self.assertEqual(rest['combustion_work_j'], 0.)
        self.assertEqual(rest['heat_j'], .01)

    def test_constant_power_equilibria_and_work_partition(self):
        for omega in (1., 19., 20., 25., 350*math.pi/30, 50., 300.):
            for starter in (False, True):
                starter_nm = 55*max(0., 1-omega/(350*math.pi/30)) if starter else 0.
                load = 60.
                opposing = 12+.006*omega*30/math.pi+load-starter_nm
                power = opposing*(20 if omega <= 20 else omega)
                result = advance_shaft(omega, .001, .18, power*.001, starter, load)
                self.assertAlmostEqual(result['omega_rad_s'], omega, delta=2e-12)
                self.assertAlmostEqual(result['rotation_rad'], omega*.001, delta=1e-13)
                self.assertAlmostEqual(result['combustion_work_j'], power*.001*min(1, omega/20), delta=1e-12)
                self.energy(omega, result)

    def test_boundaries_close_independent_work_ledgers(self):
        count = 0
        for omega in (0., .0001, 10., 19.999, 20., 20.001, 30., 350*math.pi/30, 40., 100., 600.):
            for work in (0., .001, 1., 100.):
                for starter in (False, True):
                    for load in (5., 100., -20.):
                        result = advance_shaft(omega, .001, .18, work, starter, load)
                        residual = self.energy(omega, result)
                        self.assertGreaterEqual(result['omega_rad_s'], 0.)
                        self.assertGreaterEqual(result['rotation_rad'], 0.)
                        self.assertGreaterEqual(result['heat_j'], -1e-12)
                        self.assertAlmostEqual(result['combustion_work_j']+result['heat_j'], work, delta=1e-12)
                        CASES.append(dict(kind='boundary_energy', omega_rad_s=omega,
                                          available_work_j=work, starter=starter, load_nm=load,
                                          result=result, energy_residual_j=residual))
                        count += 1
        self.assertEqual(count, 264)

    def test_high_speed_midpoint_refines_against_independent_ode(self):
        # A separate explicit RK4 reference integrates angular speed directly,
        # without the implementation's energy root or work-ledger formulas.
        duration, power, initial, inertia, load = .02, 10000., 50., .18, 5.
        def rate(value):return (power/value-12-.006*value*30/math.pi-load)/inertia
        expected = initial
        h = duration/20000
        for _ in range(20000):
            a = rate(expected); b = rate(expected+h*a/2)
            c = rate(expected+h*b/2); d = rate(expected+h*c)
            expected += h*(a+2*b+2*c+d)/6
        errors = []
        for step_us in (1000, 500, 250, 125):
            omega = initial
            for _ in range(round(duration*1e6/step_us)):
                result = advance_shaft(omega, step_us/1e6, inertia, power*step_us/1e6, False, load)
                self.energy(omega, result); omega = result['omega_rad_s']
            error = abs(omega-expected); errors.append(error)
            CASES.append(dict(kind='independent_ode', step_us=step_us, omega_rad_s=omega,
                              expected_omega_rad_s=expected, absolute_error_rad_s=error))
        self.assertTrue(all(a/b > 3.8 for a, b in zip(errors, errors[1:])), errors)
        self.assertLess(errors[-1], 3e-5)

    def test_complete_input_validation(self):
        defaults = dict(omega=10., duration=.001, inertia=.18, available_work_j=1., starter=False, load_nm=5.)
        for key in ('omega', 'duration', 'inertia', 'available_work_j', 'load_nm'):
            for value in (True, float('nan'), float('inf'), '1'):
                with self.assertRaises(ValueError):advance_shaft(**{**defaults, key:value})
        for key, value in (('omega', -1), ('duration', 0), ('duration', -1),
                           ('inertia', 0), ('available_work_j', -1), ('starter', 1)):
            with self.assertRaises(ValueError):advance_shaft(**{**defaults, key:value})

    def test_rounded_linear_asymptote_is_not_a_finite_crossing(self):
        result=advance_shaft(20.001,10.,.18,0.,True,11.842009426695228)
        self.assertGreaterEqual(result['omega_rad_s'],20.)
        self.assertAlmostEqual(result['omega_rad_s'],20.,delta=1e-12)
        self.energy(20.001,result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args, rest = parser.parse_known_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    sources = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
               ('tools/shaft_dynamics.py', 'tools/test_shaft_dynamics.py', 'tools/engine_research_plant.py')}
    result = unittest.main(argv=[__file__, *rest], exit=False, verbosity=2).result
    unchanged = all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == value for name, value in sources.items())
    (output/'cases.json').write_text(json.dumps(CASES, indent=2, allow_nan=False)+'\n')
    (output/'summary.json').write_text(json.dumps(dict(passed=result.wasSuccessful() and unchanged,
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        source_unchanged=unchanged, source_sha256=sources, saved_cases=len(CASES),
        scope='Declared research shaft integration and conservation; no coupled convergence or physical calibration'), indent=2)+'\n')
    raise SystemExit(not(result.wasSuccessful() and unchanged))
