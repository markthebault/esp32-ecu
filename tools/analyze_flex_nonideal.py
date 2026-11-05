"""Audit complete conditional matrices and compare their discrete observations.

The comparison is a numerical/model observation, never physical qualification.
"""
import argparse
import ast
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile
import numpy as np

AUDITOR_SOURCE = Path(__file__).read_bytes()
AUDITOR_SHA256 = hashlib.sha256(AUDITOR_SOURCE).hexdigest()
THRESHOLDS = ((.25, .25), (.5, .5), (.75, .75), (.75, .25))


def require_replays(observations):
    expected={(r,f,s,b) for r,f in THRESHOLDS for s in range(3) for b in ('absolute','ratiometric')}
    actual=[(o['rising_fraction'],o['falling_fraction'],o['strategy'],o['calibration_basis']) for o in observations]
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise ValueError('Missing, duplicate or unexpected controller replay inventory')


def require_replay_path(case, observation):
    stem=f"gpio-{observation['rising_fraction']}-{observation['falling_fraction']}-strategy{observation['strategy']}-{observation['calibration_basis']}"
    if observation['transcript']!=f'{case}/{stem}.jsonl.gz':
        raise ValueError('Controller replay identity/path differs')


def same_tree(actual, expected, context):
    """Allow floating arithmetic roundoff, never a changed discrete quantity."""
    if type(expected) is dict:
        if type(actual) is not dict or actual.keys()!=expected.keys():raise ValueError(context+': fields differ')
        for key,value in expected.items():same_tree(actual[key],value,context+'.'+key)
    elif type(expected) is list:
        if type(actual) is not list or len(actual)!=len(expected):raise ValueError(context+': length differs')
        for n,(a,b) in enumerate(zip(actual,expected)):same_tree(a,b,f'{context}[{n}]')
    elif type(expected) is float:
        if type(actual) not in (float,int) or not math.isfinite(actual) or not math.isclose(actual,expected,rel_tol=2e-14,abs_tol=1e-12):
            raise ValueError(context+': numeric value differs')
    elif type(actual) is not type(expected) or actual!=expected:raise ValueError(context+': value differs')


def derive_sampling(s, time, values):
    """Independent piecewise-linear raw-to-point conversion audit.

    Does not import or execute the producer. These are the declared experiment
    equations, not a second physical ADC model.
    """
    interval=None
    if s['ripple5_v'] or s['ripple33_v']:
        nonzero=abs(math.sin(math.radians(s['ripple_phase_deg'])))>1e-12
        interval=[s['disturbance_us']+(0 if nonzero else s['disturbance_rise_us']),
            s['disturbance_us']+s['disturbance_rise_us']+s['ripple_cycles']*1e6/s['ripple_hz']+(s['disturbance_rise_us'] if nonzero else 0)]
    def at(column,us):return float(np.interp(us/1e6,time,values[column]))
    queries=[];start=s['adc_phase_us']
    while start<s['duration_ms']*1000-503:
        first=float(start-333);samples=[];codes=[]
        for channel in range(8):
            when=first+48*channel;begin=when-3;end=when+24
            if time[0]>begin/1e6 or time[-1]<end/1e6:raise ValueError('Raw trace does not cover scan window')
            reference=at('adc_ref',when)
            if not 2.7<=reference<=5.5:raise ValueError('Unsupported instantaneous reference domain')
            if channel<4:pin=at(('map_adc','tps_adc','clt_adc','iat_adc')[channel],when)
            elif channel<7:pin=(1.5,1.2,14/13)[channel-4]
            else:pin=at('adc_hold' if s['sample_enabled'] else 'adc7',when)
            codes.append(min(4095,max(0,math.floor(4096*pin/reference))))
            left,right=np.searchsorted(time,[begin/1e6,end/1e6])
            extrema=[at('adc_ref',begin),at('adc_ref',end)]
            if right>left:extrema.extend((float(values['adc_ref'][left:right].min()),float(values['adc_ref'][left:right].max())))
            bounds=[min(extrema),max(extrema)]
            samples.append(dict(channel=channel,acquisition_us=[begin,when],conversion_us=[when,end],
                pin_v=pin,reference_v=reference,reference_range_v=bounds,
                reference_span_fullscale_lsb=(bounds[1]-bounds[0])/reference*4096,
                reference_in_voltage_domain_for_window=2.7<=bounds[0]<=bounds[1]<=5.5,
                source_ripple_overlaps_acquisition=bool(interval and begin<interval[1] and when>interval[0]),
                source_ripple_overlaps_conversion=bool(interval and when<interval[1] and end>interval[0])))
        queries.append(dict(control_us=float(start+500),sampled_us=first,adc_ok=1,
            adc_reference_v=samples[-1]['reference_v'],raw=codes,samples=samples))
        start=s['adc_phase_us']+5000*len(queries)
    hits=lambda key:[dict(query=n,channel=x['channel'],window_us=x[key+'_us']) for n,q in enumerate(queries) for x in q['samples'] if x['source_ripple_overlaps_'+key]]
    return dict(conversion_model='ideal held-signal/instant-reference point at acquisition end; not physical SAR',
        switching_charge_model_channels=[7],ideal_buffered_channels=[4,5,6],spi_success_assumed=True,
        adc_ok_is_not_reference_or_supply_oracle=True,
        conversion_window_model='Authored12-clock24us observation window, not a SAR bit/charge-redistribution computation',
        source_ripple_interval_us=interval,physical_cpu_and_spi_timing_qualified=False,queries=queries,
        source_ripple_acquisition_hits=hits('acquisition'),source_ripple_conversion_hits=hits('conversion'))


