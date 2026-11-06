#!/usr/bin/env python3
"""Independent review probes. Run only with a copied source root."""
import copy, csv, io, json, struct, sys, tempfile
from pathlib import Path

F = Path(sys.argv[1]).resolve()
O = Path(__file__).resolve().parent
sys.path.insert(0, str(F / 'tools'))
from engine_runtime import EngineRuntime, EngineStore
from target_runtime import TargetRuntime
from engine_protocol import DEFAULT, pages, decode_pages, Session, live_block, SIGNATURE
from engine_msq import export_msq, import_msq
from engine_observability import EngineRecorder, encoded
from flex_config import DEFAULT as FLEX_DEFAULT, OFFSETS, TIMES
from flex_stimulus import FlexStimulus

checks = 0
details = {}
def require(v, message):
    global checks
    checks += 1
    if not v: raise AssertionError(message)
def rejected(fn, message):
    try: fn()
    except ValueError: require(True, message); return
    require(False, message)
def configured():
    t = copy.deepcopy(DEFAULT)
    t['flex_fuel']['correction'].update(enabled=True, temperature_enabled=True,
        fuel_pct=[150]*6, spark_deg=[5]*6, temperature_pct=[80]*6)
    return t
def edges(r, start=920000, n=8):
    r.flex_edge(start, True)
    for k in range(1, n+1):
        r.flex_edge(start+k*10000-3000, False)
        r.flex_edge(start+k*10000, True)
    return start+n*10000
def step(r, t=1000000, **kw):
    return r.step(dict(rpm=2000, synced=True, phase_synced=True, **kw), t, use_decoder=False)

for cls in (EngineRuntime, TargetRuntime):
    r = cls(configured())
    try:
        edges(r); first = step(r)
        require(first['flex_fuel']['raw_capture_qualified'], cls.__name__+' ready')
        r.tune['revision'] = 913  # Deliberately mutate only Python metadata.
        require(step(r,1000001)['flex_fuel']['configuration_revision'] == 1, 'producer revision retained')
        r.flex_edge(1000002, True)
        edges(r,1020000)
        rejected(lambda:step(r,1100000,use_flex_capture=True,ethanol_pct=50,ethanol_qualified=True), 'malformed raw/scalar mix')
        f = step(r,1100001)['flex_fuel']
        require(f['pending_fault'] and not f['raw_capture_qualified'] and not f['control_ok'], 'error did not acknowledge')
        generation = f['fault_generation']
        completed = step(r,1100002)
        f = completed['flex_fuel']
        require(not f['pending_fault'] and f['raw_capture_qualified'] and f['acknowledged_generation']==generation, 'completed invalid control acknowledged')
        newer = configured(); newer['revision']=42; newer['flex_fuel']['correction']['fuel_pct']=[123]*6
        r.configure(newer)
        f=step(r,1100003)['flex_fuel']
        require(f['configuration_revision']==42 and f['pending_fault'] and not f['raw_capture_qualified'] and f['config_epoch']=='2', 'same-calibration new-revision invalidates')
        require(f['last_fault']=='configuration_changed', 'context fault visible')
        step(r,1100004)
        edges(r,1120000,7)
        require(not step(r,1190000)['flex_fuel']['raw_capture_qualified'], 'N-1 incomplete')
        r.flex_edge(1197000,False);r.flex_edge(1200000,True)
        f=step(r,1200000)['flex_fuel']
        require(f['raw_capture_qualified'] and f['fuel_pct']==123 and f['configuration_revision']==42, 'N coherent reacquisition')
        before=r.tune
        invalid=copy.deepcopy(newer);invalid['flex_fuel']['capture']['cycles']=256
        rejected(lambda:r.configure(invalid), 'invalid configure rejected')
        require(r.tune==before and step(r,1200001)['flex_fuel']['raw_capture_qualified'], 'failed configure retains source context')
        details[cls.__name__]={'pending_generation':generation,'final':f}
    finally:r.close()

