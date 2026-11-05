"""Actual pinned native entry, raw-input bounds and observed boost output tests.

This uses authored inputs to test the adapter. Full free-engine experiments are
separate, and these tests do not qualify physical execution or calibration.
"""
import os
from pathlib import Path
import subprocess
import unittest
from speeduino_turbo_runtime import SpeeduinoTurboRuntime

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(os.environ.get('ECU_SPEEDUINO_TURBO_BIN', str(ROOT / '.cache/engine/speeduino-turbo-011/speeduino-turbo-sim')))


class ProductionTurboTests(unittest.TestCase):
    def runtime(self, **kwargs):
        runtime = SpeeduinoTurboRuntime(REFERENCE, **kwargs)
        self.addCleanup(runtime.close)
        return runtime

    @staticmethod
    def sample(**kwargs):
        return dict(dict(map_kpa=150, tps_pct=60, clt_c=85, iat_c=25, battery_v=14,
                         **{'lambda': 1}), **kwargs)

    def test_production_setup_preserves_all_tables_in_every_mode(self):
        for mode in ('off', 'open_loop', 'closed_loop'):
            runtime = self.runtime(mode=mode)
            self.assertEqual(len(runtime.profile['boost_and_density_raw_maps']), 178)
            self.assertEqual(runtime.profile['frequency_hz'], 24)
            self.assertEqual(runtime.profile['boost_mode'], mode)
            self.assertFalse(runtime.profile['physical_execution'])
            runtime.close()

    def test_invalid_inputs_rejected_before_touching_live_child(self):
        runtime = self.runtime(mode='open_loop')
        for key, invalid in dict(map_kpa=(-1, 401), tps_pct=(-1, 101),
                                 clt_c=(-274, 2001, 1e308), iat_c=(-274, 2001, 1e308),
                                 battery_v=(-1, 25, 1e308), **{'lambda': (0, 3, 1e308)}).items():
            for value in (*invalid, float('nan'), float('inf'), True, '1'):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ValueError):
                        runtime.sensors(self.sample(**{key: value}))
                    self.assertEqual(runtime.now, 0)
                    self.assertIsNone(runtime.process.poll())
        for value in (-1, 60000001, True, .5):
            with self.assertRaises(ValueError):
                runtime.advance(value)
        runtime.sensors(self.sample())
        runtime.advance(1000)
        self.assertEqual(runtime.now, 1000)

    def test_cold_transient_and_finite_sensor_overrange_have_explicit_adc_rails(self):
        runtime = self.runtime(mode='open_loop')
        runtime.sensors(self.sample(iat_c=-100, map_kpa=400))
        self.assertEqual(runtime.raw_adc_counts['iat'], 0)
        self.assertEqual(runtime.raw_adc_counts['map'], 1023)
        runtime.sensors(self.sample(iat_c=1000, **{'lambda': 2}))
        self.assertEqual(runtime.raw_adc_counts['iat'], 1023)
        self.assertEqual(runtime.raw_adc_counts['wideband'], 1023)

    def test_lowered_limit_reloads_and_trips_actual_production_protection(self):
        runtime=self.runtime(mode='open_loop',target=130,cut_kpa=140,protection_rpm=0)
        self.assertEqual(runtime.profile['boost_raw'][3],70)
        runtime.sensors(self.sample())
        for tooth in range(1,501):runtime.advance(tooth*1000,tooth=tooth%60<58)
        self.assertEqual(runtime.boost_status()['boost_cut'],1)
        self.assertEqual(runtime.status()['fuel_channels'],0)
        self.assertEqual(runtime.status()['ignition_channels'],0)

    def test_default_entry_is_neutral_against_frozen_pre_limit_extension(self):
        original=ROOT/'.cache/engine/speeduino-turbo-008/speeduino-turbo-sim'
        if not original.exists():self.skipTest('Historical entry not present; run-specific provenance still required')
        program=['sensors 150 60 85 25 14 14.7','profile','boostmaps','adcstatus']
        for tooth in range(1,3601):
            program.append(('tooth ' if tooth%60<58 else 'advance ')+str(tooth*1000))
        program += ['status','booststatus','halt','quit']
        wire='\n'.join(program)+'\n'
        for mode in ('off','open_loop','closed_loop'):
            rows=[]
            for executable in (original,REFERENCE):
                result=subprocess.run([str(executable),mode,'40','150','--loop-period-us=1000'],input=wire,text=True,capture_output=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr);rows.append(result.stdout)
            self.assertEqual(rows[0],rows[1])

    def test_actual_native_boost_edges_and_unarmed_timer_negative_control(self):
        observed = []
        for unarmed in (False, True):
            runtime = self.runtime(mode='open_loop', default_unarmed_compare=unarmed)
            runtime.sensors(self.sample())
            edges = []
            # A 60-2 wheel at1000rpm drives the real decoder. Without crank
            # input production correctly keeps boost demand at zero.
            for tooth in range(1, 501):
                edges += runtime.advance(tooth*1000, tooth=tooth % 60 < 58)
            boost = [row for row in edges if row[1] == 9]
            observed.append(len(boost))
            self.assertEqual(runtime.boost_status()['duty_pct'], 40)
            if unarmed:
                self.assertEqual(boost, [])
            else:
                self.assertGreater(len(boost), 10)
                self.assertTrue(all(row[0] % 4 == 0 for row in boost))
                self.assertTrue(all(a[2] != b[2] for a, b in zip(boost, boost[1:])))
                rises = [row[0] for row in boost if row[2]]
                self.assertTrue(all(b-a == 41664 for a, b in zip(rises, rises[1:])))
            # The fixture's manual engine halt is separate from natural
            # shutdown and does not disable upstream boost control.
            halt = runtime.halt()
            self.assertFalse(any(row[1] == 9 for row in halt))
            self.assertEqual(runtime.boost_status()['duty_pct'], 40)
            runtime.close()
        self.assertGreater(observed[0], observed[1])

    def test_malformed_raw_ipc_is_rejected_by_native_entry(self):
        commands = [
            'advance -1', 'advance 60000001', 'advance 10\nadvance 9',
            'sensors 401 60 85 25 14 14.7', 'sensors 100 101 85 25 14 14.7',
            'sensors 100 60 1e308 25 14 14.7', 'sensors 100 60 85 1e308 14 14.7',
            'sensors 100 60 85 25 1e308 14.7', 'sensors 100 60 85 25 14 1e308',
            'sensors 100 60 nan 25 14 14.7', 'sensors 100 60 85 25 14', 'invented',
        ]
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run([str(REFERENCE), 'open_loop', '40', '150'],
                                        input=command+'\n', text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stderr.strip())

    def test_solver_subdivision_cannot_change_native_main_loop_cadence(self):
        histories = []
        for step in (250,500,1000):
            runtime = self.runtime(mode='closed_loop')
            runtime.sensors(self.sample())
            program = [(stamp,False) for stamp in range(step,3600001,step)]
            program += [(tooth*1000,True) for tooth in range(1,3601) if tooth % 60 < 58]
            edges = []
            for stamp, tooth in sorted(program):
                edges += runtime.advance(stamp,tooth=tooth)
            histories.append((edges,runtime.boost_status(),runtime.status()))
            runtime.close()
        self.assertEqual(histories[0],histories[1])
        self.assertEqual(histories[1],histories[2])
        self.assertTrue(any(row[1] == 9 and row[2] for row in histories[0][0]))

    def test_corrupted_edge_rows_and_response_intervals_fail(self):
        runtime = self.runtime(mode='open_loop')
        pin = next(iter(runtime.pin_map))
        for line in ('boostedge -1 1', 'boostedge 60000001 1', 'boostedge 10 2',
                     'boostedge 5 1 extra', f'edge 10 {pin} 2 0 360',
                     f'edge 10 {pin} 1 3 360', 'edge 10 999 1 0 360'):
            with self.subTest(line=line):
                with self.assertRaises(RuntimeError):
                    runtime._edges([line])
        actual = runtime.command
        runtime.command = lambda text: ['boostedge 1001 1']
        with self.assertRaises(RuntimeError):
            runtime.advance(1000)
        self.assertEqual(runtime.now, 0)
        runtime.command = actual


if __name__ == '__main__':
    unittest.main(verbosity=2)