def derive_edges(time, normalized, rising, falling):
    if not 0<falling<=rising<1:raise ValueError('Invalid GPIO threshold')
    candidates=[]
    for threshold,level in ((rising,1),(falling,0)):
        a,b=normalized[:-1],normalized[1:]
        crossings=(a<threshold)&(b>=threshold) if level else (a>threshold)&(b<=threshold)
        for i in np.flatnonzero(crossings):
            fraction=(threshold-normalized[i])/(normalized[i+1]-normalized[i])
            candidates.append((float(time[i]+fraction*(time[i+1]-time[i]))*1e6,level))
    state=1 if normalized[0]>=rising else 0 if normalized[0]<=falling else None
    edges=[]
    for us,level in sorted(candidates):
        if state!=level:edges.append((us,level));state=level
    return edges


def expected_stimulus(edges, queries):
    rows=[(t,0,f'E {t:.12f} {level}') for t,level in edges]
    rows.extend((q['control_us'],1,f"Q {q['control_us']:.12f} {q['sampled_us']:.12f} {q['adc_ok']} {q['adc_reference_v']:.17g} "+' '.join(map(str,q['raw']))) for q in queries)
    return '\n'.join(row[2] for row in sorted(rows))+'\n'


def msl_expected(frame, started_us):
    """Explicit JSON/MSL007 contract, including unknown values and all229 fields."""
    cols={}
    def put(label,value,unit):cols[label]=(value,unit)
    def group(obj,spec):
        for item in spec.split():
            label,key,unit=item.split(':');put(label,obj[key],unit)
    put('Time',(int(frame['control_us'])-started_us)/1e6,'s')
    put('RowSequence',int(frame['sequence']),'count');put('SnapshotSequence',int(frame['sequence']),'count')
    group(frame,'ControlAge:control_age_ms:ms SensorAge:sample_age_ms:ms Source:source_code:code TuneRevision:tune_revision:count SensorRevision:sensor_revision:count PhaseEpoch:phase_epoch:count Flags:flags:bitfield Faults:controller_faults:bitfield State:state_code:code Strategy:strategy_code:code PhaseReason:phase_reason_code:code PhaseLosses:phase_losses:count CamRejected:cam_rejected:count CamError:cam_error_deg:deg')
    group(frame['worker_observation'],'WorkerCommand:command_sequence:count WorkerAge:age_ms:ms WorkerEpoch:epoch:count WorkerTuneRevision:tune_revision:count WorkerSensorRevision:sensor_revision:count TimingFault:timing_fault_code:code LastTimingFault:last_timing_fault_code:code VirtualMask:virtual_high_mask:bitfield PhysicalCommandMask:physical_command_mask:bitfield')
    group(frame,'BoardFlags:board_flags:bitfield InputValidMask:input_valid_mask:bitfield')
    group(frame['inputs'],'RPM:rpm:RPM MAP:map_kpa:kPa TPS:tps_pct:% CLT:clt_c:C IAT:iat_c:C Lambda:lambda:lambda Battery:battery_v:V Sensor5V:sensor_v:V')
    group(frame['proposals'],'ProposedRPM:rpm:RPM VE:ve_pct:% LambdaTarget:target_lambda:lambda ProposedAdvance:advance_deg:deg ProposedPW:pulse_ms:ms ProposedDwell:dwell_ms:ms DeadTime:deadtime_ms:ms AirMass:air_mg:mg Warmup:warmup:ratio Afterstart:afterstart:ratio Accel:accel:ratio EGO:ego:ratio Duty:duty_pct:% IdleProposal:idle_pct:%')
    for n,value in enumerate(frame['raw_adc']):put(f'ADC{n}',value,'count')
    group(frame['cylinders'],'CylinderValidMask:valid_mask:bitfield CylinderTrimsEnabled:enabled:bool CylinderCapacityMask:capacity_mask:bitfield CylinderSparkClampMask:spark_clamp_mask:bitfield CylinderRetardFloorMask:retard_floor_mask:bitfield')
    for n,cylinder in enumerate(frame['cylinders']['proposals'],1):
        for label,key,unit in [('PW','pulse_ms','ms'),('Advance','advance_deg','deg'),('FuelTrim','fuel_pct','%'),('Duty','duty_pct','%')]:put(f'C{n}{label}',cylinder[key],unit)
    group(frame['idle'],'IdleTarget:target_rpm:RPM IdleDuty:duty_pct:% IdleFeedforward:feedforward_pct:% IdleP:p_term:% IdleI:i_term:% IdleD:d_term:% IdleFlags:flags:bitfield IdleState:state_code:code IdleReason:reason_code:code IdleAlgorithm:algorithm_code:code IdlePidUpdates:pid_updates:count IdleAvailable:available:bool')
    group(frame['transient_enrichment'],'AeTpsDot:tps_dot_pct_s:%/s AeMapDot:map_dot_kpa_s:kPa/s AeWindowMs:window_ms:ms AeTriggerDot:trigger_dot:source_units/s AeCorrectionPct:correction_pct:% AeUnclampedPct:unclamped_pct:% AeRemainingAtSampleMs:remaining_ms:ms AeAddedFuelMg:added_fuel_mg:mg AeFlags:flags:bitfield AeMode:mode_code:code AeApply:apply_code:code AePhase:phase_code:code AeReason:reason_code:code AeAvailable:available:bool')
    group(frame['load_model'],'LoadFuel:fuel_load:source_units LoadSpark:spark_load:source_units LoadLambda:lambda_load:source_units LoadTrim:trim_load:source_units LoadPressureFactor:pressure_factor:ratio LoadBaro:baro_kpa:kPa LoadEmap:emap_kpa:kPa LoadAux:aux_kpa:kPa LoadAfrFactor:afr_factor:ratio LoadFlags:flags:bitfield LoadFuelSource:fuel_source_code:code LoadSparkSource:spark_source_code:code LoadLambdaSource:lambda_source_code:code LoadTrimSource:trim_source_code:code LoadPressure:pressure_code:code LoadAuxRole:aux_role_code:code LoadBaroSource:baro_source_code:code LoadAfr:afr_code:code LoadReason:reason_code:code LoadAfrState:afr_state_code:code LoadAvailable:available:bool')
    for kind in ('fuel','spark'):
        obj=frame['secondary_tables'][kind];prefix='Sec'+kind.title();unit='%' if kind=='fuel' else 'deg'
        spec=[('Primary','primary',unit),('PrimaryCorrected','primary_corrected',unit),('Secondary','secondary','cell_units'),('Combined','combined',unit),('Coordinate','coordinate','source_units'),('ConditionValue','condition_value','condition_units'),('InputAgeMs','input_age_ms','ms'),('Threshold','threshold','condition_units'),('DebounceMs','debounce_ms','ms'),('Flags','flags','bitfield')]
        spec.extend((label,key,'code') for label,key in [('Mode','mode_code'),('Cells','cells_code'),('Source','source_code'),('Reason','reason_code'),('InputSource','input_source_code'),('Condition','condition_code'),('Axis','axis_code'),('InputChannel','input_channel')])
        spec.append(('ObservedUs','input_observed_us','us'))
        spec.extend((label,key,'bool') for label,key in [('Available','available'),('Evaluated','evaluated'),('Active','active'),('Clamped','clamped'),('Pending','pending'),('InputQualified','input_qualified'),('InputLevel','input_level'),('PendingLevel','pending_level'),('InputValid','input_valid'),('InputRaw','input_raw'),('ActiveHigh','active_high'),('Valid','valid')])
        for label,key,u in spec:put(prefix+label,obj[key],u)
    flex=frame['flex_fuel']
    spec=[('FrequencyHz','frequency_hz','Hz'),('LowPulseUs','low_pulse_us','us'),('EthanolPct','ethanol_pct','% ethanol'),('FuelTempC','fuel_temp_c','C'),('UnfilteredEthanolPct','unfiltered_ethanol_pct','% ethanol'),('UnfilteredFuelTempC','unfiltered_fuel_temp_c','C'),('SampleAgeMs','sample_age_ms','ms'),('FuelPct','fuel_pct','%'),('SparkAddDeg','spark_add_deg','deg delta'),('TemperaturePct','temperature_pct','%')]
    spec.extend((label,key,'code') for label,key in [('SourceCode','source_code'),('ReasonCode','reason_code'),('CaptureReasonCode','capture_reason_code'),('LastFaultCode','last_fault_code'),('CorrectionReasonCode','correction_reason_code'),('WindowCycles','window_cycles'),('ConfigurationRevision','configuration_revision')])
    spec.extend((label,key,'us' if n<3 else 'count') for n,(label,key) in enumerate([('SampleUs','sample_us'),('WindowStartUs','window_start_us'),('LastEdgeUs','last_edge_us'),('RawEdges','raw_edges'),('FaultGeneration','fault_generation'),('AcknowledgedGeneration','acknowledged_generation'),('ConfigEpoch','config_epoch')]))
    spec.extend((label,key,'bool') for label,key in [('Required','required'),('ConfigurationMatch','configuration_match'),('ValueQualified','value_qualified'),('RawCaptureQualified','raw_capture_qualified'),('ControlOk','control_ok'),('CaptureValid','capture_valid'),('SampleValueValid','sample_value_valid'),('PendingFault','pending_fault'),('FrequencyClamped','frequency_clamped'),('TemperatureClamped','temperature_clamped'),('InputConfirmed','input_confirmed'),('CorrectionsEnabled','corrections_enabled'),('CorrectionsValid','corrections_valid'),('SparkBypassed','spark_bypassed'),('SparkClamped','spark_clamped'),('ZeroFactor','zero_factor'),('Available','available')])
    for label,key,u in spec:put('Flex'+label,flex[key],u)
    if len(cols)!=229:raise ValueError('Incomplete MSL007 audit contract')
    return cols


