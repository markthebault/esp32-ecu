from pathlib import Path
import hashlib,json,sys
own=Path(__file__).resolve().parent;repo=own.parents[2];dst=own/(sys.argv[1]if len(sys.argv)>1 else'freeze-final-001')
assert repo.name=='esp32-ecu' and not dst.exists(),(repo,dst)
paths=sorted(set([str(p.relative_to(repo))for p in(repo/'firmware/include/ecu').glob('*.hpp')]+[
'firmware/main/espnow.cpp','firmware/main/config_json.hpp','firmware/tests/engine_radio_flex_test.cpp','firmware/tests/espnow_test.cpp',
'config/engine-radio-v5.json','tools/engine_receiver.py','tools/flex_radio.py','tools/flex_config.py','tools/espnow_protocol.py','tools/engine_observability.py','tools/engine_observability_bridge.cpp','tools/radio_simulator.py']+[p for p in sys.argv[2:]if(repo/p).is_file()]))
manifest={}
for rel in paths:
 src=repo/rel;body=src.read_bytes();digest=hashlib.sha256(body).hexdigest();target=dst/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body);manifest[rel]=digest
assert all(hashlib.sha256((repo/p).read_bytes()).hexdigest()==v and hashlib.sha256((dst/p).read_bytes()).hexdigest()==v for p,v in manifest.items())
(dst/'manifest.json').write_text(json.dumps({'source_root':str(repo),'source_hashes':manifest,'source_before_after_equal':True,'snapshot_equal':True},indent=2)+'\n');print(json.dumps({'freeze':dst.name,'inputs':len(manifest),'manifest_sha256':hashlib.sha256((dst/'manifest.json').read_bytes()).hexdigest()}))
