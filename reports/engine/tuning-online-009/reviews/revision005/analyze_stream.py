#!/usr/bin/env python3
"""Independent stream reassembly of raw-F discovery and framed ECU traffic."""
from collections import Counter,deque
from pathlib import Path
import argparse,hashlib,json,re,struct,zlib

def analyze(path,page_sizes=None):
    buffers={'RX':bytearray(),'TX':bytearray()};pending=deque();issues=[];transactions=[]
    requests=[];replies=[];pages={};expected_crcs={};page_checks=[];runtime=bytearray(139);runtime_seen=set();runtime_samples=[]
    def complete_request(payload,raw,line):
        event=dict(payload=payload,raw=raw,line=line);pending.append(event);requests.append(event)
    def complete_reply(payload,raw,line):
        if not pending:
            issues.append(dict(line=line,issue='reply without completed request'));return
        req=pending.popleft()
        if req['raw']!=raw:issues.append(dict(line=line,issue='reply mode differs from request'))
        cmd=req['payload'];record=dict(request_line=req['line'],response_line=line,request_hex=cmd.hex(),response_hex=payload.hex(),raw=raw)
        transactions.append(record);replies.append(payload)
        if raw:
            if payload!=b'002':issues.append(dict(line=line,issue='wrong raw-F response'))
            return
        if not payload:issues.append(dict(line=line,issue='empty reply'));return
        if payload[0]not in(0,4):return
        if cmd[:1]in(b'p',b'r')and len(cmd)==7:
            node,page,offset,count=struct.unpack('<BBHH',cmd[1:])
            if len(payload)!=count+1:issues.append(dict(line=line,issue='data size differs from requested count'));return
            if cmd[:1]==b'p':
                target=pages.setdefault(page,{})
                for i,value in enumerate(payload[1:]):target[offset+i]=value
                size=(page_sizes or{}).get(page)
                if size and len(target)==size and page in expected_crcs:
                    actual=zlib.crc32(bytes(target[i]for i in range(size)))
                    check=dict(page=page,wire_crc=expected_crcs[page],page_crc=actual,matches=actual==expected_crcs[page],line=line)
                    if not any(c['page']==page and c['wire_crc']==check['wire_crc']for c in page_checks):page_checks.append(check)
            elif page==0x30 and offset+count<=139:
                if offset==0:runtime_seen.clear()
                runtime[offset:offset+count]=payload[1:];runtime_seen.update(range(offset,offset+count))
                if len(runtime_seen)==139:
                    runtime_samples.append(dict(rpm=struct.unpack_from('<H',runtime,14)[0],map_kpa=struct.unpack_from('<H',runtime,4)[0],iat_c=runtime[6]-40,clt_c=runtime[7]-40))
        elif cmd[:1]==b'd'and len(cmd)==3 and len(payload)==5:
            page=cmd[2];expected_crcs[page]=int.from_bytes(payload[1:],'big')
            size=(page_sizes or{}).get(page);target=pages.get(page,{})
            if size and len(target)==size:
                actual=zlib.crc32(bytes(target[i]for i in range(size)))
                page_checks.append(dict(page=page,wire_crc=expected_crcs[page],page_crc=actual,matches=actual==expected_crcs[page],line=line))
        elif cmd[:1]==b'M'and len(cmd)>=7:
            node,page,offset,count=struct.unpack('<BBHH',cmd[1:7])
            if len(cmd)!=7+count:issues.append(dict(line=line,issue='M declared count differs from data length'))
            target=pages.setdefault(page,{})
            for i,value in enumerate(cmd[7:]):target[offset+i]=value
            expected_crcs.pop(page,None)
    for line_no,line in enumerate(path.read_text().splitlines(),1):
        match=re.fullmatch(r'(RX|TX) (\d+) ([0-9a-fA-F]+)',line)
        if not match:continue
        direction,declared,hex_data=match.groups();body=bytes.fromhex(hex_data)
        if len(body)!=int(declared):issues.append(dict(line=line_no,issue='truncated line',declared=int(declared),actual=len(body)))
        buffer=buffers[direction];buffer.extend(body)
        while buffer:
            if direction=='RX'and buffer[0]==0xf0:
                del buffer[0];continue
            if direction=='RX'and buffer[0]==ord('F'):
                del buffer[0];complete_request(b'F',True,line_no);continue
            if direction=='TX'and pending and pending[0]['raw']:
                if len(buffer)<3:break
                payload=bytes(buffer[:3]);del buffer[:3];complete_reply(payload,True,line_no);continue
            if len(buffer)<2:break
            size=int.from_bytes(buffer[:2],'big')
            if not 0<size<65536:issues.append(dict(line=line_no,issue='invalid frame size'));break
            if len(buffer)<size+6:break
            payload=bytes(buffer[2:2+size]);crc=int.from_bytes(buffer[2+size:6+size],'big');del buffer[:size+6]
            if zlib.crc32(payload)!=crc:issues.append(dict(line=line_no,issue='bad frame CRC'))
            if direction=='RX':complete_request(payload,False,line_no)
            else:complete_reply(payload,False,line_no)
    if buffers['RX']or buffers['TX']:issues.append(dict(issue='trailing partial stream',RX=len(buffers['RX']),TX=len(buffers['TX'])))
    if pending:issues.append(dict(issue='requests without response',count=len(pending)))
    return dict(wire_path=str(path),wire_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),request_count=len(requests),response_count=len(replies),commands=dict(Counter(chr(r['payload'][0])for r in requests if r['payload'])),response_statuses=dict(Counter(hex(p[0])for r,p in zip(requests,replies)if not r['raw']and p)),issues=issues,q_responses=sorted({p[1:].decode('ascii',errors='replace')for r,p in zip(requests,replies)if r['payload']==b'Q'}),page_coverage={p:len(v)for p,v in pages.items()},page_crc_checks=page_checks,runtime_sample_count=len(runtime_samples),runtime_sample_values={name:sorted({r[name]for r in runtime_samples})for name in('rpm','map_kpa','iat_c','clt_c')},transactions=transactions)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('wire',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    sizes=dict(enumerate([128,288,288,128,288,128,240,384,192,192,288,192,128,288,256],1))
    result=analyze(args.wire,sizes);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='transactions'},indent=2))