def verify_msl(path, frames):
    with path.open() as f:rows=list(csv.reader(f,delimiter='\t'))
    if not frames or len(rows)!=len(frames)+4 or rows[0]!=['ESP32ECU ENGINE LOG 007'] or len(rows[1])!=1:
        raise ValueError('Native MSL007 provenance/retention differs')
    duration=int(frames[-1]['control_us'])//1000000+1
    prefix=f'SYNTHETIC ENGINE REPLAY / boot synthetic-circuit-no-target / log 1 / period_ms=5 duration_s={duration} / retained rows 1..{len(frames)} of {len(frames)} / overwritten=0 missed_periods=0 repeated=0 invalid=0 / '
    if not rows[1][0].startswith(prefix):raise ValueError('Native MSL007 provenance/retention differs')
    for n,(frame,row) in enumerate(zip(frames,rows[4:])):
        expected=msl_expected(frame,int(frames[0]['control_us']))
        if rows[2]!=list(expected) or rows[3]!=[u for _,u in expected.values()] or len(row)!=len(expected):raise ValueError('Native MSL007 columns/units differ')
        for (name,(value,unit)),text in zip(expected.items(),row):
            if value is None:ok=text=='NaN'
            elif name=='Time':ok=text==f'{value:.6f}'
            elif unit in ('count','code','bitfield','bool') or isinstance(value,str):
                ok=text==str(int(value))
            else:
                number=float(text)
                # Native %.9g fields: at most half a unit in the ninth
                # significant digit; JSON carries the unformatted value.
                ok=math.isfinite(number) and math.isclose(number,float(value),rel_tol=5.1e-9,abs_tol=5e-12)
            if not ok:raise ValueError(f'Native MSL007 value differs at row{n+1}/{name}')


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def member(root,name):
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Evidence path escapes matrix')
    return path