with tempfile.TemporaryDirectory(dir=O) as d:
    store=EngineStore(Path(d)/'tune.json');a=b=None
    try:
        a,b=Session(store),Session(store)
        request=lambda offset,data:b'M'+struct.pack('<BBHH',0,1,offset,len(data))+data
        original=bytes(a.buffers[1]); bad=bytearray(original[7952:7972]);bad[-1]=1
        require(a.command(request(7952,bad))==b'\x84', 'cross-boundary reserved chunk rejected')
        require(bytes(a.buffers[1])==original and not a.dirty,'chunk failure atomic')
        require(a.command(request(OFFSETS['filter_ms'],struct.pack('<f',125.5)))==b'\0','stage fractional filter')
        require(a.command(request(OFFSETS['enabled'],struct.pack('<I',1)))==b'\0','stage enable')
        require(a.command(b'b\0\1')==b'\4','atomic flex burn')
        require(store.tune['revision']==2 and store.tune['flex_fuel']['capture']['filter_ms']==125.5 and store.tune['flex_fuel']['correction']['enabled'],'burn activated complete config')
        require(store.runtime.tune['revision']==2 and store.runtime.data()['tune_revision']!=1,'new runtime does not retain old sample')
        require(b.command(request(OFFSETS['filter_ms'],struct.pack('<f',99)))==b'\x84','stale session cannot stage')
        stale=copy.deepcopy(DEFAULT);stale['flex_fuel']['capture']['filter_ms']=75
        require(store.save(encoded(stale))[0]==409,'JSON CAS retains revision')
        require(store.tune['flex_fuel']['capture']['filter_ms']==125.5,'CAS failure retains calibration')
        require(a.buffers[1][268:272]==struct.pack('<I',1),'wire origin retained')
        data=pages(store.tune)[1]
        for offset in [OFFSETS['enabled'],OFFSETS['input_confirmed'],OFFSETS['cycles']]:
            invalid=bytearray(data);struct.pack_into('<I',invalid,offset,0x100)
            rejected(lambda:decode_pages({1:invalid},DEFAULT),'full-width malformed rejects')
        for pos in (7968,8191):
            invalid=bytearray(data);invalid[pos]=1
            rejected(lambda:decode_pages({1:invalid},DEFAULT),'tail rejects')
        text=export_msq(store.tune)
        require(pages(import_msq(text,base_revision=2))==pages(store.tune),'MSQ full page exact')
        # Deleting a current field, lying about identity, duplicates and foreign constants.
        import xml.etree.ElementTree as ET
        from engine_msq import tag
        root=ET.fromstring(text);page=next(root.iter(tag('page')))
        flexnode=next(n for n in page if n.get('name')=='flex_filter_ms');page.remove(flexnode)
        rejected(lambda:import_msq(ET.tostring(root)), '010 missing field rejects')
        rejected(lambda:import_msq(text.replace(SIGNATURE.decode(),'ESP32ECU DEV 009 INHIBITED')), '009 with 010 fields rejects')
        root=ET.fromstring(text);page=next(root.iter(tag('page')));page.append(copy.deepcopy(next(n for n in page if n.get('name')=='flex_filter_ms')))
        rejected(lambda:import_msq(ET.tostring(root)), 'duplicate flex field rejects')
        rejected(lambda:import_msq(text.replace(SIGNATURE.decode(),'Speeduino')), 'foreign signature rejects')
        rejected(lambda:import_msq('<!DOCTYPE x>'+text), 'DTD rejects')
        # Schema8 migration with distinctive tables retains the whole secondary object.
        old=json.loads((F/'config/engine/defaults-v8.json').read_text());old['revision']=77
        for i,kind in enumerate(('fuel','spark')):
            rule=old['secondary_tables'][kind];rule.update(mode='conditional',condition='ethanol_pct',threshold=40+i,hysteresis=2+i,input_channel=i,active_high=not bool(i))
            rule['map']['cells']=[(80+i if kind=='fuel' else 7)+n/1024 for n in range(256)]
        path=Path(d)/'old.json';body=encoded(old);path.write_bytes(body)
        migrated=EngineStore(path)
        try:
            require(migrated.storage_ok and migrated.tune['secondary_tables']==old['secondary_tables'],'schema8 all secondary values preserved')
            require(migrated.tune['flex_fuel']==FLEX_DEFAULT and path.read_bytes()==body and migrated.tune['revision']==77,'legacy neutral bytes/revision retained')
        finally:migrated.runtime.close();migrated.data_recorder.close()
    finally:
        if a:a.close()
        if b:b.close()
        store.runtime.close();store.data_recorder.close()

