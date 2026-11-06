#!/usr/bin/env python3
"""Exercise frozen builder with owned object links and an owned mutation only."""
from pathlib import Path
import fcntl,hashlib,json,shutil,subprocess,time
BASE=Path(__file__).resolve().parent
PROJECT=BASE.parents[3]
FROZEN=BASE/'fixture-root';OWN=BASE/'build-validation-root'
for name in ['scripts/build_speeduino_serial.py','tools/speeduino_serial_sim.cpp','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp']:
    dest=OWN/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(FROZEN/name,dest)
original=PROJECT/'.cache/engine/speeduino-sim';base=OWN/'.cache/engine/speeduino-sim';base.mkdir(parents=True,exist_ok=True)
for name in ['build-manifest.json','speeduino-sim']:shutil.copy2(original/name,base/name)
m=json.loads((base/'build-manifest.json').read_text())
copy_name='source-'+m['archive_sha256'][:16]+'-idle-aux-v1'
(base/copy_name).symlink_to(original/copy_name,target_is_directory=True)
obj=base/'obj';obj.mkdir()
for path in (original/'obj').glob('*.o'):(obj/path.name).symlink_to(path)
command=['python3',str(OWN/'scripts/build_speeduino_serial.py'),'--source',str(PROJECT.parent/'speeduino')]
serial=OWN/'.cache/engine/speeduino-serial-sim';serial.mkdir(parents=True,exist_ok=True)
stdout=(BASE/'builder-positive.stdout').open('w');stderr=(BASE/'builder-positive.stderr').open('w')
with (base/'build.lock').open('a+b')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    process=subprocess.Popen(command,stdout=stdout,stderr=stderr)
    time.sleep(.2)
    lock_blocks=process.poll()is None and not(serial/'numerical-reference-relink').exists()
    fcntl.flock(lock,fcntl.LOCK_UN)
assert lock_blocks
status=process.wait(timeout=60);stdout.close();stderr.close();assert status==0,(BASE/'builder-positive.stderr').read_text()
result_manifest=json.loads((serial/'build-manifest.json').read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
attested=result_manifest['numerical_relink_sha256']==m['binary_sha256']==sha(serial/'numerical-reference-relink')
assert attested
protected_inputs=result_manifest['locked_original_input_hashes']
assert all(sha(Path(path))==digest for path,digest in protected_inputs.items())
# Alter only an owned copy of comms.o's unique protocol-version string. The
# external checkout and original benchmark object are never opened for writes.
name='speeduino_comms.cpp.o';changed=obj/name;object_bytes=changed.read_bytes();assert object_bytes.count(b'\x00002')==1
changed.unlink();changed.write_bytes(object_bytes.replace(b'\x00002',b'\x00003'))
negative=subprocess.run(command,capture_output=True,text=True,timeout=60)
(BASE/'builder-negative.stdout').write_text(negative.stdout);(BASE/'builder-negative.stderr').write_text(negative.stderr)
assert negative.returncode!=0 and 'Cached objects do not reproduce the attested numerical reference binary'in negative.stderr
assert sha(original/'obj'/name)==hashlib.sha256(object_bytes).hexdigest()
result=dict(base_shared_lock_wait_verified=lock_blocks,positive_build_exit=status,exact_numerical_relink_verified=attested,locked_input_hashes_validated=len(protected_inputs),serial_source_hashes=result_manifest['fixture_sources'],owned_modified_object=name,negative_build_exit=negative.returncode,negative_detected_changed_object=True,original_object_unchanged=True,owned_rebuild_binary_sha256=result_manifest['binary_sha256'],note='Rebuild has relocated fixture-source filenames and is separate from exact root-binary lifecycle probes.')
(BASE/'build-provenance-probes.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