def load_complete(root,allow_partial=False):
    summary=json.loads((root/'results.json').read_text())
    complete=summary.get('status')=='complete' and summary.get('complete') is True
    partial=summary.get('status')=='failed' and summary.get('complete') is False and summary.get('failure') is not None
    if not complete and not (allow_partial and partial):
        raise ValueError('Matrix is incomplete or failed; partial results are not acceptance evidence')
    plan=json.loads((root/'matrix-plan.json').read_text())
    names=[s['name'] for s in plan['selected_cases']]
    completed=summary['completed_case_names']
    if not names or len(set(names))!=len(names) or summary['selected_case_names']!=names or completed!=names[:len(completed)] or (complete and completed!=names):
        raise ValueError('Planned/completed case inventory differs')
    if (complete and summary['failure'] is not None) or summary['physical_qualification'] is not False:raise ValueError('Invalid completion/scope')
    for name,expected in summary['source_sha256'].items():
        if digest(member(root,'sources/'+name))!=expected:raise ValueError('Frozen source differs: '+name)
    if summary['source_sha256']!=plan['source_sha256']:raise ValueError('Plan/source binding differs')
    if len(summary['cases'])!=len(completed):raise ValueError('Case count differs')
    for planned,case in zip(plan['selected_cases'],summary['cases']):
        if planned!=case['scenario'] or case.get('status')!='complete':raise ValueError('Case declaration differs')
    tree=ast.parse((root/'sources/tools/run_flex_nonideal.py').read_text())
    columns=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COLUMNS' for t in n.targets))
    return summary,columns


