import hashlib,json,os,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path.cwd();SOURCE=ROOT/'reports/engine/flex-radio';OUT=ROOT/'.cache/engine'/('flex-radio-negative-'+uuid.uuid4().hex);OUT.mkdir()
def patch(path,change):
 x=json.loads(path.read_text());change(x);path.unlink();path.write_text(json.dumps(x,indent=2)+'\n')
def manifest(directory):
 p=directory/'artifact-manifest.json';p.unlink();rows=[dict(path=str(x.relative_to(directory)),bytes=x.stat().st_size,sha256=hashlib.sha256(x.read_bytes()).hexdigest())for x in sorted(directory.rglob('*'))if x.is_file()];p.write_text(json.dumps(dict(artifacts=rows),indent=2)+'\n')
cases=[
 ('partial-engine-ack','native/partial.json',lambda x:x['peers'][0].update(engine_connected=True),'Partial ACK labeling differs'),
 ('wrong-wire-budget','sources/config/engine-radio-v5.json',lambda x:x.update(max_datagram_bytes=251),'Source snapshot differs'),
 ('review-rejected','reviews/independent/review.json',lambda x:x.update(accepted=False),'Independent acceptance missing'),
 ('build-sources-changed','build/summary.json',lambda x:x.update(source_inputs_unchanged=False),'Build attestation failed'),
 ('raw-flex-stale-hidden','validation/sender-receiver.json',lambda x:x['status_at_380_ms'].update(flex_value_qualified=True),'Independent raw expiry differs'),
 ('full-parity-overclaim','summary.json',lambda x:x.update(full_speeduino_parity=True),'Overstated qualification'),
 ('legacy-byte-claim','reviews/independent/legacy-comparison-001.json',lambda x:x.update(capture_sha256='0'*64),'Reviewer evidence differs'),
]
results=[]
for name,relative,change,expected in cases:
 target=OUT/name;shutil.copytree(SOURCE,target,copy_function=os.link)
 patch(target/relative,change);manifest(target)
 command=[sys.executable,'-B',str(ROOT/'tools/verify_flex_radio_evidence.py'),'--report',str(target)]
 p=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(OUT/(name+'.log')).write_text(p.stdout)
 results.append(dict(name=name,returncode=p.returncode,expected=expected,rejected=p.returncode!=0 and expected in p.stdout,command=command))
report=dict(passed=all(x['rejected']for x in results),scope='Owned hardlink copies with copy-before-write JSON mutation and recomputed artifact manifests; original report byte checks remain separate',original_artifact_manifest_sha256=hashlib.sha256((SOURCE/'artifact-manifest.json').read_bytes()).hexdigest(),output=str(OUT),cases=results)
(OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));sys.exit(0 if report['passed']else 1)
