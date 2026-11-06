#!/usr/bin/env python3
"""Compare old/current trace serialization without changing either runtime."""
from pathlib import Path
import importlib.util,json,queue,shutil,threading,time,zlib
BASE=Path(__file__).resolve().parent
old=BASE.parent/'revision003/fixture-root'
negative=BASE/'negative-fixture'
for name in ['tools/speeduino_serial_runtime.py','tools/speeduino_serial_sim.cpp','scripts/build_speeduino_serial.py','.cache/engine/speeduino-serial-sim/build-manifest.json','.cache/engine/speeduino-serial-sim/speeduino-serial-sim']:
    dest=negative/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/name,dest)
def frame(payload):return len(payload).to_bytes(2,'big')+payload+zlib.crc32(payload).to_bytes(4,'big')
def run(name,fixture):
    spec=importlib.util.spec_from_file_location(name,fixture/'tools/speeduino_serial_runtime.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    trace=[];q_started=threading.Event();release=threading.Event();q=queue.Queue();errors=[]
    def wire(direction,body):
        trace.append((direction,body.hex()))
        if direction=='RX'and body==frame(b'Q'):
            q_started.set()
            if not release.wait(2):raise RuntimeError('Probe barrier was not released')
    n=m.SpeeduinoSerialRuntime(q.put,wire,BASE/'sessions'/name)
    def send(command):
        try:n.send(frame(command))
        except Exception as error:errors.append(str(error))
    a=threading.Thread(target=send,args=(b'Q',));b=threading.Thread(target=send,args=(b'C',))
    try:
        a.start();assert q_started.wait(1);b.start();time.sleep(.1)
        before_release=list(trace);release.set();a.join(2);b.join(2)
        assert not a.is_alive()and not b.is_alive()and not errors
        pending=b'';responses=[]
        while len(responses)<2:
            pending+=q.get(timeout=2)
            while len(pending)>=2:
                count=int.from_bytes(pending[:2],'big')
                if len(pending)<count+6:break
                payload=pending[2:count+2];assert zlib.crc32(payload)==int.from_bytes(pending[count+2:count+6],'big')
                responses.append(payload.hex());pending=pending[count+6:]
        result=dict(trace=trace,before_barrier_release=before_release,responses=responses,errors=errors,failure=n.failure)
    finally:release.set();n.close()
    return result
negative_result=run('old-trace-negative',negative)
current_result=run('current-trace-serialized',BASE/'fixture-root')
assert negative_result['responses']==[b'\0\xff'.hex(),b'\0speeduino 202504-dev'.hex()]
assert current_result['responses']==[b'\0speeduino 202504-dev'.hex(),b'\0\xff'.hex()]
result=dict(old_bug_reproduced=True,current_fix_verified=True,old=negative_result,current=current_result)
(BASE/'trace-order-comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
