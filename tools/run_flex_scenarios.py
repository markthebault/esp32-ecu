#!/usr/bin/env python3
"""Raw-edge acquisition/correction experiments, not a complete flex ECU test.

No plant, target input, engine Tune/UI/config integration or physical output is
qualified here. Production status is observed, never assigned by this driver.
"""
import argparse
from fractions import Fraction
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/engine/speeduino-flex-sim"
SOURCES = ["firmware/include/ecu/flex_fuel.hpp", "firmware/tests/flex_fuel_test.cpp",
           "scripts/build_speeduino_flex.py", "tools/speeduino_flex_sim.cpp", "tools/run_flex_scenarios.py", "tools/check_flex_experiments.py"]


def digest(body):
    return hashlib.sha256(body).hexdigest()


def cases():
    rows = []
    for name, hz, low, expectation in [
        ("e0-neutral-startup", 50, 3000, "startup"),
        ("e50-ramp", 100, 3000, "nominal"),
        ("e50-neutral", 100, 3000, "nominal"),
        ("e50-cold-ramp", 100, 1000, "nominal"),
        ("e50-hot-ramp", 100, 5000, "nominal"),
        ("e85-ramp", 135, 3000, "nominal"),
        ("e100-neutral", 150, 3000, "nominal"),
        ("e1-reference-deadband", 51, 3000, "deadband"),
        ("low-frequency48", 48, 3000, "frequency"),
        ("high-frequency160", 160, 3000, "frequency"),
        ("sensor-fault170", 170, 1000, "sensor_fault"),
        ("counter-wrap356", 356, 1000, "counter_wrap"),
        ("short-low-pulse", 100, 500, "pulse_width"),
        ("long-low-pulse", 100, 5500, "pulse_width"),
        ("lower-tolerance49", 49, 3000, "tolerance"),
        ("upper-tolerance151", 151, 3000, "tolerance"),
    ]:
        rows.append(dict(name=name, segments=[[0, 3200001, hz, low]], samples=[0, 100000, 160000, 500000, 999999, 1000000, 1200000, 2200000, 3200000],
                         expectation=expectation, ramp="ramp" in name, low_hz=50, high_hz=150, reference_filter=0, enabled=True))
    def add(name, expectation, **values):
        row=dict(next(row for row in rows if row["name"]=="e50-ramp"));row.update(name=name, expectation=expectation);row.update(values);rows.append(row)
    add("custom40-160-span", "custom_span", low_hz=40, high_hz=160)
    add("reference-filter75", "filtered", reference_filter=75)
    add("disabled-curves-live-acquisition", "disabled", enabled=False)
    add("dropout", "dropout", segments=[[0,2000000,100,3000]], samples=[0,1000000,1900000,2240000,2240001,2500000,3000000,3200000])
    add("hidden-width-fault-and-ack", "hidden_fault", segments=[[0,1000000,100,3000],[1000000,1010000,100,500],[1010000,3200001,100,3000]],
        samples=[0,900000,1200000,1200002,2200000,3200000], ack_times=[1200001])
    add("flat-high", "flat", segments=[], manual_edges=[[0,1]])
    add("flat-low", "flat", segments=[], manual_edges=[])
    add("e50-phase1us", "nominal", phase_us=1)
    add("e50-loop-refinement", "nominal", refinement_us=1000)
    return rows


