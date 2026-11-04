#!/usr/bin/env python3
"""Verify published idle hardware evidence bytes, optionally live/index bindings.

This checks evidence integrity, not electrical, engine or manufacturing safety.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-live-sources',action='store_true')
    p.add_argument('--check-index',action='store_true')
    a=p.parse_args();out=ROOT/'reports/engine/idle-isolation'
    manifest=json.loads((out/'artifact-manifest.json').read_text())
    files={str((out/k).relative_to(ROOT)):v for k,v in manifest['files_sha256'].items()}
    assert all(sha((ROOT/k).read_bytes())==v for k,v in files.items()),'Published artifact bytes differ'
    source=json.loads((out/'validation-summary.json').read_text())['source_sha256']
    if a.check_live_sources:
        assert all(sha((ROOT/k).read_bytes())==v for k,v in source.items()),'Live source differs from this evidence'
    if a.check_index:
        expected=dict(files)
        expected[str((out/'artifact-manifest.json').relative_to(ROOT))]=sha((out/'artifact-manifest.json').read_bytes())
        if a.check_live_sources:expected.update(source)
        for name,digest in expected.items():
            data=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
            assert sha(data)==digest,'Git index bytes differ: '+name
    result=json.loads((out/'circuit/results.json').read_text())
    assert result['source_unchanged_during_run'] and result['validation']['passed']
    for name in ('accessory','carrier'):
        erc=json.loads((out/f'cad/{name}-erc.json').read_text())
        drc=json.loads((out/f'cad/{name}-drc.json').read_text())
        assert not any(s['violations'] for s in erc['sheets'])
        assert all(not drc[k] for k in ('violations','unconnected_items','schematic_parity'))
    print(json.dumps(dict(passed=True,artifacts=len(files),live_sources_checked=len(source) if a.check_live_sources else 0,
        index_bytes_checked=a.check_index,physical_qualification=False),indent=2))


if __name__=='__main__':main()
