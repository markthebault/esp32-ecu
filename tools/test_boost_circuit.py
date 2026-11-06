"""Regression boundaries for authored electrical replay of actual control cuts."""
import json
from pathlib import Path
import tempfile
import unittest

from run_boost_circuit import Case, edge_waveform


class ReplayTests(unittest.TestCase):
    def replay(self, rows, **extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'result.json').write_text(json.dumps(dict(completed=True, physical_execution=False,
                                                           duration_s=8, controller='regression')))
            (root/'edges.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            return edge_waveform(Case('cut', edge_run=str(root), edge_start_s=5.9, **extra))

    @staticmethod
    def rows():
        return [dict(sequence=1, time_us=5950000, ch=9, high=True, cause='dispatcher'),
                dict(sequence=2, time_us=6030000, ch=9, high=False, cause='cut:control')]

    def test_control_cut_survives_replay(self):
        waveform = self.replay(self.rows())
        self.assertEqual([r['cause'] for r in waveform['replayed_boost_edges']], ['dispatcher', 'cut:control'])
        self.assertIn('0.13000001 0', waveform['pwl'])

    def test_fixture_halt_is_not_a_natural_cut(self):
        rows = self.rows(); rows[-1]['cause'] = 'fixture_halt'
        with self.assertRaisesRegex(AssertionError, 'fixture terminal'):
            self.replay(rows)

    def test_reordered_sequences_rejected(self):
        rows = self.rows(); rows[-1]['sequence'] = 1
        with self.assertRaisesRegex(AssertionError, 'source sequence'):
            self.replay(rows)

    def test_reversed_clocks_rejected(self):
        rows = self.rows(); rows[-1]['time_us'] = 5940000
        with self.assertRaisesRegex(AssertionError, 'source clock'):
            self.replay(rows)


if __name__ == '__main__':
    unittest.main(verbosity=2)
