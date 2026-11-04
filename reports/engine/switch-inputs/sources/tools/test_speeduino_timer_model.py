#!/usr/bin/env python3
"""Reproduce native16 timer-HAL sanitizer checks using its recorded build flags."""
import argparse,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def run(output):
 manifest=R/'.cache/engine/speeduino-sim16/build-manifest.json'
 if not manifest.exists():raise SystemExit('Build the16bit reference first: python3 scripts/build_speeduino_sim.py --timer-bits 16')
 m=json.loads(manifest.read_text());assert m['timer_counter_bits']==16
 output.mkdir(parents=True,exist_ok=True);binary=output/'timer-model-test';sources=[R/'tools/speeduino_sim_hal.cpp',R/'tools/speeduino_timer_model_test.cpp']
 cmd=['g++',*m['compile_flags'],'-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',*map(str,sources),'-o',str(binary)];subprocess.run(cmd,check=True);result=subprocess.run([str(binary)],check=True,text=True,capture_output=True)
 report=dict(passed=True,scope='16bit/4us/equality native timer HAL only; not CPU/register/IRQ emulation',checks=['wrap','compare behind count','zero-tick delay','disabled count and re-enable'],stdout=result.stdout,source_hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},reference_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
 (output/'timer-model.json').write_text(json.dumps(report,indent=2)+'\n');print(result.stdout.strip());return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=R/'.cache/engine/timer-model-check');a=p.parse_args();run(a.output_dir)
