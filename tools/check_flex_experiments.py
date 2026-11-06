#!/usr/bin/env python3
"""Replay source-bound raw flex experiments, causal controls and corruptions."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import run_flex_scenarios as runner


def read(path):
    return gzip.decompress(path.read_bytes()).decode()


def verify(matrix,live=False):
    matrix=Path(matrix);summary=json.loads((matrix/"summary.json").read_text());cases={case["name"]:case for case in runner.cases()}
    if not summary["passed"]or summary["physical_qualification"]or summary["full_flex_integration"]:raise ValueError("Wrong acceptance scope")
    if {row["name"]for row in summary["results"]}!=set(cases):raise ValueError("Missing or additional declared cases")
    if live:
        for name,digest in summary["sources"].items():
            if hashlib.sha256((runner.ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError("Live source changed: "+name)
    captures={};checks=[]
    for row in summary["results"]:
        name=row["name"];case=cases[name];body,events=runner.stimulus(case);saved=read(matrix/(name+".input.gz"));stdout=read(matrix/(name+".stdout.gz"))
        if body!=saved or hashlib.sha256(saved.encode()).hexdigest()!=row["input_sha256"]or hashlib.sha256(stdout.encode()).hexdigest()!=row["stdout_sha256"]:raise ValueError("Capture/stimulus binding: "+name)
        rows=[json.loads(line)for line in stdout.splitlines()if line.strip()];audit=runner.audit(case,rows,events)
        if not audit["passed"]or any(audit[key]!=row[key]for key in audit):raise ValueError("Audit replay differs: "+name)
        captures[name]=(case,rows,events);checks.append(dict(name=name,passed=True,snapshots=audit["snapshots"]))
    def snapshots(name):return {row["time_us"]:row for row in captures[name][1]if row["kind"]=="snapshot"}
    # Same raw stimulus and binary, only curve choices change. Acquisition must
    # be identical; factors follow the independently declared curves.
    neutral=snapshots("e50-neutral")[3200000];ramp=snapshots("e50-ramp")[3200000]
    acquisition=("source","valid","sample_us","frequency_hz","low_pulse_us","ethanol_pct","fuel_temp_c","raw_edges")
    if any(neutral["own"][key]!=ramp["own"][key]for key in acquisition):raise ValueError("Curve configuration changed own acquisition")
    if not(neutral["own"]["fuel_pct"]==100 and ramp["own"]["fuel_pct"]==125 and neutral["own"]["spark_add_deg"]==0 and ramp["own"]["spark_add_deg"]==5):raise ValueError("Own causal correction response")
    if not(neutral["reference"]["ethanol_pct"]==ramp["reference"]["ethanol_pct"]==50 and neutral["reference"]["fuel_pct"]==100 and ramp["reference"]["fuel_pct"]==125 and ramp["reference"]["pulse_us"]>neutral["reference"]["pulse_us"]):raise ValueError("Genuine production causal correction response")
    checks.append(dict(name="neutral_vs_ramp_causal_control",passed=True))
    # Main-loop refinement and sub-us-grid phase are acquisition controls, not
    # claims about matching scheduler pulses or physical interrupt latency.
    normal=snapshots("e50-ramp");fine=snapshots("e50-loop-refinement");phase=snapshots("e50-phase1us")
    for time in(1200000,2200000,3200000):
        for key in acquisition:
            if normal[time]["own"][key]!=fine[time]["own"][key]:raise ValueError("Own acquisition depends on query cadence")
        for key in("ethanol_pct","fuel_temp_c","counter","low_pulse_us"):
            if normal[time]["reference"][key]!=fine[time]["reference"][key]:raise ValueError("Production acquisition depends on query cadence")
        for controller in("own","reference"):
            for key in("ethanol_pct","fuel_temp_c"):
                if normal[time][controller][key]!=phase[time][controller][key]:raise ValueError("Static acquisition changes with1us phase")
    checks.append(dict(name="query_refinement_and_phase_control",passed=True))
    rejected=[]
    def mutation(name,case_name,edit):
        case,rows,events=captures[case_name];rows=copy.deepcopy(rows);edit(rows)
        result=runner.audit(case,rows,events)
        if result["passed"]:raise ValueError("Corruption accepted: "+name)
        rejected.append(dict(name=name,rejected=True,failures=result["failures"]))
    def tail(rows):return next(row for row in reversed(rows)if row["kind"]=="snapshot")
    mutation("wrong_ethanol","e50-ramp",lambda rows:tail(rows)["own"].update(ethanol_pct=60))
    mutation("forged_target_source","e50-ramp",lambda rows:tail(rows)["own"].update(source="target_capture"))
    mutation("future_sample","e50-ramp",lambda rows:tail(rows)["own"].update(sample_us=3200001))
    mutation("wrong_own_edge_count","e50-ramp",lambda rows:tail(rows)["own"].update(raw_edges=0))
    mutation("wrong_reference_counter","e50-ramp",lambda rows:tail(rows)["reference"].update(counter=255))
    mutation("missing_snapshot","e50-ramp",lambda rows:rows.pop(-1))
    mutation("wrong_callback","e50-ramp",lambda rows:rows[0].update(callback_is_flexPulse=False))
    mutation("wrong_temperature_factor","e50-ramp",lambda rows:tail(rows)["own"].update(temperature_pct=150))
    mutation("lost_neutrality","e50-neutral",lambda rows:tail(rows)["own"].update(fuel_pct=99))
    def hide_fault(rows):next(row for row in rows if row.get("time_us")==1200000 and row["kind"]=="snapshot")["own"].update(pending_fault=False)
    mutation("hidden_recovered_fault","hidden-width-fault-and-ack",hide_fault)
    def hide_startup(rows):
        for row in rows:
            if row["kind"]=="snapshot"and 160000<=row["time_us"]<1000000:row["reference"].update(fuel_pct=100,spark_add_deg=0)
    mutation("erased_startup_evidence","e0-neutral-startup",hide_startup)
    return dict(passed=True,scope="saved_raw_edge_flex_audits_and_controls",cases=len(cases),checks=checks,mutations=rejected,physical_qualification=False,full_flex_integration=False)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("matrix",type=Path);parser.add_argument("output",type=Path);parser.add_argument("--check-live-sources",action="store_true");args=parser.parse_args()
    if args.output.exists():raise ValueError("Preserve previous audit output")
    result=verify(args.matrix,args.check_live_sources);args.output.write_text(json.dumps(result,indent=2)+"\n")
    print("Verified",result["cases"],"raw-edge cases, causal/refinement controls and",len(result["mutations"]),"rejected corruptions")
