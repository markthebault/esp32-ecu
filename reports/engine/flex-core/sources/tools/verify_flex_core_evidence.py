#!/usr/bin/env python3
"""Verify archived flex groundwork; replay saved audits and sanitizer probes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"reports/engine/flex-core"


def sha(body):return hashlib.sha256(body).hexdigest()
def document(path):return json.loads(path.read_text())
def require(value,message):
    if not value:raise ValueError(message)
def safe(name):
    path=Path(name);require(not path.is_absolute()and".."not in path.parts,"Unsafe artifact path: "+name);return path


def verify(report=REPORT,live=False,replay=False):
    report=report.resolve();manifest=document(report/"artifact-manifest.json");entries=manifest["artifacts"]
    names={row["path"]for row in entries};require(len(names)==len(entries),"Duplicate artifact")
    actual={str(p.relative_to(report))for p in report.rglob("*")if p.is_file()and p!=report/"artifact-manifest.json"}
    require(names==actual,"Artifact set differs")
    for row in entries:
        path=report/safe(row["path"]);require(not path.is_symlink(),"Symlink artifact")
        body=path.read_bytes();require(len(body)==row["bytes"]and sha(body)==row["sha256"],"Changed artifact: "+row["path"])
    summary=document(report/"summary.json")
    require(summary["scope"]=="flex_raw_edge_groundwork"and summary["checks_passed"],"Packet scope/checks")
    require(not any(summary[name]for name in("full_flex_integration","target_capture_implemented","physical_qualification","online_tuner_accepted","full_speeduino_parity")),"Overstated feature acceptance")
    for name,row in summary["sources"].items():
        body=(report/safe(row["snapshot"])).read_bytes();require(sha(body)==row["sha256"],"Source snapshot differs: "+name)
        if live:require((ROOT/safe(name)).read_bytes()==body,"Live source changed: "+name)
    for name,row in summary["upstream"].items():require(sha((report/safe(row["snapshot"])).read_bytes())==row["sha256"],"Upstream source snapshot: "+name)
    matrix=document(report/"matrix/summary.json");require(matrix["passed"]and matrix["sources_stable"]and matrix["original_inputs_stable"],"Matrix acceptance")
    require(len(matrix["results"])==25 and not matrix["physical_qualification"]and not matrix["full_flex_integration"],"Matrix scope/count")
    for name,digest in matrix["sources"].items():require(summary["sources"][name]["sha256"]==digest,"Execution source binding: "+name)
    native=document(report/"matrix/native-build-manifest.json")
    require(native["speeduino_sha"]=="9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20"and not native["unit_test"],"Production reference pin")
    require(native["base_binary_sha256"]==native["numerical_relink_sha256"]=="046389d754c996c34cb7e7171b1e42088f5ae6c0615133a3c5e74743f9f6d52c","Exact numerical baseline relink")
    require(len(native["locked_original_input_hashes"])==565 and native["original_objects_reused"]==108,"Original build input set")
    for name,digest in native["fixture_sources"].items():require(summary["sources"][name]["sha256"]==digest,"Native source binding: "+name)
    controls=document(report/"checks.json");require(controls["passed"]and controls["cases"]==25 and len(controls["mutations"])==11 and all(row["rejected"]for row in controls["mutations"]),"Causal/negative controls")
    review=document(report/"reviews/independent-review.json");require(review["accepted"]and not review["open_findings"],"Independent review acceptance")
    require(set(matrix["sources"]).issubset(review["source_hashes"]),"Execution files omitted from independent review")
    for name,digest in review["source_hashes"].items():require(summary["sources"][name]["sha256"]==digest,"Independent review source: "+name)
    side_effect=document(report/"reviews/coverage-side-effect.json")
    require(len(side_effect["generated_files_touched"])==16 and not side_effect["tracked_source_changed"]and not side_effect["numerical_fixtures_changed"],"Coverage side-effect disclosure")
    require("flex_fuel_checks 509"in(report/"validation/firmware-tests-gcc.log").read_text(),"Full native harness result")
    if replay:
        previous_bytecode=sys.dont_write_bytecode;previous_modules={name:sys.modules.get(name)for name in("run_flex_scenarios","frozen_flex_checks")}
        try:
            sys.dont_write_bytecode=True;modules={}
            for name,file in(("run_flex_scenarios","run_flex_scenarios.py"),("frozen_flex_checks","check_flex_experiments.py")):
                spec=importlib.util.spec_from_file_location(name,report/"sources/tools"/file);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);modules[name]=module
            require(modules["frozen_flex_checks"].verify(report/"matrix")==controls,"Saved matrix/control replay differs")
        finally:
            sys.dont_write_bytecode=previous_bytecode
            for name,module in previous_modules.items():
                if module is None:sys.modules.pop(name,None)
                else:sys.modules[name]=module
        with tempfile.TemporaryDirectory(prefix="ecu-flex-groundwork-")as temporary:
            work=Path(temporary);environment={**os.environ,"ASAN_OPTIONS":"detect_leaks=1:abort_on_error=1","UBSAN_OPTIONS":"halt_on_error=1","GCOV_PREFIX":str(work/"gcov"),"GCOV_PREFIX_STRIP":"0"}
            for name,source,expected in(
                ("parent",report/"sources/firmware/tests/flex_fuel_test.cpp","flex_fuel_checks 509"),
                ("independent",report/"reviews/core-independent-001.cpp","independent_core_checks 2101"),
                ("boundaries",report/"reviews/core-boundary-002.cpp","independent_boundary_checks 21382")):
                binary=work/name
                subprocess.run(["g++","-std=c++14","-O1","-g","-Wall","-Wextra","-Werror","-pedantic","-fsanitize=address,undefined","-fno-omit-frame-pointer","-I"+str(report/"sources/firmware/include"),str(source),"-o",str(binary)],check=True)
                result=subprocess.run([str(binary)],capture_output=True,text=True,env=environment)
                require(result.returncode==0 and result.stdout.strip()==expected and not result.stderr,"Sanitizer replay: "+name+" "+result.stderr)
        print("Replayed25 saved cases, causal/refinement controls,11 corruptions and509+2101+21382 sanitizer assertions")
    print("Verified",len(entries),"artifacts and",len(summary["sources"]),"source snapshots; target/UI/config/PCB/plant and physical/full parity remain open")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--report",type=Path,default=REPORT);parser.add_argument("--check-live-sources",action="store_true");parser.add_argument("--replay",action="store_true");args=parser.parse_args();verify(args.report,args.check_live_sources,args.replay)
