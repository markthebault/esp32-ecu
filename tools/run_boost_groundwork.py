"""Execute the real production boost fixture and portable kernel/PWM probes.

This is isolated groundwork, not the full ECU/turbo-plant comparison. Own RPM
is authored; reference RPM comes only from real missing-tooth callbacks.
"""
import argparse
from dataclasses import asdict,dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

@dataclass(frozen=True)
class Case:
    name:str
    mode:str='open'
    duty:int=60
    map_kpa:int=130
    tps_pct:int=50
    target:int=150
    frequency:int=24
    cut:int=220
    duration_us:int=1200000
    stop_trigger_us:int=1200000
    high_pressure_at_us:int=0
    default_compare:bool=False
    tps_ramp:bool=False

def cases():
    return [Case('disabled',mode='off'),Case('open-zero',duty=0),Case('open20',duty=20),
        Case('open60'),Case('open100',duty=100),Case('closed-feedforward',mode='closed',duty=30,duration_us=4500000,stop_trigger_us=4500000),
        Case('closed-below-activation',mode='closed',duty=30,map_kpa=100,duration_us=4500000,stop_trigger_us=4500000),
        Case('trigger-stall',duration_us=1800000,stop_trigger_us=600000),
        Case('overboost',high_pressure_at_us=600000),Case('unarmed-native-timer',default_compare=True),
        *[Case(f'tps-ramp-{tps}',duty=tps,tps_pct=tps,tps_ramp=True) for tps in (20,40,60,80)]]

def edge_stats(rows,minimum):
    edges=[r for r in rows if r['kind']=='boost_edge' and r['time_us']>=minimum]
    cycles=[]
    for n in range(len(edges)-2):
        a,b,c=edges[n:n+3]
        if a['high'] and not b['high'] and c['high']:
            period=c['time_us']-a['time_us'];high=b['time_us']-a['time_us']
            if period<=0 or not 0<high<period:raise ValueError('Invalid executed PWM ordering')
            cycles.append(dict(period_us=period,high_us=high,duty_pct=100*high/period))
    return dict(edge_count=len(edges),cycles=len(cycles),
        period_range_us=[min(c['period_us'] for c in cycles),max(c['period_us'] for c in cycles)] if cycles else None,
        duty_range_pct=[min(c['duty_pct'] for c in cycles),max(c['duty_pct'] for c in cycles)] if cycles else None)

def reference(binary,c,folder):
    flags=(['--default-unarmed-compare'] if c.default_compare else [])+(['--tps-duty-ramp'] if c.tps_ramp else [])
    args=[str(binary),c.mode,str(c.duty if not c.tps_ramp else 0),str(c.target),str(c.frequency),str(c.cut),*flags]
    p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        ready=p.stdout.readline();g=json.loads(ready)
        if g['kind']!='ready' or g['time_us']!=0 or g['physical_execution'] is not False:raise ValueError('Reference initialization differs')
        start=1000;end=start+c.duration_us
        events=[(start,0,f'sensors {start} {c.map_kpa} {c.tps_pct}')]
        for n,t in enumerate(range(start,start+c.stop_trigger_us,500)):
            if n%60<58:events.extend([(t,1,f'trigger {t} 1'),(t+5,1,f'trigger {t+5} 0')])
        if c.high_pressure_at_us:
            t=start+c.high_pressure_at_us;events.append((t,0,f'sensors {t} 230 {c.tps_pct}'))
        for t in range(start,end+1,5000):events.append((t,2,f'observe {t}'))
        body='\n'.join(e[2] for e in sorted(events))+'\nquit\n';(folder/'reference-input.txt').write_text(body)
        stdout,stderr=p.communicate(body,timeout=60)
        (folder/'reference.jsonl').write_text(ready+stdout);(folder/'reference-stderr.log').write_text(stderr)
        if p.returncode or stderr:raise RuntimeError('Reference failed: '+stderr)
        return [g,*[json.loads(line) for line in stdout.splitlines()]]
    finally:
        if p.poll() is None:p.kill();p.communicate()

