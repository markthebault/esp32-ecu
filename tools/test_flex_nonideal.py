"""Numerical setup, scan-exposure and incomplete-matrix regression tests.

These test the experiment implementation. They do not qualify an ADC or board.
"""
import json
import copy
import csv
import gzip
import io
import shutil
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import run_flex_nonideal as m
import analyze_flex_nonideal as analysis


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.scenarios={s.name:s for s in m.scenarios()}
        self.time=np.linspace(0,.22,2201)
        self.arrays={name:np.full_like(self.time,1.65) for name in m.COLUMNS[1:]}
        self.arrays['adc_ref'][:]=3.3

    def queries(self,name):return m.scan_queries(self.scenarios[name],self.time,self.arrays)

    def test_workaround_keeps_the_original_component_equations(self):
        s=replace(self.scenarios['open-filter-witness'],max_step_us=.25)
        before=(m.ROOT/'tools/fixtures/flex-nonideal-open-before-minbreak.cir').read_text()
        after=m.deck(s)
        def equations(text):
            return [line for line in text.splitlines() if line and not line.startswith(('*','.','tran ','run','set ','wrdata ','quit'))]
        self.assertEqual(equations(before),equations(after))
        self.assertIn('.tran 0.25u 220m 0 0.25u',after)
        control=after.split('.control',1)[1]
        self.assertIn('\nrun\n',control);self.assertNotIn('\ntran ',control)
        self.assertIn('minbreak=',after)

    def test_literal_open_does_not_substitute_an_arbitrarily_small_capacitor(self):
        text=m.deck(self.scenarios['open-filter-witness'])
        for token in ('\nC27 ','\nRmodel_C27 ','\nLmodel_C27 '):self.assertNotIn(token,text)
        self.assertIn('\nC27 ',m.deck(self.scenarios['baseline']))

    def test_ideal_point_codes_and_declared_scan_timing(self):
        query=self.queries('baseline')[0]
        self.assertEqual(query['raw'][:4],[2048]*4)
        self.assertEqual(query['adc_ok'],1)
        self.assertEqual(query['control_us'],1000)
        self.assertEqual(query['sampled_us'],167)
        self.assertEqual([x['acquisition_us'][1] for x in query['samples']],list(range(167,504,48)))
        self.assertEqual(query['samples'][7]['conversion_us'],[503,527])

    def test_spi_success_is_not_inferred_from_reference_quality(self):
        self.arrays['adc_ref'][:]=2.99
        self.assertTrue(all(q['adc_ok']==1 for q in self.queries('baseline')))
        self.arrays['adc_ref'][:]=2.6
        with self.assertRaisesRegex(ValueError,'not a rail oracle'):self.queries('baseline')

    def test_original_short_ripple_bursts_are_between_scans(self):
        for name in ('ripple-five','ripple-three'):
            self.assertFalse(any(x['source_ripple_overlaps_acquisition'] or x['source_ripple_overlaps_conversion']
                for q in self.queries(name) for x in q['samples']))

    def test_named_apertures_really_overlap_and_whole_scan_covers_all_channels(self):
        for rail in ('five','three'):
            for suffix,channel in [('map-aperture',0),('rail-aperture',7)]:
                hits={x['channel'] for q in self.queries(f'ripple-{rail}-{suffix}') for x in q['samples'] if x['source_ripple_overlaps_acquisition']}
                self.assertIn(channel,hits)
            hits={x['channel'] for q in self.queries(f'ripple-{rail}-whole-scan') for x in q['samples'] if x['source_ripple_overlaps_acquisition']}
            self.assertEqual(hits,set(range(8)))

    def test_nonzero_phase_does_not_ramp_the_supply_before_the_burst(self):
        s=self.scenarios['ripple-five-rail-aperture'];text=m.supply_wave(s,5,0,.1)
        values=text[4:-1].split();points=[(float(values[i][:-1]),float(values[i+1])) for i in range(0,len(values),2)]
        self.assertEqual(points[:2],[(0.,5.),(s.disturbance_us,5.)])
        self.assertAlmostEqual(points[2][1],5.1)
        self.assertEqual(points[-1],(220000.,5.))

    def test_exposure_counter_tracks_a_changed_scan_phase(self):
        s=replace(self.scenarios['ripple-five-map-aperture'],adc_phase_us=2000)
        queries=m.scan_queries(s,self.time,self.arrays)
        self.assertFalse(any(x['source_ripple_overlaps_acquisition'] for q in queries for x in q['samples']))

    def test_window_range_preserves_interior_reference_excursions(self):
        time=np.array([0.,1.,2.,3.]);values=np.array([3.3,3.0,3.6,3.3])
        self.assertEqual(m.window_range(time,values,500000,2500000),[3.,3.6])

    def matrix(self,output,fail):
        def fake_run(s,*args):
            if fail and s.name=='no-sampling-load':raise RuntimeError('intentional numerical failure')
            return dict(status='complete',scenario=m.asdict(s),raw_rows=1,observations=[],ripple_acquisition_samples=0)
        args=['experiment','--ngspice','unused','--output',str(output),'--cases','baseline','no-sampling-load']
        with patch.object(sys,'argv',args),patch.object(m,'prepare_ngspice',return_value=(Path('unused'),{},{})),patch.object(m,'build_control',return_value=Path('unused')),patch.object(m,'run',side_effect=fake_run):
            m.main()

    def test_aborted_matrix_exposes_partial_results_as_failed(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'run'
            with self.assertRaisesRegex(RuntimeError,'intentional'):self.matrix(out,True)
            result=json.loads((out/'results.json').read_text())
            self.assertEqual(result['status'],'failed');self.assertFalse(result['complete'])
            self.assertEqual(result['completed_case_names'],['baseline'])
            self.assertEqual(result['selected_case_names'],['baseline','no-sampling-load'])
            self.assertEqual(result['active_case'],'no-sampling-load')

    def test_complete_requires_all_planned_cases(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'run';self.matrix(out,False)
            result=json.loads((out/'results.json').read_text())
            self.assertEqual(result['status'],'complete');self.assertTrue(result['complete'])
            self.assertEqual(result['completed_case_names'],result['selected_case_names'])
            self.assertIsNone(result['failure'])
            parent='hardware/a5-idle-interface/net_contract.json'
            self.assertEqual(result['source_sha256'][parent],m.sha(out/'sources'/parent))


class AnalysisTests(unittest.TestCase):
    def test_deck_regeneration_binds_scenario_and_recovers_only_exact_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'experiment';sources=root/'sources'
            parent='hardware/a5-idle-interface/net_contract.json'
            names=['tools/run_flex_nonideal.py','tools/run_flex_circuit.py',str(m.PROFILE),str(m.nominal.FRONTEND),str(m.CORE)]
            for name in names:
                target=sources/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(m.ROOT/name,target)
            folder=root/'baseline';folder.mkdir();path=folder/'circuit.cir'
            text=m.deck(m.Scenario('baseline'));path.write_text(text)
            cases=[dict(scenario=m.asdict(m.Scenario('baseline')))];bound=m.bind()
            recovered=analysis.verify_decks(root,cases,bound,m.ROOT/parent)
            self.assertEqual(recovered[parent]['sha256'],bound['carrier_sha256'])
            self.assertFalse((sources/parent).exists())
            path.write_text(text.replace('Rmodel_F2 bus5 sensor5 4.5','Rmodel_F2 bus5 sensor5 7.5'))
            with self.assertRaisesRegex(ValueError,'Circuit deck differs'):analysis.verify_decks(root,cases,bound,m.ROOT/parent)
            wrong=Path(directory)/'wrong.json';wrong.write_text('{}')
            with self.assertRaisesRegex(ValueError,'pre-run binding'):analysis.verify_decks(root,cases,bound,wrong)

    def test_exact_unique_replay_inventory_is_mandatory(self):
        rows=[dict(rising_fraction=r,falling_fraction=f,strategy=s,calibration_basis=b)
            for r,f in ((.25,.25),(.5,.5),(.75,.75),(.75,.25)) for s in range(3) for b in ('absolute','ratiometric')]
        analysis.require_replays(rows)
        for bad in ([],rows[:-1],rows+[rows[0]],rows[:-1]+[rows[0]]):
            with self.subTest(count=len(bad)),self.assertRaisesRegex(ValueError,'inventory'):analysis.require_replays(bad)

    def test_threshold_label_swaps_and_transcript_aliases_reject(self):
        original=dict(rising_fraction=.25,falling_fraction=.25,strategy=0,calibration_basis='absolute',transcript='baseline/gpio-0.25-0.25-strategy0-absolute.jsonl.gz')
        analysis.require_replay_path('baseline',original)
        for fields in ({'rising_fraction':.75,'falling_fraction':.75},{'transcript':'baseline/gpio-0.5-0.5-strategy0-absolute.jsonl.gz'},{'transcript':'other/gpio-0.25-0.25-strategy0-absolute.jsonl.gz'}):
            with self.subTest(fields=fields),self.assertRaisesRegex(ValueError,'identity/path'):
                analysis.require_replay_path('baseline',dict(original,**fields))

    def test_scan_is_reconstructed_from_raw_before_trusting_metadata(self):
        s=m.Scenario('audit');time=np.linspace(0,.22,2201)
        values={n:np.full_like(time,1.65) for n in m.COLUMNS[1:]};values['adc_ref'][:]=3.3
        expected=analysis.derive_sampling(m.asdict(s),time,values)
        self.assertEqual(expected['queries'][0]['raw'],[2048]*4+[1861,1489,1336,2048])
        self.assertEqual(expected['queries'][0]['sampled_us'],167)
        self.assertEqual(expected['queries'][0]['samples'][7]['conversion_us'],[503.,527.])
        for field,value in [('pin_v',100.),('reference_v',4.),('acquisition_us',[1.,2.]),('reference_range_v',[3.,4.]),('source_ripple_overlaps_acquisition',True)]:
            bad=copy.deepcopy(expected);bad['queries'][0]['samples'][0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'sampling'):
                analysis.same_tree(bad,expected,'sampling')
        bad=copy.deepcopy(expected);bad['queries'][0]['raw'][0]+=1
        with self.assertRaises(ValueError):analysis.same_tree(bad,expected,'sampling')

    def test_stateful_gpio_crossings_and_stimulus_queries_are_checked(self):
        time=np.arange(9)*1e-6;levels=np.array([0,.5,.9,.6,.8,.2,.4,.1,.9])
        edges=analysis.derive_edges(time,levels,.75,.25)
        self.assertEqual([level for _,level in edges],[1,0,1])
        np.testing.assert_allclose([t for t,_ in edges],[1.625,4+11/12,7.8125],rtol=0,atol=1e-12)
        q=[dict(control_us=10.,sampled_us=2.,adc_ok=1,adc_reference_v=3.3,raw=[1]*8)]
        expected=analysis.expected_stimulus(edges,q)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'case').mkdir();path=root/'case/gpio-0.75-0.25.stimulus.txt'
            path.write_text(expected);self.assertEqual(len(analysis.stimulus(root,'case',.75,.25,expected)),3)
            for bad in (expected.replace('E 1.625000000000 1','E 1.625000000000 0'),expected.replace('Q 10.000000000000','Q 11.000000000000'),expected.replace(' 1 1 1 1 1 1 1 1',' 2 1 1 1 1 1 1 1')):
                path.write_text(bad)
                with self.assertRaisesRegex(ValueError,'Stimulus'):analysis.stimulus(root,'case',.75,.25,expected)

    def test_partial_or_old_unlabelled_tables_are_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for value in [dict(cases=[]),dict(status='running',complete=False),dict(status='failed',complete=False,failure={'message':'timeout'})]:
                (root/'results.json').write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError,'partial results'):analysis.load_complete(root)

    def sample(self):
        return dict(cases={'example':dict(scenario={'name':'example','max_step_us':1,'sensor_fuse_ohm':4.5},
            queries=[dict(control_us=1000,sampled_us=167,adc_ok=1,raw=[2000]*8)],
            edge_inputs={'threshold':{'0':[(900,1)]}},replays={'replay':{'canonical_sha256':'same'}})})

    def test_identical_discrete_inputs_require_identical_native_records(self):
        a=self.sample();b=copy.deepcopy(a);b['cases']['example']['replays']['replay']['canonical_sha256']='different'
        with self.assertRaisesRegex(ValueError,'Deterministic'):analysis.compare(a,b)

    def test_code_differences_and_timing_differences_are_not_called_identical(self):
        a=self.sample();b=copy.deepcopy(a);b['cases']['example']['queries'][0]['raw'][0]+=1
        self.assertFalse(analysis.compare(a,b)['example']['identical_discrete_inputs'])
        b=copy.deepcopy(a);b['cases']['example']['queries'][0]['sampled_us']+=1
        self.assertFalse(analysis.compare(a,b)['example']['identical_discrete_inputs'])

    def test_refinement_cannot_change_a_physical_case_parameter(self):
        a=self.sample();b=copy.deepcopy(a);b['cases']['example']['scenario']['sensor_fuse_ohm']=2.5
        with self.assertRaisesRegex(ValueError,'declarations'):analysis.compare(a,b)
        b=copy.deepcopy(a);b['cases']['example']['scenario']['max_step_us']=.25
        self.assertTrue(analysis.compare(a,b)['example']['identical_discrete_inputs'])


class NativeLogAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(Path(__file__).parent/'fixtures/flex-nonideal-msl007.json.gz','rt') as f:cls.snapshots=json.load(f)['entries']

    def test_real_native_logs_match_json_with_faults_and_masked_rail(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'native.msl'
            for snapshot in self.snapshots:
                with self.subTest(case=snapshot['case'],basis=snapshot['basis']):
                    path.write_text(snapshot['msl']);analysis.verify_msl(path,snapshot['frames'])
            low=self.snapshots[-1]['frames']
            self.assertTrue(all(f['controller_faults'] and f['inputs']['sensor_v'] is None for f in low))

    def test_mutating_each_of_the_229_native_columns_rejects(self):
        snapshot=self.snapshots[0];original=list(csv.reader(io.StringIO(snapshot['msl']),delimiter='\t'))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mutated.msl'
            for index,name in enumerate(original[2]):
                rows=copy.deepcopy(original);old=rows[4][index]
                rows[4][index]='0' if old=='NaN' else str(float(old)+1)
                with path.open('w') as f:csv.writer(f,delimiter='\t',lineterminator='\n').writerows(rows)
                with self.subTest(column=name),self.assertRaisesRegex(ValueError,'MSL007 value'):
                    analysis.verify_msl(path,snapshot['frames'])

    def test_missing_rows_changed_units_and_unknown_to_number_reject(self):
        snapshot=self.snapshots[-1];original=list(csv.reader(io.StringIO(snapshot['msl']),delimiter='\t'))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mutated.msl'
            for mutation in ('missing','units','header','unknown','retention','source'):
                rows=copy.deepcopy(original)
                if mutation=='missing':rows.pop()
                elif mutation=='units':rows[3][rows[2].index('MAP')]='V'
                elif mutation=='header':rows[2][rows[2].index('MAP')]='UnboundMAP'
                elif mutation=='retention':rows[1][0]=rows[1][0].replace('retained rows 1..44 of 44','retained rows 2..45 of 100')
                elif mutation=='source':rows[1][0]=rows[1][0].replace('SYNTHETIC ENGINE REPLAY','TARGET CONTROL/SENSOR OBSERVATIONS')
                else:rows[4][rows[2].index('Sensor5V')]='5'
                with path.open('w') as f:csv.writer(f,delimiter='\t',lineterminator='\n').writerows(rows)
                with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,'MSL007'):analysis.verify_msl(path,snapshot['frames'])


if __name__=='__main__':unittest.main(verbosity=2)
