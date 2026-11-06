"""Detect stale or miswired literal circuit/model binding, without editing CAD."""
import copy,json,tempfile,unittest
from pathlib import Path
import run_flex_circuit as circuit

class FlexFrontendBinding(unittest.TestCase):
 def test_current_literal_topology(self):
  self.assertEqual(len(circuit.binding()['resistors_ohm']),12)
 def test_each_modeled_pin_value_or_identity_change_is_rejected(self):
  root=circuit.ROOT;front=json.loads((root/circuit.FRONTEND).read_text());carrier=(root/'hardware/a5-idle-interface/net_contract.json').read_bytes();mutations=[]
  for part in front['parts']:
   for pin in part['pins']:mutations.append((part['ref'],'pins',pin,'WRONG_NET'))
   for field in ('ohm','farad'):
    if field in part:mutations.append((part['ref'],field,None,part[field]*2))
   if 'mpn'in part:mutations.append((part['ref'],'mpn',None,'WRONG_DEVICE'))
  with tempfile.TemporaryDirectory()as directory:
   task_root=Path(directory);path=task_root/circuit.FRONTEND;path.parent.mkdir(parents=True);old=task_root/'hardware/a5-idle-interface/net_contract.json';old.parent.mkdir(parents=True);old.write_bytes(carrier)
   try:
    circuit.ROOT=task_root
    for ref,key,pin,value in mutations:
     changed=copy.deepcopy(front);part=next(p for p in changed['parts']if p['ref']==ref)
     if pin is None:part[key]=value
     else:part[key][pin]=value
     path.write_text(json.dumps(changed))
     with self.subTest(ref=ref,key=key,pin=pin),self.assertRaises(AssertionError):circuit.binding()
   finally:circuit.ROOT=root
 def test_off_supply_is_disconnected_and_actual_bleed_is_present(self):
  text=circuit.deck(circuit.Case('off',powered=False,rail5=0,rail33=0,fault_v=36))
  self.assertIn('R33wire supply33 rail33 1000000000000.0',text);self.assertIn('Rcarrier7 rail33 0 100',text)
  self.assertIn('Generic GPIO protection equivalents',text);self.assertIn('Authored assumed equivalents',text)
 def test_clamp_filter_are_upstream_of_immediate_feedback(self):
  text=circuit.deck(circuit.Case('bound'))
  self.assertIn('D213 0 flex_input_mid DFEED',text);self.assertIn('C158 flex_input_mid 0 4.7e-11',text)
  self.assertIn('R160 flex_cmp flex_in 330000',text);self.assertNotIn('C158 flex_in ',text)
 def test_explicit_compact_profile_has_both_rail_bypasses(self):
  profile=Path('hardware/flex-input/frontend-compact.json')
  bound=circuit.binding(profile)
  self.assertEqual(bound['modeled_capacitors_farad']['C164'],1e-7)
  self.assertEqual(bound['unmodeled_package_changes'],['J20'])
  text=circuit.deck(circuit.Case('compact'),profile)
  self.assertIn('C160 rail5 0 1e-07',text)
  self.assertIn('C164 rail33 0 1e-07',text)
  self.assertNotIn('C164 ',circuit.deck(circuit.Case('legacy')))
 def test_compact_graph_identity_values_and_structural_corruption_are_rejected(self):
  profile=Path('hardware/flex-input/frontend-compact.json');root=circuit.ROOT
  front=json.loads((root/profile).read_text());mutations=[]
  for index,part in enumerate(front['parts']):
   for pin in part['pins']:
    changed=copy.deepcopy(front);changed['parts'][index]['pins'][pin]='WRONG_NET';mutations.append((f"{part['ref']} pin{pin}",changed))
   for field in ('ohm','farad','mpn','value'):
    if field in part:
     changed=copy.deepcopy(front);changed['parts'][index][field]=part[field]*2 if field in('ohm','farad')else'WRONG_DEVICE';mutations.append((f"{part['ref']} {field}",changed))
   if 'mounting'in part:
    for field in ('side','footprint','series'):
     if field in part['mounting']:
      changed=copy.deepcopy(front);changed['parts'][index]['mounting'][field]='WRONG_MOUNT';mutations.append((f"{part['ref']} mounting {field}",changed))
  changed=copy.deepcopy(front);changed['parts'].append(copy.deepcopy(changed['parts'][0]));mutations.append(('duplicate reference',changed))
  changed=copy.deepcopy(front);changed['parts'].append(dict(ref='C999',farad=1e-6,pins={'1':'+5V','2':'GND'}));mutations.append(('unknown reference',changed))
  changed=copy.deepcopy(front);changed['parts']=[row for row in changed['parts']if row['ref']!='C164'];mutations.append(('missing bypass',changed))
  changed=copy.deepcopy(front);changed['parent_revision']['source_sha256']='0'*64;mutations.append(('wrong parent',changed))
  changed=copy.deepcopy(front);changed['contract']='UNSUPPORTED';mutations.append(('unknown contract',changed))
  changed=copy.deepcopy(front);changed['parts'][0]['farad']=1e-6;mutations.append(('unexpected modeled capacitor field',changed))
  with tempfile.TemporaryDirectory()as directory:
   task_root=Path(directory)
   for relative in [circuit.FRONTEND,Path('hardware/a5-idle-interface/net_contract.json')]:
    target=task_root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((root/relative).read_bytes())
   path=task_root/profile
   try:
    circuit.ROOT=task_root
    path.write_text(json.dumps(front));circuit.binding(profile)
    for name,changed in mutations:
     path.write_text(json.dumps(changed))
     with self.subTest(mutation=name),self.assertRaises(AssertionError):circuit.binding(profile)
    path.write_text(json.dumps(front).replace('"contract":','"contract":"DUPLICATE", "contract":',1))
    with self.assertRaises(AssertionError):circuit.binding(profile)
   finally:circuit.ROOT=root

if __name__=='__main__':unittest.main()