def own(binary,c,folder):
    body=[]
    for elapsed in range(0,c.duration_us+1,5000):
        now=elapsed+1000;pressure=230 if c.high_pressure_at_us and elapsed>=c.high_pressure_at_us else c.map_kpa
        # An authored stopped input after the declared trigger-stop interval.
        running=int(c.stop_trigger_us>=c.duration_us or elapsed<c.stop_trigger_us)
        body.append(f'sample {now} {pressure} {c.tps_pct} {2000 if running else 0} 100 {running} 0 0 7')
    text='\n'.join(body)+'\nquit\n';(folder/'own-input.txt').write_text(text)
    args=[str(binary),c.mode,str(c.duty),str(c.target),str(c.frequency),str(c.cut)]
    p=subprocess.run(args,input=text,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    (folder/'own.jsonl').write_text(p.stdout);(folder/'own-stderr.log').write_text(p.stderr)
    if p.returncode or p.stderr:raise RuntimeError('Own replay failed: '+p.stderr)
    rows=[json.loads(line) for line in p.stdout.splitlines()]
    if any(r['kind']=='sample' and (not r['pwm_accepted'] or r['pwm_fault']) for r in rows):raise ValueError('Own PWM fault/rejected command')
    return rows

def check_case(c,ref,portable):
    a=[r for r in ref if r['kind']=='sample'];b=[r for r in portable if r['kind']=='sample']
    if len(a)!=c.duration_us//5000+1 or len(b)!=len(a):raise ValueError('Incomplete query inventory')
    for rows in (ref,portable):
        if not all(r['physical_execution'] is False for r in rows):raise ValueError('Invalid provenance')
    if a[100]['rpm']!=2000:raise ValueError('Reference did not acquire true trigger-derived RPM')
    settle=3601000 if c.mode=='closed' else 401000
    a_pwm=edge_stats(ref,settle);b_pwm=edge_stats(portable,settle)
    result=dict(case=asdict(c),reference_last=a[-1],own_last=b[-1],reference_pwm=a_pwm,own_pwm=b_pwm)
    if c.mode=='closed':
        targets=[r for r in a if r['boost_target_kpa']]
        if not targets:raise ValueError('Production closed-loop target never updated; PWM frequency is not yet meaningful')
        result['reference_first_nonzero_target_query_us']=targets[0]['time_us']
        if not 3300000<=targets[0]['time_us']<=3305000:raise ValueError('Native33ms/100ms shared-mask timing witness changed')
        result['timing_difference']='Under the declared fast native loop, nested33ms/100ms gates first coincide at3300ms; own PID uses an explicit period.'
    if c.name in ('disabled','open-zero','closed-below-activation'):
        if any(r['boost_duty_pct'] or r['boost_pin_high'] for r in a[100:]+b[100:]):raise ValueError('Expected zero PWM')
        if any(r['high'] for rows in (ref,portable) for r in rows if r['kind']=='boost_edge' and r['time_us']>=401000):raise ValueError('Unexpected high edge between zero-duty query observations')
    elif c.name=='unarmed-native-timer':
        if a[-1]['boost_duty_pct']!=60 or a_pwm['edge_count'] or not b_pwm['cycles']:raise ValueError('Missing requested-vs-executed negative witness')
    elif c.name=='trigger-stall':
        if a[-1]['rpm'] or a[-1]['boost_duty_pct'] or a[-1]['boost_pin_high'] or b[-1]['boost_duty_pct'] or b[-1]['boost_pin_high']:raise ValueError('Stall did not remove boost duty')
    elif c.name=='overboost':
        if not a[-1]['boost_cut'] or a[-1]['fuel_channels'] or a[-1]['spark_channels']:raise ValueError('Reference protection did not cut both scheduling masks')
        if not b[-1]['inhibit_engine'] or b[-1]['boost_duty_pct'] or b[-1]['boost_pin_high']:raise ValueError('Own overboost did not inhibit engine/valve')
        result['policy_difference']='Reference boost duty may persist while engine protection cuts scheduling masks; own kernel deenergizes.'
    elif c.tps_ramp:
        # The fixture stores the documented half-percent TPS axis and
        # declared duty cells; report the production lookup scaling explicitly.
        if a[-1]['boost_lookup_tps_coordinate']!=4*a[-1]['tps_pct'] or a[-1]['boost_lookup_y_factor']!=2 or a[-1]['boost_stored_tps_coordinate']!=2*a[-1]['tps_pct']:raise ValueError('Unexpected production TPS lookup scale')
        if abs(a[-1]['boost_duty_pct']-a[-1]['tps_pct'])>3:raise ValueError('TPS conversion/interpolation witness differs')
        if b[-1]['boost_duty_pct']!=c.tps_pct:raise ValueError('Own physical-percent demand differs')
        for pwm,r in ((a_pwm,a[-1]),(b_pwm,b[-1])):
            if pwm['cycles']<5 or any(abs(p-1e6/c.frequency)>8 for p in pwm['period_range_us']):raise ValueError('TPS ramp PWM period differs')
            if any(abs(d-r['boost_duty_pct'])>.6 for d in pwm['duty_range_pct']):raise ValueError('TPS ramp executed duty differs')
        result['unit_observation']='Production raw half-percent TPS, table yFactor2 and physical-percent duty agree within integer table/ADC quantization.'
    elif c.name=='open100':
        if a[-1]['boost_duty_pct']!=100 or not a[-1]['boost_pin_high'] or b[-1]['boost_duty_pct']!=100 or not b[-1]['boost_pin_high']:raise ValueError('Expected full duty')
    else:
        for pwm in (a_pwm,b_pwm):
            if pwm['cycles']<5 or any(abs(p-1e6/c.frequency)>8 for p in pwm['period_range_us']):raise ValueError('Executed PWM period differs from declared frequency')
        for r,pwm in ((a[-1],a_pwm),(b[-1],b_pwm)):
            if any(abs(d-r['boost_duty_pct'])>.6 for d in pwm['duty_range_pct']):raise ValueError('Executed duty differs from request/declared quantization')
        if abs(a[-1]['boost_duty_pct']-b[-1]['boost_duty_pct'])>1:raise ValueError('Comparable steady duty differs')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    names=['tools/run_boost_groundwork.py','tools/boost_core_sim.cpp','firmware/include/ecu/boost_control.hpp','firmware/include/ecu/boost_pwm.hpp','firmware/include/ecu/idle_pwm.hpp','firmware/include/ecu/realtime.hpp']
    hashes={n:digest(ROOT/n) for n in names}
    for n in names:
        target=output/'sources'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,target)
    binary=args.reference.resolve();m=json.loads(binary.with_name('build-manifest.json').read_text())
    if digest(binary)!=m['binary_sha256'] or m['unit_test'] is not False or m['speeduino_sha']!='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20':raise ValueError('Reference attestation differs')
    command=['g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(ROOT/'firmware/include'),str(ROOT/'tools/boost_core_sim.cpp'),'-o',str(output/'own-core')]
    with (output/'build.log').open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
    (output/'build-command.json').write_text(json.dumps(command,indent=2)+'\n')
    results=[];selected=cases();active=None
    def state(status,error=None):
        report=dict(status=status,complete=status=='complete',scope=__doc__,planned_cases=[c.name for c in selected],
            completed_cases=[r['case']['name'] for r in results],active_case=active,
            failure=None if error is None else dict(type=type(error).__name__,message=str(error)),
            cases=results,source_sha256=hashes,reference_manifest_sha256=digest(binary.with_name('build-manifest.json')),
            own_binary_sha256=digest(output/'own-core'),physical_qualification=False)
        temporary=output/'results.json.pending';temporary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');os.replace(temporary,output/'results.json')
    state('running')
    try:
        for case in selected:
            active=case.name;state('running')
            folder=output/case.name;folder.mkdir();ref=reference(binary,case,folder);portable=own(output/'own-core',case,folder)
            result=check_case(case,ref,portable);results.append(result);print(json.dumps(dict(case=case.name,passed=True)),flush=True);state('running')
        if hashes!={n:digest(ROOT/n) for n in names}:raise ValueError('Study source changed')
        active=None;state('complete')
    except BaseException as error:state('failed',error);raise

if __name__=='__main__':main()
