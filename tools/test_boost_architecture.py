"""Guard the unrouted boost interface candidate against its exact A6 parent."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

def validate(candidate,parent):
    if candidate['physical_outputs_enabled'] is not False or candidate['module']['firmware_allocation_active'] is not False:
        raise ValueError('Development candidate must remain inactive')
    refs={p['ref']:p for p in parent['parts']};module=candidate['module'];part=refs[module['reference']]
    if module['gpio']!=45 or module['pad']!='37' or part['names'][module['pad']]!='45' or part['pins'][module['pad']] is not None:
        raise ValueError('GPIO45 pad is not the declared unused A6 binding')
    if candidate['logic_interface']['candidate_connector'] in refs:raise ValueError('Candidate connector reference already allocated')
    if module['permanent_carrier_pulldown_ohm']!=2200:raise ValueError('Permanent input bias differs')
    if candidate['carrier_outline_limit_mm']!=[120,120]:raise ValueError('Carrier outline contract differs')

class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=json.loads((ROOT/'hardware/boost-control/architecture.json').read_text())
        source=ROOT/cls.c['parent']['path']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==cls.c['parent']['sha256']
        cls.parent=json.loads(source.read_text())

    def test_candidate_binds_exact_parent(self):validate(self.c,self.parent)

    def test_existing_rgb_header_cannot_be_reused(self):
        c=copy.deepcopy(self.c);c['logic_interface']['candidate_connector']='J23'
        with self.assertRaisesRegex(ValueError,'already allocated'):validate(c,self.parent)

    def test_reserved_psram_pin_or_active_allocation_rejects(self):
        c=copy.deepcopy(self.c);c['module']['gpio']=35;c['module']['pad']='33'
        with self.assertRaisesRegex(ValueError,'GPIO45'):validate(c,self.parent)
        c=copy.deepcopy(self.c);c['module']['firmware_allocation_active']=True
        with self.assertRaisesRegex(ValueError,'inactive'):validate(c,self.parent)

if __name__=='__main__':unittest.main(verbosity=2)
