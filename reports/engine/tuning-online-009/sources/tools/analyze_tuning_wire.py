#!/usr/bin/env python3
"""Audit bounded rawF/MS-envelope RX/TX hex captures across byte-slice boundaries.

RX/TX mean bytes observed by the host bridge, not proof of physical delivery or
application consumption. A controlled stop can leave an unanswered tail; that
is disclosed separately from complete transactions and invalid frames.
"""
import argparse,collections,hashlib,json,re,zlib
from pathlib import Path
LIMIT=16777216
def analyze(path):
 raw=Path(path).read_bytes()
 if len(raw)>LIMIT:raise ValueError('Wire capture exceeds16MiB analysis bound')
 rx=bytearray();tx=bytearray();orphan_tx=bytearray();waiting=collections.deque();pairs=[];issues=[];commands=collections.Counter();counts={'RX':0,'TX':0};reset_prefixes=0
 def extract_requests():
  nonlocal reset_prefixes
  while rx:
   if rx[0]==0xf0:del rx[0];reset_prefixes+=1;continue
   if rx[0]==ord('F'):payload=b'F';del rx[0];kind='raw_F';valid=True
   else:
    if len(rx)<2:return
    size=int.from_bytes(rx[:2],'big')
    if not 0<size<=16384:issues.append('Request length outside capture domain');rx.clear();return
    if len(rx)<size+6:return
    frame=bytes(rx[:size+6]);del rx[:size+6];payload=frame[2:-4];kind='framed';valid=zlib.crc32(payload)==int.from_bytes(frame[-4:],'big')
    if not valid:issues.append('Request CRC differs')
   command=chr(payload[0]);commands[command]+=1;waiting.append(dict(kind=kind,command=command,request_hex=payload.hex(),request_crc_valid=valid))
 def extract_responses():
  while tx and waiting:
   request=waiting[0]
   if request['kind']=='raw_F':
    if len(tx)<3:return
    body=bytes(tx[:3]);del tx[:3];valid=body==b'002';status=None
    if not valid:issues.append('RawF response differs from002')
   else:
    if len(tx)<2:return
    size=int.from_bytes(tx[:2],'big')
    if not 0<size<=16384:issues.append('Response length outside capture domain');tx.clear();return
    if len(tx)<size+6:return
    frame=bytes(tx[:size+6]);del tx[:size+6];body=frame[2:-4];valid=zlib.crc32(body)==int.from_bytes(frame[-4:],'big');status=body[0]
    if not valid:issues.append('Response CRC differs')
   waiting.popleft();pairs.append(dict(**request,response_hex=body.hex(),response_crc_valid=valid,response_status=status))
  if tx and not waiting:
   issues.append('Response bytes with no queued complete request');orphan_tx.extend(tx);tx.clear()
 for number,line in enumerate(raw.decode('utf-8').splitlines(),1):
  if not line.startswith(('RX ','TX ')):continue
  match=re.fullmatch(r'(RX|TX) (\d+) ([0-9a-fA-F]+)',line)
  if not match:issues.append('Malformed event at line'+str(number));continue
  direction,count,value=match.groups()
  if len(value)%2:issues.append('Odd hex length at line'+str(number));continue
  body=bytes.fromhex(value)
  if len(body)!=int(count):issues.append('Declared byte count differs at line'+str(number));continue
  counts[direction]+=len(body)
  if direction=='RX':rx.extend(body);extract_requests()
  else:tx.extend(body)
  extract_responses()
  if len(rx)>LIMIT or len(tx)>LIMIT or len(waiting)>65536:raise ValueError('Unmatched capture exceeds analysis bound')
 signatures=sorted({bytes.fromhex(p['response_hex'])[1:].decode('ascii',errors='backslashreplace')for p in pairs if p['command']=='Q'and p['response_status']==0})
 capabilities=[]
 for p in pairs:
  body=bytes.fromhex(p['response_hex'])
  if p['command']=='f'and p['response_status']==0 and len(body)==6:capabilities.append(dict(protocol=body[1],read_chunk_bytes=int.from_bytes(body[2:4],'big'),write_chunk_bytes=int.from_bytes(body[4:6],'big')))
 return dict(scope='host_observed_rawF_and_framed_capture',wire_sha256=hashlib.sha256(raw).hexdigest(),bytes=counts,command_counts=dict(commands),complete_transactions=len(pairs),invalid_frames=issues,unanswered_requests=list(waiting),partial_request_hex=rx.hex(),unmatched_response_hex=(orphan_tx+tx).hex(),capture_complete=not waiting and not rx and not tx and not orphan_tx,signatures=signatures,capabilities=capabilities[:4],reset_prefixes=reset_prefixes,transactions=pairs)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('wire',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--require-complete',action='store_true');args=parser.parse_args()
 if args.output.exists():raise ValueError('Analysis output exists; preserve earlier evidence')
 result=analyze(args.wire);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items()if k not in('transactions','unanswered_requests')},indent=2))
 if result['invalid_frames']or(args.require_complete and not result['capture_complete']):raise SystemExit(1)
