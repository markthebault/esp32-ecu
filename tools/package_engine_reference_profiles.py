"""Package reviewed expanded-reference sources/evidence without overwriting history."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache/engine'
BASELINE='c0d7d0fe1c96a9f783bc89591d8be1b09195f612'
SAFE={'.json','.log','.py','.cpp','.h','.hpp','.txt','.md','.gz','.stderr'}
SOURCES=('scripts/build_speeduino_profiles.py','tools/speeduino_profiles_sim.cpp',
    'tools/speeduino_profiles_runtime.py','tools/test_speeduino_profiles.py',
    'tools/test_engine_profile_comparison.py','tools/test_engine_profile_compatibility.py',
    'tools/compare_engine_controllers.py','tools/package_engine_reference_profiles.py',
    'docs/engine-reference-profiles.md','docs/engine-cylinder-profiles.md','docs/engine-feature-coverage.md')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())


def main(output):
    output=output.resolve()
    if output.exists():raise RuntimeError('Choose a new packet directory')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if head!=BASELINE:raise RuntimeError('This historical packet is an overlay on its declared baseline')
    groups={name:{}for name in ('sources','validation','plants')}
    def add(group,path,name):
        path=Path(path);name=str(name)
        assert path.is_file()and not path.is_symlink(),path
        assert not Path(name).is_absolute()and'..'not in Path(name).parts and name not in groups[group]
        groups[group][name]=path
    def tree(group,base,prefix):
        for path in sorted(base.rglob('*')):
            if path.is_file()and not path.is_symlink()and path.suffix in SAFE:
                add(group,path,Path(prefix)/path.relative_to(base))
    identities={name:dict(bytes=(ROOT/name).stat().st_size,sha256=sha(ROOT/name))for name in SOURCES}
    for name in SOURCES:add('sources',ROOT/name,name)
    matrix=CACHE/'expanded-reference-coupled-002';m=read(matrix/'summary.json')
    assert m['passed']and m['source_unchanged']and m['tests']==5 and len(m['cases'])==68
    counts={category:sum(item['category']==category for item in m['cases'].values())
            for category in set(item['category']for item in m['cases'].values())}
    assert counts==dict(normal_profile=44,unsupported_reference_geometry_diagnostic=4,
        fault_comparison=6,fixed_geometry_causal_control=2,numerical_refinement=12),counts
    for name,expected in m['source_sha256'].items():assert sha(ROOT/name)==expected,name
    tree('plants',matrix,'coupled');add('plants',matrix.with_suffix('.log'),'coupled-run.log')
    compatibility=CACHE/'expanded-reference-compatibility-001';c=read(compatibility/'summary.json')
    assert c['passed']and c['source_unchanged']and len(c['cases'])==12
    assert c['current_source_sha256']==sha(ROOT/'tools/compare_engine_controllers.py')
    assert c['probe_sha256']==sha(ROOT/'tools/test_engine_profile_compatibility.py')
    tree('validation',compatibility,'four-cylinder-exact-regression')
    add('validation',compatibility.with_suffix('.log'),'four-cylinder-exact-regression.log')
    acceptance=CACHE/'expanded-reference-acceptance-003';a=read(acceptance/'summary.json')
    assert a['passed']and a['tests']==4 and len(a['cases'])==24
    for name,expected in a['source_sha256'].items():assert sha(ROOT/name)==expected,name
    tree('validation',acceptance,'prescribed-shaft')
    add('validation',acceptance.with_suffix('.log'),'prescribed-shaft.log')
    build=CACHE/'expanded-reference-build-002';b=read(build/'build-manifest.json')
    assert a['binary_sha256']==b['binary_sha256']==sha(build/'speeduino-profiles')
    for name,expected in b['fixture_sources'].items():assert sha(ROOT/name)==expected,name
    tree('validation',build/'sources','fixture-build/sources')
    for name in ('build-manifest.json','command-1.log','command-2.log','command-3.log'):
        add('validation',build/name,'fixture-build/'+name)
    review=CACHE/'expanded-reference-review-001';assessment=read(review/'assessment.json')
    assert assessment['passed']and assessment['open_findings']==[]
    for name,expected in assessment['reviewed_sources'].items():assert sha(ROOT/name)==expected,name
    assert assessment['reference_binary_sha256']==b['binary_sha256']
    assert assessment['reference_manifest_sha256']==sha(build/'build-manifest.json')
    whitelist=read(review/'whitelist.json')
    assert whitelist['assessment_sha256']==sha(review/'assessment.json')
    for item in whitelist['files']:
        path=review/item['relative_path']
        assert path.resolve().is_relative_to(review.resolve())and not path.is_symlink()
        assert path.stat().st_size==item['size_bytes']and sha(path)==item['sha256']
        if path.suffix in SAFE:add('validation',path,Path('independent-review')/item['relative_path'])
    add('validation',review/'whitelist.json','independent-review/whitelist.json')
    # Preserve the failed configuration and failed generic timing gate. Their
    # artifacts remain historical and are never counted as passing evidence.
    oldbuild=CACHE/'expanded-reference-build-001'
    tree('plants',oldbuild/'sources','historical-fixture-001/sources')
    add('plants',oldbuild/'build-manifest.json','historical-fixture-001/build-manifest.json')
    first=CACHE/'expanded-reference-coupled-probe-001'
    for name in ('1-batch_wasted-speeduino.json.gz','1-batch_wasted-ours.json.gz'):
        add('plants',first/name,'historical-fixture-001/'+name)
    failed=CACHE/'expanded-reference-coupled-001';f=read(failed/'summary.json')
    assert not f['passed']and f['failures']==2 and f['errors']==0
    historical=failed/'sources/tools/test_engine_profile_comparison.py'
    assert sha(historical)==f['source_sha256']['tools/test_engine_profile_comparison.py']
    add('plants',historical,'historical-gate-001/test_engine_profile_comparison.py')
    add('plants',failed/'summary.json','historical-gate-001/summary.json')
    add('plants',failed.with_suffix('.log'),'historical-gate-001/run.log')
    manifest=dict(status='reviewed_development_checkpoint_goal_active',baseline_commit=BASELINE,
        goal_complete=False,engine_outputs_inhibited=True,physical_operation_verified=False,
        fitted_injector_commands=4,fitted_coil_commands=4,coupled_cases=counts,
        source_identities=identities,archives={},
        scope='Actual16GPIO pinned production-reference fixture;1..8-cylinder independent research plants, explicit mismatches/faults/causality/refinement; original4-cylinder behavior preserved',
        limits=['Fixed500cc/cylinder60-2/Hall neutral-correction fixture, not all supported Speeduino tunes',
                'Native zero-CPU-time HAL and uncalibrated empirical combustion, no physical timing claim',
                'Reference demand is sampled, not event-latched; variable-RPM prediction differs',
                'No PCB/target/turbo expansion or online tuning qualification in this increment'])
    output.mkdir(parents=True,exist_ok=False)
    for group,files in groups.items():
        payloads={name:dict(bytes=path.stat().st_size,sha256=sha(path))for name,path in sorted(files.items())}
        archive=output/(group+'.zip')
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
            for name,path in sorted(files.items()):z.write(path,name)
        with zipfile.ZipFile(archive)as z:
            assert z.testzip()is None and set(z.namelist())==set(files)
            for name,path in files.items():assert sha(path)==payloads[name]['sha256']==hashlib.sha256(z.read(name)).hexdigest()
        manifest['archives'][group]=dict(file=archive.name,bytes=archive.stat().st_size,sha256=sha(archive),payloads=payloads)
    for name,identity in identities.items():assert sha(ROOT/name)==identity['sha256']
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'README.md').write_text('''# Expanded production-reference comparison packet

This development checkpoint adds a separate sixteen-output genuine Speeduino native fixture and generalized coupled engine comparisons. The full feature goal remains active. Existing PCB capacity is4+4; physical engine outputs remain inhibited.

- `sources.zip`: source overlay on commitc0d7d0f, including tools, reproduction commands and scope documentation.
- `validation.zip`:24 prescribed-shaft profiles, exact original4-cylinder GPIO/status and12 full coupling-result regressions, source/object/library/binary identities, independent raw/negativeIO/coupled/variable-shaft review and closure receipts. Binaries and gcov files are excluded.
- `plants.zip`:68 raw coupled runs:44 normal profiles,4 explicit incompatible reference fallback diagnostics,6 fault cases,2 fixed-geometry causal controls and12 refinements. Historical failedN1 fixture and failed common timing-gate reports are separate records and do not count as passing evidence.

Twenty reference profiles and all24 project profiles power the declared free-shaft engine after starter removal. Two- and seven-cylinder non-sequential reference fallbacks do not represent the selected even-fire COP geometry. Timing differences and reference transient errors remain in raw results; no equivalent accuracy or calibration claim is made.

See `docs/engine-reference-profiles.md` for configuration, actual native pin wiring, effective modes, commands and limits. These are uncalibrated research plants and a native HAL with zeroCPU/IRQ cost. They do not qualify physical target timing, electrical behavior, engine/vehicle operation, EMI/surge, thermal, splash, RF or printed fit. Expanded turbo geometry, matching hardware, online tuning integration and wider control/trigger features remain unfinished.
''')
    print(json.dumps(dict(output=str(output),archives={name:dict(bytes=item['bytes'],files=len(item['payloads']))for name,item in manifest['archives'].items()})))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)
