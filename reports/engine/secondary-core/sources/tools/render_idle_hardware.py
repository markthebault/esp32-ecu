#!/usr/bin/env python3
"""Render nominal assembly drawings from isolated writable KiCad project copies.

These plots are review illustrations, never manufacturing/3D fit acceptance.
KiCad plotting can write project settings, so it never runs on source projects.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import cairosvg

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args()
    out=a.report_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    commands=[];sources={}
    with tempfile.TemporaryDirectory(prefix='ecu-idle-plots-') as temporary:
        for folder,board,names in [
            ('idle-isolated','isolated',[('accessory-top','F.Fab,Edge.Cuts',False),('accessory-back','B.Fab,Edge.Cuts',True)]),
            ('a5-idle-interface','esp32-ecu',[('carrier-top','F.Fab,Edge.Cuts',False)])]:
            source=ROOT/'hardware'/folder;target=Path(temporary)/folder
            shutil.copytree(source,target,ignore=shutil.ignore_patterns('*.kicad_prl','*.lck'))
            for f in source.rglob('*'):
                if f.is_file() and f.suffix not in {'.kicad_prl','.lck'}:sources[str(f.relative_to(ROOT))]=sha(f)
            for name,layers,mirror in names:
                svg=out/(name+'.svg')
                cmd=['kicad-cli','pcb','export','svg','--mode-single','--layers',layers,
                     '--sketch-pads-on-fab-layers','--page-size-mode','2','--exclude-drawing-sheet',
                     '--output',str(svg)]
                if mirror:cmd.append('--mirror')
                cmd.append(str(target/(board+'.kicad_pcb')))
                r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                commands.append(dict(command=cmd,returncode=r.returncode,output=r.stdout))
                assert r.returncode==0 and 'Error:' not in r.stdout,r.stdout
                cairosvg.svg2png(url=str(svg),write_to=str(svg.with_suffix('.png')),output_width=1600,background_color='white')
    assert all(sha(ROOT/f)==h for f,h in sources.items()),'Source project changed during render'
    (out/'render-manifest.json').write_text(json.dumps(dict(scope=__doc__,source_sha256=sources,
        kicad_version=subprocess.check_output(['kicad-cli','version'],text=True).strip(),
        cairosvg_version=cairosvg.__version__,commands=commands,source_bytes_unchanged=True),indent=2)+'\n')


if __name__=='__main__':main()
