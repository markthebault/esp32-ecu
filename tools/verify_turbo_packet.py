"""Verify a frozen turbo study packet and replay its consumed-edge snapshots.

No archived code or native executable is executed. Hash validation and trace
replay do not reproduce the gas solver or establish physical qualification.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe payload name')
    return path.as_posix()


def replay(result,traces,edges):
    high=[False]*10;last=-1;boost_count=0
    for index,edge in enumerate(edges,1):
        stamp,channel,level=edge['time_us'],edge['ch'],edge['high']
        assert edge['sequence']==index and type(stamp) is int and last<=stamp<=round(result['duration_s']*1e6)
        assert type(channel) is int and 0<=channel<10 and channel!=8
        assert type(level) is bool and high[channel]!=level
        high[channel]=level;last=stamp
        boost_count+=channel==9 and edge['cause']=='dispatcher'
    assert len(edges)==result['edges'] and boost_count==result['boost_edges'] and not any(high)
    high=[False]*10;index=coil_edges=dispatcher_edges=0
    for row in traces:
        count=row['edges_consumed'];stamp=row['time_us']
        assert type(count) is int and index<=count<=len(edges)
        while index<count:
            edge=edges[index];assert edge['time_us']<=stamp
            high[edge['ch']]=edge['high'];coil_edges+=edge['ch']==9
            dispatcher_edges+=edge['ch']==9 and edge['cause']=='dispatcher';index+=1
        assert index==len(edges) or edges[index]['time_us']>stamp
        assert row['boost_dispatcher_edges_consumed']==dispatcher_edges
        coil=row['valve']['coil']
        assert coil['gpio_high']==high[9] and coil['edges']==coil_edges
        assert abs(coil['electrical_residual_j'])<1e-8
        state=row['dispatcher']
        if result['controller']=='ours':
            assert state['virtual_high']==high[9] and state['physical_policy_enabled'] is False and state['physical_command_high'] is False
        else:
            assert bool(state['pin_high'])==high[9]
            adcs=row['input_adc_counts'];sample=row['sensor_input']
            assert set(adcs)=={'map','tps','clt','iat','battery','wideband'}
            assert all(type(value) is int and 0<=value<=1023 for value in adcs.values())
            m,t,c,i,b,a=[float(format(value,'.12g')) for value in
                       (sample['map_kpa'],sample['tps_pct'],sample['clt_c'],sample['iat_c'],sample['battery_v'],sample['lambda']*14.7)]
            raw=(m/400*1023,t/100*1023,(c+40)*33/8,(i+40)*33/8,b*10/245*1024,(a*10-80)*33/5)
            expected=dict(zip(('map','tps','clt','iat','battery','wideband'),[min(1023,max(0,math.floor(value+.5))) for value in raw]))
            assert adcs==expected,('ADC conversion',stamp,adcs,expected)
    before=result['before_halt']
    while index<before['edges_consumed']:
        edge=edges[index];high[edge['ch']]=edge['high'];index+=1
    assert high==before['high']
    assert all(edge['time_us']==round(result['duration_s']*1e6) and edge['cause'] in ('fixture_halt','cut:simulation_end') and edge['high'] is False for edge in edges[index:])
    ledger=result['before_halt']['ledger']
    assert abs(ledger['coupled_mass_residual_kg'])<1e-9 and abs(ledger['coupled_energy_residual_j'])<.02
    assert result['physical_execution'] is False and result['completed'] is True
    if result['stimulus']['scenario']=='charged_map_rail':
        stamp=result['stimulus']['charged_fault_start_us']
        assert type(stamp) is int and stamp>=6000000 and result['stimulus']['charged_channels_at_start']
        if result['controller']=='ours':
            assert any(abs(row['time_s']-stamp/1e6)<1e-9 and row['energy_j']>.002 for row in before['cut_discharges'])
    if result['stimulus']['cut_kpa']==140:
        assert max(row['gas']['map_kpa'] for row in traces)>140
        assert result['stimulus']['map_sensor_override_kpa'] is None
        if result['controller']=='ours':assert int(before['control']['boost_control']['overboost_events'])>0
        else:assert any(row['control']['boost_control']['boost_cut'] for row in traces)
    return len(traces)


def verify(root,repo=None):
    root=Path(root)
    manifest=json.loads((root/'artifact-manifest.json').read_text())
    names={item['path'] for item in manifest['files']}
    assert len(names)==len(manifest['files'])
    assert not any(path.is_symlink() for path in root.rglob('*'))
    assert {str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()}==names|{'artifact-manifest.json'}
    for item in manifest['files']:
        content=(root/safe(item['path'])).read_bytes()
        assert len(content)==item['bytes'] and sha(content)==item['sha256'],item['path']
    payloads={};archive_count=0
    for archive in manifest['archives']:
        rows={item['path']:item for item in archive['payloads']}
        assert len(rows)==len(archive['payloads'])
        with tarfile.open(root/safe(archive['path']),'r:*') as source:
            members=source.getmembers()
            assert len(members)==len(rows) and {member.name for member in members}==set(rows)
            for member in members:
                assert member.isfile() and safe(member.name)==member.name
                content=source.extractfile(member).read();item=rows[member.name]
                assert len(content)==item['bytes'] and sha(content)==item['sha256'],member.name
                if archive['role']=='study':payloads[member.name]=content
        archive_count+=1
    summary=json.loads((root/'summary.json').read_text())
    assert summary['run_invariants_passed'] and summary['independent_review_accepted'] and not summary['physical_execution'] and not summary['full_speeduino_parity']
    snapshots=0
    if summary['fresh_verification_sha256'] is not None:
        assert sha(payloads['study/verification-result.json'])==summary['fresh_verification_sha256']
    for name in summary['case_names']:
        prefix='cases/'+safe(name)+'/'
        result=json.loads(payloads[prefix+'result.json'])
        traces=[json.loads(line) for line in payloads[prefix+'trace.jsonl'].decode().splitlines()]
        edges=[json.loads(line) for line in payloads[prefix+'edges.jsonl'].decode().splitlines()]
        snapshots+=replay(result,traces,edges)
    if repo:
        for name,value in summary['source_hashes'].items():
            assert sha((Path(repo)/safe(name)).read_bytes())==value,name
    return dict(passed=True,archives=archive_count,payloads=sum(len(a['payloads']) for a in manifest['archives']),
                cases=len(summary['case_names']),snapshots=snapshots,current_sources_checked=repo is not None,
                qualification=__doc__.strip())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path)
    args=parser.parse_args();print(json.dumps(verify(Path(__file__).resolve().parent,args.repo),indent=2))
