#!/usr/bin/env python3
"""Bind actual application's write/burn/CRC/MSQ to frozen production reference."""
from pathlib import Path
import hashlib,json,struct,subprocess,xml.etree.ElementTree as ET,zlib
BASE=Path(__file__).resolve().parent;PROJECT=BASE.parents[3];APP=BASE/'reference-public-003'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
analysis=json.loads((BASE/'independent-public-stream-analysis.json').read_text());assert not analysis['issues']
native=json.loads((APP/'native-build-manifest.json').read_text());session=json.loads((APP/'session.json').read_text())
cache={};before=None;writes=[];burns=[];crc_checks=[]
for index,t in enumerate(analysis['transactions']):
    request=bytes.fromhex(t['request_hex']);answer=bytes.fromhex(t['response_hex'])
    if t['raw']:continue
    if request[:1]==b'p'and request[2]==2:
        node,page,offset,count=struct.unpack('<BBHH',request[1:]);assert answer[0]==0 and len(answer)==count+1
        for n,value in enumerate(answer[1:]):cache[offset+n]=value
        if len(cache)==288 and before is None:before=bytes(cache[n]for n in range(288))
    elif request[:1]==b'M':
        node,page,offset,count=struct.unpack('<BBHH',request[1:7]);assert page==2 and answer==b'\0'and len(request)==7+count
        previous=bytes(cache[offset+n]for n in range(count));new=request[7:]
        writes.append(dict(transaction=index,request_line=t['request_line'],response_line=t['response_line'],page=page,offset=offset,count=count,before_hex=previous.hex(),after_hex=new.hex(),reply_hex=answer.hex(),request_hex=request.hex()))
        for n,value in enumerate(new):cache[offset+n]=value
    elif request[:1]==b'b':
        assert request==b'b\0\2'and answer==b'\4';burns.append(dict(transaction=index,request_line=t['request_line'],response_line=t['response_line'],page=2,reply_hex=answer.hex()))
    elif request==b'd\0\2':
        wire=int.from_bytes(answer[1:],'big');assert answer[0]==0 and len(answer)==5
        if len(cache)==288:
            computed=zlib.crc32(bytes(cache[n]for n in range(288)));assert computed==wire
            crc_checks.append(dict(transaction=index,request_line=t['request_line'],response_line=t['response_line'],wire_hex=f'{wire:08x}',computed_hex=f'{computed:08x}',after_burn=bool(burns)))
assert before is not None and len(writes)==1 and len(burns)==1
after=bytes(cache[n]for n in range(288));diff=[dict(offset=n,before=a,after=b)for n,(a,b)in enumerate(zip(before,after))if a!=b]
assert diff==[dict(offset=240,before=85,after=86)]
assert any(c['after_burn']and c['wire_hex']=='be04ef33'for c in crc_checks)
root=ET.fromstring((APP/'reference-app-edited.msq').read_bytes());constants={n.attrib['name']:n for n in root.iter()if'name'in n.attrib}
values=lambda name:[float(x)for x in(constants[name].text or'').split()]
assert(constants['algorithm'].text or'').strip()=='"MAP"'
ve=values('veTable');rpm=values('rpmBins');load=values('fuelLoadBins');assert len(ve)==256 and len(rpm)==len(load)==16
def encoded(values,scale):
    result=[]
    for value in values:
        raw=value/scale;assert raw.is_integer()and 0<=raw<=255;result.append(int(raw))
    return bytes(result)
msq_page=encoded(ve,1)+encoded(rpm,100)+encoded(load,2);assert msq_page==after
version=next(n for n in root.iter()if n.tag.rsplit('}',1)[-1]=='versionInfo');assert version.attrib['signature']=='speeduino 202504-dev'
assert zlib.crc32(msq_page)==0xbe04ef33
debug=(APP/'user/TunerStudioProjects/TunerStudioAppDebug.txt').read_text();closure=json.loads((APP/'native/closure.json').read_text());assert closure['returncode']==0 and closure['failure']==''and closure['physical_interface']is False
current_sources={name:dict(expected=digest,current=sha(PROJECT/name),matches=digest==sha(PROJECT/name))for name,digest in session['sources'].items()};assert all(r['matches']for r in current_sources.values())
input_checks={name:dict(expected=digest,current=sha(Path(name)),matches=digest==sha(Path(name)))for name,digest in native['locked_original_input_hashes'].items()};assert all(r['matches']for r in input_checks.values())
assert native['binary_sha256']==sha(PROJECT/'.cache/engine/speeduino-serial-sim/speeduino-serial-sim')
native_tx=sum(len(bytes.fromhex(line.split()[2]))for line in(APP/'native/native-events.log').read_text().splitlines()if line.startswith('tx '))
assert native_tx==json.loads((BASE/'final-analyzer-public-result.json').read_text())['bytes']['TX']
pid_status=subprocess.run(['ps','-p',','.join(str(session[name])for name in('java_pid','xvfb_pid','native_pid')),'-o','pid=,stat=,comm='],capture_output=True,text=True)
assert not pid_status.stdout.strip()
report=dict(identity=version.attrib['signature'],application_jar_sha256=session['application_sha256'],same_application_as_own009=session['application_sha256']=='3ebafb867fef3722816e768879501845904f81bc5e13249c77d170e9adf61cf8',pinned_ini_sha256=sha(PROJECT.parent/'speeduino/reference/speeduino.ini'),application_ini_sha256=sha(APP/'SPEEDUINO-PRODUCTION/projectCfg/mainController.ini'),ini_matches_pinned=(APP/'SPEEDUINO-PRODUCTION/projectCfg/mainController.ini').read_bytes()==(PROJECT.parent/'speeduino/reference/speeduino.ini').read_bytes(),application_msq_sha256=sha(APP/'reference-app-edited.msq'),application_msq_bytes=(APP/'reference-app-edited.msq').stat().st_size,changed_bytes=diff,write_transactions=writes,burn_transactions=burns,controller_crc_checks=crc_checks,msq_complete_page_bytes=288,msq_page_equals_controller_reconstruction=True,msq_page_crc32='be04ef33',initial_page_crc32=f'{zlib.crc32(before):08x}',msq_axis_scales=dict(rpm=100,fuel_load=2),sources_match_launch=current_sources,locked_original_inputs_verified=len(input_checks),native_build_binary_sha256=native['binary_sha256'],native_TX_bytes_equal_bridge_TX=native_tx,unsupported_warnings=debug.count('Unsupported Controller Firmware'),app_debug_burn_confirmed='burned page 2'in debug and'CRC matches for page 2:xBE x04 xEF x33'in debug,closure=closure,recorded_stats_are_final_totals=False,recorded_stats_meaning='Last explicitly requested runtime observation; final byte totals come from complete wire/native-event captures.',owned_processes_remaining=pid_status.stdout.strip(),scope='Unmodified actual TunerStudio + genuine pinned Speeduino stopped-engine native serial read/edit/burn positive control. Fake EEPROM only; no physical persistence, engine, target USB or running-plant claim.')
(BASE/'public-application-write-burn-review.json').write_text(json.dumps(report,indent=2)+'\n');(BASE/'launch-input-hash-validation.json').write_text(json.dumps(input_checks,indent=2)+'\n');(BASE/'reference-page2-before.bin').write_bytes(before);(BASE/'reference-page2-after.bin').write_bytes(after);print(json.dumps(report,indent=2))
