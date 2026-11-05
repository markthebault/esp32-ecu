"""Build a fresh boost-control entry point from unchanged, attested production objects."""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
from build_speeduino_flex import ROOT, PIN, BASE_SHA, digest


def build(output,source=None):
    source=Path(source or ROOT.parent/'speeduino').resolve();output=output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    base=ROOT/'.cache/engine/speeduino-sim'
    with (base/'build.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_SH)
        manifest=base/'build-manifest.json';m=json.loads(manifest.read_text())
        if m['unit_test'] or m['speeduino_sha']!=PIN or m['timer_counter_bits']!=32 or m['binary_sha256']!=BASE_SHA or digest(base/'speeduino-sim')!=BASE_SHA:
            raise RuntimeError('Production reference attestation failed')
        if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=PIN:raise RuntimeError('Reference pin changed')
        subprocess.run(['git','-C',str(source),'diff','--exit-code','HEAD','--','speeduino','lib'],check=True)
        copied=base/('source-'+m['archive_sha256'][:16]+'-idle-aux-v1');inputs={}
        for name,expected in m['source_hashes'].items():
            p=ROOT/name if name.startswith('tools/') else copied/name
            if digest(p)!=expected:raise RuntimeError('Changed numerical source: '+name)
            inputs[str(p)]=expected
        for key,directory in (('header_hashes',copied),('dependency_hashes',source)):
            for name,expected in m[key].items():
                p=directory/name
                if digest(p)!=expected:raise RuntimeError('Changed numerical input: '+name)
                inputs[str(p)]=expected
        original=[base/'obj'/(name.replace('/','_')+'.o') for name in m['source_hashes'] if name!='tools/speeduino_sim_native.hpp']
        libraries=[source/name for name in m['dependency_hashes'] if name.endswith('.a')]
        if len(original)!=109:raise RuntimeError('Original translation-unit set changed')
        for p in original+libraries+[manifest,base/'speeduino-sim']:inputs[str(p)]=digest(p)
        commands=[]
        def command(args):
            commands.append(args)
            with (output/f'command-{len(commands)}.log').open('xb') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
        tail=['-Wl,--start-group',*map(str,libraries),'-Wl,--end-group','-lgcov','-pthread']
        relink=output/'numerical-reference-relink';command([m['compiler'],*map(str,original),*tail,'-o',str(relink)])
        if digest(relink)!=BASE_SHA:raise RuntimeError('Original object relink differs')
        names=['tools/speeduino_boost_sim.cpp','scripts/build_speeduino_boost.py','scripts/build_speeduino_flex.py']
        own={name:digest(ROOT/name) for name in names}
        for name in names:
            p=output/'sources'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
        entry=output/'entry.o';command([m['compiler'],*m['compile_flags'],'-x','c++','-c',str(ROOT/'tools/speeduino_boost_sim.cpp'),'-o',str(entry)])
        objects=[p for p in original if p.name!='tools_speeduino_sim.cpp.o']+[entry]
        binary=output/'speeduino-boost-sim';command([m['compiler'],*map(str,objects),*tail,'-o',str(binary)])
        if any(digest(Path(name))!=expected for name,expected in inputs.items()) or any(digest(ROOT/name)!=expected for name,expected in own.items()):raise RuntimeError('Source changed during build')
        result=dict(scope='production_loop_raw_adc_crank_boost_and_pwm',speeduino_sha=PIN,unit_test=False,
            binary_sha256=digest(binary),base_manifest_sha256=digest(manifest),numerical_relink_sha256=digest(relink),
            locked_original_input_hashes=inputs,fixture_sources=own,original_objects_reused=108,commands=commands,
            limits=['Native HAL, not AVR/ESP32 execution or ADC hardware simulation','Raw analogRead counts and actual primary trigger callbacks; no MAP/RPM/sync status injection','Authored boost tune and native timer HAL; no physical solenoid or turbo model','No physical engine or electrical qualification'])
        (output/'build-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
        return binary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path)
    args=p.parse_args();print(build(args.output,args.source))