def verify_decks(root, cases, bound, binding_source=None):
    """Regenerate decks from this owned experiment's verified frozen authoring.

    This executes trusted project Python in a separate interpreter, only for
    deck construction. Raw-to-scan and edge reconstruction above is independent.
    Never use this auditor to execute sources from an untrusted evidence bundle.
    """
    code='''import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'sources/tools'))
import run_flex_nonideal as producer
cases=json.loads(sys.stdin.read());result={}
for case in cases:
    text=producer.deck(producer.Scenario(**case['scenario'])).encode()
    result[case['scenario']['name']]=hashlib.sha256(text).hexdigest()
print(json.dumps(result))
'''
    # The first producer recorded the parent's hash in binding, but omitted
    # its bytes from sources/. Recover only that exact already-bound input;
    # never modify the original experiment or silently use a different parent.
    parent='hardware/a5-idle-interface/net_contract.json';recovered={}
    with tempfile.TemporaryDirectory(prefix='ecu-deck-audit-') as directory:
        owned=Path(directory);shutil.copytree(root/'sources',owned/'sources')
        destination=owned/'sources'/parent
        if not destination.exists():
            source=binding_source or Path(__file__).resolve().parents[1]/parent
            if digest(source)!=bound['carrier_sha256']:raise ValueError('Recovered parent differs from recorded pre-run binding')
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
            recovered[parent]=dict(sha256=bound['carrier_sha256'],recovered_from=str(source),
                hash_recorded_before_run=True,bytes_retained_in_original_source_tree=False)
        elif digest(destination)!=bound['carrier_sha256']:raise ValueError('Frozen parent binding differs')
        output=subprocess.run([sys.executable,'-I','-B','-c',code,str(owned)],input=json.dumps(cases),
            text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=60)
    expected=json.loads(output.stdout)
    for case in cases:
        name=case['scenario']['name']
        if digest(member(root,name+'/circuit.cir'))!=expected[name]:
            raise ValueError('Circuit deck differs from frozen scenario authoring: '+name)
    return recovered


def stimulus(root,case,rising,falling,expected):
    name=f"{case}/gpio-{rising}-{falling}.stimulus.txt"
    body=member(root,name).read_text()
    if body!=expected:raise ValueError('Stimulus differs from raw-derived GPIO/ADC queries')
    events=[]
    for line in body.splitlines():
        parts=line.split()
        if parts[0]=='E':events.append((float(parts[1]),int(parts[2])))
    return events


