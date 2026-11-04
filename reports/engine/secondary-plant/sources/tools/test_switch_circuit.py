"""Reject stale SPICE/CAD binding without mutating the project hardware."""
import copy,json,tempfile,unittest
from pathlib import Path
import run_switch_circuit as circuit

class SwitchCircuitBindingTests(unittest.TestCase):
 def test_current_literal_binding(self):
  self.assertEqual(len(circuit.binding()['literal_resistors_ohm']),22)
 def test_each_modeled_part_value_pin_and_identity_change_rejects(self):
  root=circuit.ROOT;accessory=json.loads((root/'hardware/switch-inputs/net_contract.json').read_text());carrier=json.loads((root/'hardware/a5-idle-interface/net_contract.json').read_text())
  mutations=[]
  for part in accessory['parts']:
   ref=part['reference']
   if ref.startswith(('R','C','D','Q','U','J')):
    for pin in part['pins']:
     if part['pins'][pin] is not None:mutations.append((ref,'pins',pin,'WRONG_NET'))
   if ref.startswith(('R','C')):mutations.append((ref,'value',None,'WRONG_VALUE'))
   if ref.startswith(('D','Q','U')):mutations.append((ref,'mpn',None,'WRONG_DEVICE'))
  with tempfile.TemporaryDirectory() as directory:
   task_root=Path(directory);a=task_root/'hardware/switch-inputs/net_contract.json';b=task_root/'hardware/a5-idle-interface/net_contract.json';a.parent.mkdir(parents=True);b.parent.mkdir(parents=True);b.write_text(json.dumps(carrier))
   try:
    circuit.ROOT=task_root
    for ref,key,pin,value in mutations:
     bad=copy.deepcopy(accessory);part=next(p for p in bad['parts']if p['reference']==ref)
     if pin is None:part[key]=value
     else:part[key][pin]=value
     a.write_text(json.dumps(bad))
     with self.subTest(ref=ref,key=key,pin=pin),self.assertRaises(AssertionError):circuit.binding()
   finally:circuit.ROOT=root
 def test_deck_records_distinct_bus_source_and_remaining_unknowns(self):
  text=circuit.deck(circuit.Case('bus-fed',supply=0,power_connected=False,bus_v=3.63))
  self.assertIn('Vbus bus_source 0 3.63',text);self.assertIn('i(Vsupply) i(Vbus)',text)
  self.assertIn('Generic assumed models',text);self.assertIn('Idealized supervisor static behavior ONLY',text)

if __name__=='__main__':unittest.main()