def stimulus(case):
    end=max(case["samples"]);events=set();phase=case.get("phase_us",0)
    for start,stop,hz,width in case["segments"]:
        period=Fraction(1000000,hz)
        for n in range(int(Fraction(stop-start,1)/period)+2):
            rise=start+round(n*period)+phase
            fall=start+round((n+1)*period)-width+phase
            for time,level in ((rise,1),(fall,0)):
                if start<=time<stop and time<=end:events.add((time,0,"edge",level))
    for time,level in case.get("manual_edges",[]):events.add((time,0,"edge",level))
    #2000RPM,60-2 wheel:58 physical teeth and a real missing-tooth gap.
    for cycle in range(end//30000+1):
        for tooth in range(58):
            rising=cycle*30000+tooth*500
            for time,level in ((rising,1),(rising+100,0)):
                if time<=end:events.add((time,1,"trigger",level))
    samples=set(case["samples"])
    if case.get("refinement_us"):samples.update(range(0,end+1,case["refinement_us"]))
    for time in samples:events.add((time,2,"observe",None))
    for time in case.get("ack_times",[]):events.add((time,3,"ack",None))
    events=sorted(events)
    text="".join(command+" "+str(time)+(" "+str(level)if level is not None else "")+"\n"for time,_,command,level in events)+"quit\n"
    return text,events


def audit(case,rows,events):
    failures=[]
    def check(condition,message):
        if not condition:failures.append(message)
    check(bool(rows)and rows[0]["kind"]=="ready","Missing setup receipt")
    if failures:return dict(passed=False,failures=failures)
    ready=rows[0]
    check(ready["time_us"]==0 and ready["flex_pin"]==2 and ready["flex_interrupt"]==0 and ready["trigger_pin"]==19,"Pin/clock fixture changed")
    check(ready["enabled"]==case["enabled"] and ready["callback_is_flexPulse"]==case["enabled"] and ready["trigger_callback_registered"] and ready["tick_before_input"],"Genuine setup/callback binding")
    expected_observations=[time for time,_,kind,_ in events if kind=="observe"]
    observations=[row for row in rows if row["kind"]=="snapshot"]
    check([row["time_us"]for row in observations]==expected_observations,"Snapshot coverage differs")
    if failures:return dict(passed=False,failures=failures)
    raw_edges=delivered=trigger_edges=counter=0;levels={"edge":0,"trigger":0};next_tick=1000000;last_edge=0;index=0
    for time,_,kind,level in events:
        while time>=next_tick:counter=0;next_tick+=1000000
        if kind in levels:
            changed=levels[kind]!=level;levels[kind]=level
            if changed and kind=="edge":
                raw_edges+=1;last_edge=time
                if case["enabled"]:
                    delivered+=1
                    if level:counter=(counter+1)%256
            elif changed and kind=="trigger" and ready["trigger_on_high"if level else "trigger_on_low"]:trigger_edges+=1
        elif kind=="observe":
            row=observations[index];index+=1;o=row["own"];r=row["reference"];label=case["name"]+":"+str(time)
            check(row["delivered_flex_edges"]==delivered and row["delivered_trigger_edges"]==trigger_edges and o["raw_edges"]==raw_edges and o["last_edge_us"]==last_edge,label+" actual callback/edge count")
            check(r["counter"]==counter,label+" independent one-second/mod256 counter")
            check(o["source"]==("synthetic_edges"if raw_edges else "unavailable"),label+" source provenance")
            check(o["corrections_enabled"]==case["enabled"],label+" correction enable")
            if o["valid"]:
                check(not o["pending_fault"]and o["reason"]=="ready"and o["capture_reason"]=="ready"and o["window_cycles"]==8 and o["sample_us"]<=time,label+" qualification")
                check(abs(o["sample_age_ms"]-(time-o["sample_us"])/1000)<1e-9 and o["sample_age_ms"]<=250,label+" sample freshness")
            if case["enabled"]and not o["valid"]:
                check(not o["corrections_valid"]and o["fuel_pct"]is None and o["spark_add_deg"]is None and o["temperature_pct"]is None,label+" invalid correction inhibition")
            if not case["enabled"]:
                check(o["corrections_valid"]and o["fuel_pct"]==100 and o["spark_add_deg"]==0 and o["temperature_pct"]==100,label+" disabled exact neutrality")
    tail=observations[-1];o=tail["own"];r=tail["reference"];expect=case["expectation"]
    if expect in ("startup","nominal","deadband","custom_span","filtered","disabled","tolerance"):
        check(o["valid"],"Expected qualified final own acquisition")
        hz=case["segments"][0][2];expected=max(0,min(100,100*(hz-case["low_hz"])/(case["high_hz"]-case["low_hz"])))
        check(o["ethanol_pct"]is not None and abs(o["ethanol_pct"]-expected)<.05,"Calibrated physical ethanol conversion")
        check(o["fuel_temp_c"]is not None and abs(o["fuel_temp_c"]-(.04125*case["segments"][0][3]-81.25))<1e-9,"Physical low-width temperature")
        if case["enabled"]:
            fuel=100+.5*o["ethanol_pct"]if case["ramp"]else 100
            spark=.1*o["ethanol_pct"]if case["ramp"]else 0
            check(abs(o["fuel_pct"]-fuel)<1e-8 and abs(o["spark_add_deg"]-spark)<1e-8,"Independent curve interpolation")
            temperature=100
            if case["ramp"]:
                x=[-40,0,20,40,80,125];y=[80,90,95,100,110,120];temperature=o["fuel_temp_c"]
                slot=next((n for n in range(5)if temperature<=x[n+1]),4)
                temperature=y[slot]+(y[slot+1]-y[slot])*(temperature-x[slot])/(x[slot+1]-x[slot])
            check(abs(o["temperature_pct"]-temperature)<1e-8,"Independent temperature curve interpolation")
    if expect=="startup":
        early=[row for row in observations if 160000<=row["time_us"]<1000000]
        check(early and all(x["reference"]["rpm"]==2000 and x["reference"]["sync"] and x["reference"]["fuel_pct"]==0 and x["reference"]["spark_add_deg"]==-40 and x["reference"]["pulse_us"]==0 for x in early),"Production native startup cache behavior changed")
        check(r["fuel_pct"]==100 and r["spark_add_deg"]==0 and r["pulse_us"]>0,"Post-second neutral production corrections")
    elif expect in ("frequency","sensor_fault","counter_wrap","pulse_width","flat","dropout"):
        check(not o["valid"]and not o["corrections_valid"],"Invalid signal must not enable own corrections")
        if expect not in("flat",):check(o["pending_fault"],"Fault must remain pending")
        if expect=="counter_wrap":check(r["ethanol_pct"]==50,"Production356Hz/mod256 alias changed")
        if case["name"]=="high-frequency160":check(r["ethanol_pct"]==100,"Production high-range clamp changed")
    elif expect=="custom_span":check(r["ethanol_pct"]==60 and abs(o["ethanol_pct"]-50)<1e-8,"Non-100Hz span difference changed")
    elif expect=="deadband":check(r["ethanol_pct"]==0 and abs(o["ethanol_pct"]-1)<.05,"One-pulse reference deadband changed")
    elif expect=="hidden_fault":
        before=next(x for x in observations if x["time_us"]==1200000);after=next(x for x in observations if x["time_us"]==1200002)
        check(not before["own"]["valid"]and before["own"]["pending_fault"]and before["own"]["capture_reason"]=="ready"and before["own"]["reason"]=="low_pulse_width_out_of_range","Recovered fault must remain visible before consumer ACK")
        check(after["own"]["valid"]and any(x["kind"]=="ack"and x["accepted"]for x in rows),"Explicit simulated consumer ACK recovery")
    return dict(passed=not failures,failures=failures,snapshots=len(observations),raw_edges=raw_edges,reference=tail["reference"],own=tail["own"])


def run(output,selected=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((CACHE/"build-manifest.json").read_text());binary=CACHE/"speeduino-flex-sim"
    if manifest["scope"]!="raw_edge_flex_acquisition_and_corrections_groundwork"or manifest["unit_test"]or digest(binary.read_bytes())!=manifest["binary_sha256"]:raise RuntimeError("Fixture attestation failed")
    before={name:digest((ROOT/name).read_bytes())for name in SOURCES}
    for name,expected in manifest["fixture_sources"].items():
        if before[name]!=expected:raise RuntimeError("Rebuild changed fixture source: "+name)
    (output/"native-build-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    results=[];chosen=[case for case in cases()if selected is None or case["name"]in selected]
    if not chosen or selected and set(selected)!={case["name"]for case in chosen}:raise ValueError("Unknown case selection")
    for case in chosen:
        body,events=stimulus(case);flags=[]
        if not case["enabled"]:flags.append("--disabled")
        if case["ramp"]:flags.append("--ramp")
        flags += ["--low",str(case["low_hz"]),"--high",str(case["high_hz"]),"--reference-filter",str(case["reference_filter"])]
        env={**os.environ,"GCOV_PREFIX":str(output.resolve()/"gcov"),"GCOV_PREFIX_STRIP":"0"}
        process=subprocess.run([str(binary),*flags],input=body,text=True,capture_output=True,env=env,timeout=30)
        prefix=output/case["name"]
        for extension,text in (("input",body),("stdout",process.stdout),("stderr",process.stderr)):
            prefix.with_suffix("."+extension+".gz").write_bytes(gzip.compress(text.encode(),mtime=0))
        rows=[json.loads(line)for line in process.stdout.splitlines()if line.strip()]
        result=audit(case,rows,events)if process.returncode==0 else dict(passed=False,failures=["Native exit"+str(process.returncode)])
        result.update(name=case["name"],case=case,flags=flags,input_sha256=digest(body.encode()),stdout_sha256=digest(process.stdout.encode()),exit_code=process.returncode)
        results.append(result);print(case["name"],"PASS"if result["passed"]else result["failures"],flush=True)
    after={name:digest((ROOT/name).read_bytes())for name in SOURCES}
    original_stable=all(digest(Path(name).read_bytes())==expected for name,expected in manifest["locked_original_input_hashes"].items())
    summary=dict(scope="raw_edge_flex_groundwork",passed=all(row["passed"]for row in results)and before==after and original_stable,
                 sources=before,sources_stable=before==after,original_inputs_stable=original_stable,physical_qualification=False,full_flex_integration=False,
                 execution="Production setup + attached raw callbacks + oneMSInterval + loop, alongside standalone own core; no production status injection",
                 results=results)
    (output/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True);parser.add_argument("--case",action="append")
    args=parser.parse_args();result=run(args.output,args.case)
    raise SystemExit(0 if result["passed"]else 1)