def audit(root,allow_partial=False,binding_source=None):
    summary,columns=load_complete(root,allow_partial);cases={};traces=0
    recovered=verify_decks(root,summary['cases'],summary['binding'],binding_source)
    inputs={}
    def retain(path):
        inputs[str(path.relative_to(root))]=digest(path)
    retain(root/'results.json');retain(root/'matrix-plan.json')
    tool=json.loads((root/'toolchain.json').read_text());retain(root/'toolchain.json')
    for name,key in [('toolchain/ngspice-elf','executable_sha256'),('toolchain/spice-lib/scripts/spinit','startup_sha256')]:
        path=member(root,name)
        if digest(path)!=tool[key]:raise ValueError('Retained solver/startup hash differs')
        retain(path)
    baseline=None
    for case in summary['cases']:
        require_replays(case['observations'])
        name=case['scenario']['name'];folder=member(root,name)
        if not name or Path(name).name!=name:raise ValueError('Invalid case name')
        if case['sampling_file']!='sampling.json':raise ValueError('Sampling identity/path differs')
        for observation in case['observations']:require_replay_path(name,observation)
        raw=folder/'values.txt.gz'
        if digest(raw)!=case['raw_sha256']:raise ValueError('Raw archive hash differs')
        retain(raw)
        numerical_log=folder/'ngspice.log';retain(numerical_log)
        if any(token in numerical_log.read_text() for token in ('simulation(s) aborted','Timestep too small')):raise ValueError('Solver abort diagnostics')
        retain(folder/'circuit.cir')
        with gzip.open(raw,'rb') as f:data=np.loadtxt(f,skiprows=1,ndmin=2)
        if data.shape!=(case['raw_rows'],len(columns)) or not np.isfinite(data).all():raise ValueError('Raw trace shape/values differ')
        if not np.all(np.diff(data[:,0])>0) or not math.isclose(float(data[-1,0]),case['scenario']['duration_ms']/1000,rel_tol=0,abs_tol=1e-12):
            raise ValueError('Strict numerical time/end contract failed')
        values={n:data[:,i] for i,n in enumerate(columns)}
        if np.min(values['module33'])<=0:raise ValueError('Unsupported GPIO supply')
        derived=derive_sampling(case['scenario'],data[:,0],values)
        sampling_path=member(root,name+'/'+case['sampling_file']);retain(sampling_path)
        sampling=json.loads(sampling_path.read_text());same_tree(sampling,derived,'Raw-derived sampling')
        queries=derived['queries']
        threshold_edges={(r,f):derive_edges(data[:,0],values['gpio']/values['module33'],r,f) for r,f in THRESHOLDS}
        if case['ripple_acquisition_samples']!=len(derived['source_ripple_acquisition_hits']) or case['ripple_conversion_samples']!=len(derived['source_ripple_conversion_hits']):
            raise ValueError('Case exposure counters differ')
        row=dict(scenario=case['scenario'],raw_rows=len(data),queries=queries,
            ripple_acquisition_samples=len(sampling['source_ripple_acquisition_hits']),
            ripple_conversion_samples=len(sampling['source_ripple_conversion_hits']),
            dynamic_reference_sample_count=sum(s['reference_span_fullscale_lsb']>1 for q in queries for s in q['samples']),
            max_reference_span_fullscale_lsb=max(s['reference_span_fullscale_lsb'] for q in queries for s in q['samples']),
            waveform_ranges={n:[float(np.min(data[:,i])),float(np.max(data[:,i]))] for i,n in enumerate(columns) if n in ('sensor5','adc_ref','module33','adc7')},
            edge_inputs={},replays={})
        del values,data
        for obs in case['observations']:
            label=f"{obs['rising_fraction']}-{obs['falling_fraction']}:{obs['strategy']}:{obs['calibration_basis']}"
            path=member(root,obs['transcript'])
            if digest(path)!=obs['transcript_sha256']:raise ValueError('Controller transcript hash differs')
            retain(path)
            stat=dict(rows=0,faulted=0,ready=0,acknowledgements=0,phase0=[],fault_masks={},canonical_sha256=None)
            h=hashlib.sha256();map_errors=[];seen=set();phase0=[]
            with gzip.open(path,'rt') as file:
                for text in file:
                    frame=json.loads(text);seq=int(frame['sequence']);phase=frame['circuit_clock_phase_us'];key=(seq,phase)
                    if key in seen or not 1<=seq<=len(queries):raise ValueError('Controller sequence duplicate/out of range')
                    seen.add(key);query=queries[seq-1]
                    if frame['schema_version']!=1 or frame['data_source']!='synthetic_control_observation' or frame['physical_execution'] is not False:
                        raise ValueError('Controller provenance differs')
                    if frame['raw_adc']!=query['raw'] or int(frame['control_us'])!=math.floor(query['control_us']+phase) or int(frame['sampled_us'])!=math.floor(query['sampled_us']+phase):raise ValueError('Binding inputs differ from scan')
                    if frame['board_flags']!=query['adc_ok'] or frame['circuit_adc7_code']!=query['raw'][7]:raise ValueError('ADC transport debug differs')
                    same_tree(frame['circuit_adc_reference_v'],query['adc_reference_v'],'ADC reference debug')
                    if frame['circuit_ratiometric']!=(obs['calibration_basis']=='ratiometric') or frame['strategy_code']!=obs['strategy']:raise ValueError('Controller configuration differs')
                    faults=frame['controller_faults'];flags=frame['flags'];stat['rows']+=1
                    if faults and flags&3072!=3072:raise ValueError('Fault did not cut both proposals')
                    if frame['worker_observation']['physical_command_mask']!=0:raise ValueError('Unexpected physical command')
                    if frame['circuit_fault_acknowledged'] and (not frame['flex_fuel']['pending_fault'] or frame['flex_fuel']['control_ok'] or flags&3072!=3072):raise ValueError('ACK without completed invalid/cut control')
                    stat['faulted']+=bool(faults);stat['ready']+=not bool(faults);stat['acknowledgements']+=frame['circuit_fault_acknowledged']
                    stat['fault_masks'][str(faults)]=stat['fault_masks'].get(str(faults),0)+1
                    if phase==0:
                        phase0.append(frame)
                        stat['phase0'].append(dict(control_us=int(frame['control_us']),faults=faults,flags=flags,
                            measured_sensor_v=frame['inputs']['sensor_v'],map_kpa=frame['inputs']['map_kpa'],
                            map_error_kpa=frame['circuit_map_error_kpa'],pulse_ms=frame['proposals']['pulse_ms']))
                        if int(frame['control_us'])>=86000 and frame['circuit_map_error_kpa'] is not None:map_errors.append(frame['circuit_map_error_kpa'])
                    # The sampled analogue reference is an independent debug
                    # observation. Every other native observation must compare.
                    canonical={k:v for k,v in frame.items() if k!='circuit_adc_reference_v'}
                    h.update(json.dumps(canonical,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n')
            expected={(n,phase/10) for n in range(1,len(queries)+1) for phase in range(10)}
            if seen!=expected or stat['rows']!=obs['rows']:raise ValueError('Missing controller phase/query')
            same_tree(obs['final'],frame,'Final replay record')
            if stat['faulted']!=obs['faulted_rows'] or len(map_errors)!=obs['settled_valid_map_rows']:raise ValueError('Replay counters differ')
            same_tree(obs['settled_valid_map_error_kpa'],[min(map_errors),max(map_errors)] if map_errors else None,'Settled MAP errors')
            stat['canonical_sha256']=h.hexdigest();stat['settled_map_error_kpa']=[min(map_errors),max(map_errors)] if map_errors else None
            log=path.with_name(path.name.removesuffix('.jsonl.gz'))/'engine.msl'
            verify_msl(log,phase0);retain(log)
            row['replays'][label]=stat;traces+=1
            threshold=f"{obs['rising_fraction']}-{obs['falling_fraction']}"
            if threshold not in row['edge_inputs']:
                declared_edges=threshold_edges[(obs['rising_fraction'],obs['falling_fraction'])]
                edges=stimulus(root,name,obs['rising_fraction'],obs['falling_fraction'],expected_stimulus(declared_edges,queries))
                retain(member(root,f'{name}/gpio-{threshold}.stimulus.txt'))
                row['edge_inputs'][threshold]={str(p):[(math.floor(t+p/10),level) for t,level in edges] for p in range(10)}
        row['full_replay_matrix']=True
        row['sampling_derived_from_raw']=True;row['msl_columns_checked']=229
        if name=='baseline':baseline=queries
        cases[name]=row
        print(json.dumps(dict(matrix=root.name,case=name,raw_rows=row['raw_rows'],replays=len(row['replays']),ripple_acquisition_samples=row['ripple_acquisition_samples'])),flush=True)
    if baseline:
        for row in cases.values():
            if [q['sampled_us'] for q in row['queries']]!=[q['sampled_us'] for q in baseline]:continue
            row['relative_to_matched_baseline']={str(ch):dict(
                max_pin_delta_v=max(abs(q['samples'][ch]['pin_v']-b['samples'][ch]['pin_v']) for q,b in zip(row['queries'],baseline)),
                max_reference_delta_v=max(abs(q['samples'][ch]['reference_v']-b['samples'][ch]['reference_v']) for q,b in zip(row['queries'],baseline)),
                differing_codes=sum(q['raw'][ch]!=b['raw'][ch] for q,b in zip(row['queries'],baseline))) for ch in range(8)}
    if digest(Path(__file__))!=AUDITOR_SHA256:raise ValueError('Analyzer source changed during audit')
    return dict(root=str(root),complete=summary['complete'],original_matrix_status=summary['status'],
        original_planned_cases=summary['selected_case_names'],audited_case_names=list(cases),
        input_sha256=inputs,analyzer_sha256=AUDITOR_SHA256,
        recovered_bound_sources=recovered,
        interpretation='Conditional point-conversion observations; reference span is not a physical SAR error bound',
        replays=traces,cases=cases,physical_qualification=False)


def compare(a,b):
    if set(a['cases'])!=set(b['cases']):raise ValueError('Matrix case sets differ')
    result={}
    for name,x in a['cases'].items():
        y=b['cases'][name]
        if {k:v for k,v in x['scenario'].items() if k not in ('max_step_us','solver','minimum_break_s')}!={k:v for k,v in y['scenario'].items() if k not in ('max_step_us','solver','minimum_break_s')}:
            raise ValueError('Physical/model/timing case declarations differ')
        if len(x['queries'])!=len(y['queries']):raise ValueError('Query count differs')
        differences=[dict(query=n,channel=ch,coarse=u['raw'][ch],fine=v['raw'][ch])
            for n,(u,v) in enumerate(zip(x['queries'],y['queries'])) for ch in range(8) if u['raw'][ch]!=v['raw'][ch]]
        query_differences=[n for n,(u,v) in enumerate(zip(x['queries'],y['queries']))
            if any(u[k]!=v[k] for k in ('control_us','sampled_us','adc_ok'))]
        edge_differences=[dict(threshold=t,phase=p) for t in x['edge_inputs'] for p in x['edge_inputs'][t] if x['edge_inputs'][t][p]!=y['edge_inputs'][t][p]]
        record_differences=[key for key,z in x['replays'].items() if z['canonical_sha256']!=y['replays'][key]['canonical_sha256']]
        if not differences and not edge_differences and not query_differences and record_differences:
            raise ValueError('Deterministic native records differ despite identical declared discrete inputs')
        result[name]=dict(identical_discrete_inputs=not(differences or edge_differences or query_differences),raw_code_differences=differences,
            query_timing_or_transport_differences=query_differences,
            quantized_edge_differences=edge_differences,native_record_differences=record_differences)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--matrix',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inspect-completed-cases-of-failed-matrix',action='store_true',help='Exploratory only; output remains explicitly incomplete')
    p.add_argument('--binding-source',type=Path,help='Exact hash-bound A5 contract when omitted from an older frozen source tree')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'analyzer.py').write_bytes(AUDITOR_SOURCE)
    reports=[]
    for root in args.matrix:
        report=audit(root.resolve(),args.inspect_completed_cases_of_failed_matrix,args.binding_source);reports.append(report)
        (args.output/(root.name+'.json')).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    comparisons=[dict(coarse=reports[0]['root'],fine=r['root'],cases=compare(reports[0],r)) for r in reports[1:]]
    (args.output/'comparison.json').write_text(json.dumps(comparisons,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(complete=all(r['complete'] for r in reports),matrices=len(reports),physical_qualification=False)))
