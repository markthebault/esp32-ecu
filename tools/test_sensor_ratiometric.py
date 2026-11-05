"""Real profile parser/converter/filter, migration and host persistence checks."""
import copy
import ctypes
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from web_server import Device, Reading, R, canonical_profile, load_bridge


def legacy(profile):
    p=copy.deepcopy(profile);p['schema_version']=1
    for sensor in p['sensors']:
        sensor.pop('ratiometric');sensor.pop('reference_supply_v')
    return p


class RatiometricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge=load_bridge()
        cls.defaults=json.loads((R/'config/defaults.json').read_text())

    def setUp(self):
        self.p=copy.deepcopy(self.defaults)
        self.p['sensors'][0].update(mode='linear',unit='kPa',confirmed=True,
            v0=.5,y0=10,v1=4.5,y1=110,ratiometric=True)

    def valid(self,p):
        return bool(self.bridge.validate_profile(json.dumps(p).encode()))

    def raw(self,signal,supply,reference=3.3):
        adc=lambda v:max(0,min(4095,math.floor(4096*v/reference)))
        return (ctypes.c_uint*8)(adc(signal*.6),*[adc(2*.6)]*5,
                                  adc(14/13),adc(supply*.6))

    def evaluate(self,raw,previous=None,dt=5,reset=True):
        body=json.dumps(self.p).encode();basis=(ctypes.c_double*6)()
        old=(ctypes.c_double*6)(*(previous or [0]*6))
        self.assertEqual(self.bridge.filter_profile(body,raw,old,dt,reset,True,basis),1)
        out=(Reading*6)()
        self.assertEqual(self.bridge.evaluate_profile(body,raw,basis,out),1)
        return out,list(basis)

    def test_defaults_explicitly_disable_compensation(self):
        self.assertEqual(self.defaults['schema_version'],2)
        self.assertTrue(all(not s['ratiometric'] and s['reference_supply_v']==5
                            for s in self.defaults['sensors']))

    def test_quantized_linear_and_table_pressure_sweep(self):
        for mode in ('linear','table'):
            self.p['sensors'][0].update(mode=mode,points=[dict(v=.5,value=10),dict(v=2.1,value=50),dict(v=4.5,value=110)])
            for supply in (4.75,4.8,4.9,5.,5.25):
                out,_=self.evaluate(self.raw(.42*supply,supply))
                self.assertTrue(out[0].valid,out[0].fault)
                self.assertAlmostEqual(out[0].value,50,delta=.08)
                self.assertAlmostEqual(out[0].sensor_v,.42*supply,delta=.002)
                self.assertAlmostEqual(out[0].transfer_v,2.1,delta=.003)

    def test_supply_reference_error_cancels_in_ratio_but_absolute_profile_is_preserved(self):
        out,_=self.evaluate(self.raw(2.1,5,3.4))
        self.assertAlmostEqual(out[0].value,50,delta=.08)
        self.p['sensors'][0]['ratiometric']=False
        out,_=self.evaluate(self.raw(2.016,4.8))
        self.assertAlmostEqual(out[0].value,47.9,delta=.05)

    def test_invalid_and_incomplete_schema2_rejected(self):
        for field,value in [('ratiometric',1),('reference_supply_v',None),('reference_supply_v',3.99),('reference_supply_v',5.31)]:
            p=copy.deepcopy(self.p);p['sensors'][0][field]=value;self.assertFalse(self.valid(p))
        for field in ('ratiometric','reference_supply_v'):
            p=copy.deepcopy(self.p);del p['sensors'][0][field];self.assertFalse(self.valid(p))
        for mode in ('voltage','ntc_beta'):
            p=copy.deepcopy(self.p);p['sensors'][2].update(mode=mode,ratiometric=True,pullup_fitted=True);self.assertFalse(self.valid(p))
        p=legacy(self.p);p['sensors'][0]['ratiometric']=False;self.assertFalse(self.valid(p))

    def test_raw_fault_precedes_compensated_conversion(self):
        self.p['sensors'][0]['fault_low_v']=.45
        out,_=self.evaluate(self.raw(.43,4))
        self.assertFalse(out[0].valid);self.assertIn(b'below',out[0].fault)

    def test_profile1_load_preserves_saved_bytes_and_explicitly_disables_ratio(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profile.json';old=legacy(self.p);original=json.dumps(old,indent=3).encode();path.write_bytes(original)
            d=Device(path,self.bridge)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(d.profile['schema_version'],2)
            self.assertTrue(all(not s['ratiometric'] and s['reference_supply_v']==5 for s in d.profile['sensors']))
            self.assertEqual(d.profile['sensors'][0]['confirmed'],old['sensors'][0]['confirmed'])
            code,saved=d.save(json.dumps(d.profile).encode());self.assertEqual(code,200)
            self.assertEqual(saved['revision'],2);self.assertEqual(json.loads(path.read_bytes()),saved)
            self.assertEqual(Device(path,self.bridge).profile,saved)

    def test_legacy_put_migrates_before_commit_and_retains_cas(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Device(Path(folder)/'profile.json',self.bridge)
            code,saved=d.save(json.dumps(legacy(self.p)).encode());self.assertEqual(code,200)
            self.assertEqual(saved['schema_version'],2);self.assertFalse(saved['sensors'][0]['ratiometric'])
            previous=d.path.read_bytes()
            self.assertEqual(d.save(json.dumps(legacy(self.p)).encode())[0],409)
            self.assertEqual(d.path.read_bytes(),previous)

    def test_invalid_migration_and_failed_save_preserve_file_and_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profile.json';path.write_text(json.dumps(legacy(self.p)))
            d=Device(path,self.bridge);original=path.read_bytes();before=copy.deepcopy(d.profile)
            p=legacy(self.p);p['sensors'][0]['reference_supply_v']=5
            self.assertEqual(d.save(json.dumps(p).encode())[0],422)
            self.assertEqual(path.read_bytes(),original);self.assertEqual(d.profile,before)
            with patch('web_server.os.replace',side_effect=OSError('injected failed atomic replace')):
                self.assertEqual(d.save(json.dumps(self.p).encode())[0],507)
            self.assertEqual(path.read_bytes(),original);self.assertEqual(d.profile,before)

    def test_supply_step_filter_and_invalid_supply_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Device(Path(folder)/'profile.json',self.bridge);self.assertEqual(d.save(json.dumps(self.p).encode())[0],200)
            d.started=100
            with patch('web_server.time.monotonic',return_value=100):first=d.status()
            d.faults['map']='rail_4v8'
            with patch('web_server.time.monotonic',return_value=100.005):second=d.status()
            a,b=first['sensors'][0],second['sensors'][0]
            self.assertLess(b['sensor_v'],a['sensor_v']-.08)
            self.assertAlmostEqual(a['value'],b['value'],delta=.04)
            self.assertTrue(b['valid']);self.assertAlmostEqual(second['sensor_5v'],4.8,delta=.002)
            d.faults['map']='rail'
            with patch('web_server.time.monotonic',return_value=100.010):bad=d.status()
            self.assertFalse(bad['sensors'][0]['valid']);self.assertIsNone(bad['sensors'][0]['value'])
            self.assertIsNone(bad['sensors'][0]['transfer_voltage_v']);json.dumps(bad,allow_nan=False)
            d.faults['map']='normal'
            with patch('web_server.time.monotonic',return_value=100.015):recovered=d.status()
            r=recovered['sensors'][0];self.assertTrue(r['valid'])
            self.assertEqual(r['transfer_voltage_v'],r['display_transfer_voltage_v'])

    def test_envelope_and_roundtrip(self):
        for body in (json.dumps(self.p).encode()+b'\0',b' '*16385):
            with self.assertRaises(ValueError):canonical_profile(self.bridge,body)
        self.assertEqual(canonical_profile(self.bridge,json.dumps(self.p).encode()),self.p)


if __name__=='__main__':unittest.main(verbosity=2)