r=EngineRuntime(configured());d=EngineRecorder()
try:
    edges(r);step(r);s=r.data();s['flex_fuel'].update(raw_edges='18446744073709551615',fault_generation='9007199254740993',acknowledged_generation='9007199254740993',config_epoch='18446744073709551615')
    require(d.bridge.data_validate(encoded(s))==1,'exact large U64 metadata accepted')
    require(d.command(dict(action='start',period_ms=20,duration_s=20),1000000)==200,'start retained log')
    for n in range(300):
        row=copy.deepcopy(s);row['sequence']=str(n+1);row['control_us']=str(1000000+n*20000);row['sampled_us']=row['control_us']
        require(d.append(row,int(row['control_us'])),'append row')
    require(d.command(dict(action='stop',log_id=1),7000000)==200,'stop retained log')
    h=d.header();require(h['capacity']==128 and h['retained']==128 and h['overwritten']==172 and h['first_sequence']==173 and h['total']==300,'128-row loss counts')
    records=[];after=0;pages_out=[]
    while after<300:
        p=d.page(1,after);pages_out.append(p)
        if after==0:require((p['gap_first'],p['gap_last'])==(1,172),'explicit lost-row range')
        records.extend(p['records']);require(p['next_after']>after,'cursor progresses');after=p['next_after']
    require([q['row_sequence']for q in records]==list(range(173,301)),'retained contiguous rows')
    for k in ['raw_edges','fault_generation','acknowledged_generation','config_epoch']:
        require(all(q['sample']['flex_fuel'][k]==s['flex_fuel'][k] for q in records),'record exact U64 '+k)
    msl=list(csv.reader(io.StringIO(d.msl(1)),delimiter='\t'));require(len(msl[2])==229 and len(msl[3])==229 and all(len(q)==229 for q in msl[4:]),'229 columns consistent')
    exported=dict(zip(msl[2],msl[4]));require(exported['FlexRawEdges']=='18446744073709551615' and exported['FlexFaultGeneration']=='9007199254740993','MSL exact U64')
    (O/'host-diagnostic-fixtures.json').write_text(json.dumps({'sample':s,'header':dict(h,boot_id='0'*32),'pages':[dict(p,boot_id='0'*32)for p in pages_out]},indent=2)+'\n')
    details['recorder']={'header':h,'pages':len(pages_out),'columns':len(msl[2])}
    for schema in (1,2,3,4):rejected(lambda:d.frame(s,b'k'*16,b'n'*32,1,1,schema=schema),'raw corrected suppresses radio')
    # Scalar ETH dependency also suppresses legacy transport; Off has no such dependency.
    select=copy.deepcopy(DEFAULT);select['secondary_tables']['fuel'].update(mode='conditional',condition='ethanol_pct',threshold=40)
    r.configure(select);step(r,7100000,ethanol_pct=50,ethanol_qualified=True);scalar=r.data()
    for schema in (1,2,3,4):rejected(lambda:d.frame(scalar,b'k'*16,b'n'*32,1,1,schema=schema),'ETH dependency suppresses radio')
    r.configure(copy.deepcopy(DEFAULT));step(r,7200000);off=r.data()
    for schema in (1,2,3,4):require(len(d.frame(off,b'k'*16,b'n'*32,1,1,schema=schema)) in (232,250),'neutral Off legacy radio supported')
    # Runtime JSON parser mutations for a matching browser differential probe.
    mutations={}
    for name,changes in {
        'negative_calibration':{'capture_calibration':dict(s['flex_fuel']['capture_calibration'],low_hz=-50)},
        'fractional_read_age':{'read_age_ms':0.5},
        'control_allowed_without_value':{'value_qualified':False,'raw_capture_qualified':False,'capture_valid':False,'sample_value_valid':False,'corrections_enabled':False,'corrections_valid':False,'control_ok':True},
        'target_unconfirmed':{'source':'target_capture','source_code':1,'input_confirmed':False},
        'bad_raw_counter':{'raw_edges':'18446744073709551616'},
        'required_false_enabled':{'required':False},
    }.items():
        bad=copy.deepcopy(s);bad['flex_fuel'].update(changes);mutations[name]={'flex':bad['flex_fuel'],'native_accepted':bool(d.bridge.data_validate(encoded(bad)))}
        require(not mutations[name]['native_accepted'],'native rejects '+name)
    (O/'host-diagnostic-mutations.json').write_text(json.dumps(mutations,indent=2)+'\n')
finally:r.close();d.close()

for bad in (None, True, '2', -1, float('inf')):
    rejected(lambda:FlexStimulus(dict(frequency_hz=100,low_pulse_us=3000,dropout_at_s=bad)),'invalid dropout clean ValueError')

print(json.dumps({'passed':True,'checks':checks,'details':details},indent=2))
