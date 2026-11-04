#!/usr/bin/env python3
"""Independent audit of complete, nontruncated RX/TX hex-line captures."""
from pathlib import Path
import argparse,collections,hashlib,json,re,zlib

def validate(path):
    requests=[];responses=[];issues=[];messages=[];pending=None
    for line_no,line in enumerate(path.read_text().splitlines(),1):
        match=re.match(r'(RX|TX) (\d+) ([0-9a-f]+)$',line)
        if not match:
            continue
        direction,count,hex_data=match.groups()
        data=bytes.fromhex(hex_data)
        if len(data)!=int(count):
            issues.append(dict(line=line_no,issue='truncated hex data',declared=int(count),captured=len(data)))
        if direction=='RX':
            if pending is not None:
                issues.append(dict(line=line_no,issue='new request before prior response'))
            raw=data==b'F'
            payload=data if raw else data[2:-4]
            if not raw and not valid_frame(data):
                issues.append(dict(line=line_no,issue='invalid request length or CRC'))
            pending=(payload,raw,line_no)
            requests.append(payload)
        else:
            if pending is None:
                issues.append(dict(line=line_no,issue='response with no request'))
                continue
            payload,raw,request_line=pending
            pending=None
            answer=data if raw else data[2:-4]
            if raw and data!=b'002':
                issues.append(dict(line=line_no,issue='raw F response differs from 002'))
            if not raw and not valid_frame(data):
                issues.append(dict(line=line_no,issue='invalid response length or CRC'))
            responses.append(answer)
            messages.append(dict(request_line=request_line,response_line=line_no,request_hex=payload.hex(),response_hex=answer.hex(),raw=raw))
    if pending is not None:
        issues.append(dict(issue='unanswered final request'))
    return dict(wire_path=str(path),wire_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),request_count=len(requests),response_count=len(responses),command_counts=dict(collections.Counter(chr(p[0]) if p else '' for p in requests)),request_payload_counts=dict(collections.Counter(p.hex() for p in requests)),issues=issues,page_runtime_write_or_burn_requests=sum(p[:1] in (b'p',b'r',b'M',b'd',b'b') for p in requests),transactions=messages)

def valid_frame(data):
    return len(data)>=7 and int.from_bytes(data[:2],'big')==len(data)-6 and zlib.crc32(data[2:-4])==int.from_bytes(data[-4:],'big')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wire',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=validate(args.wire)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='transactions'},indent=2))
