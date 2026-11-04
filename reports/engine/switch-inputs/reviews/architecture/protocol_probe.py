"""Independent abstract protocol probes. These do not execute the production driver."""
from pathlib import Path
import json

OUT=Path(__file__).resolve().parent
# Physical contacts=closed, straps0x28 and GP6 fed from GP7.
# GP7 input read is deliberately ignored: MCP23008 GP7 is output-only.
def registers(configured, challenge):
    value=[0]*11
    value[0]=0x7f if configured else 0xff
    value[9]=0x28|0x03|(0x40 if configured and challenge else 0)
    value[10]=0x80 if configured and challenge else 0
    return value

def qualifies(burst, guard, challenge, guarded):
    expected=registers(True,challenge)
    # INTCAP is historical/unknown. GPIO contacts are data; GP7 is not input evidence.
    config_ok=all(burst[i]==expected[i] for i in (0,1,2,3,4,5,6,7,10))
    pins_ok=(burst[9]&0x7c)==(expected[9]&0x7c)
    return config_ok and pins_ok and (not guarded or guard==0x7f)

cases=[]
for challenge in (False,True):
    for boundary in range(12):
        before=registers(True,challenge); after=registers(False,challenge)
        # Reset just before byte boundary;11 means after OLAT and before the guard.
        burst=[before[i] if i<boundary else after[i] for i in range(11)]
        cases.append(dict(challenge=int(challenge),reset_before_burst_byte=boundary,
                          unguarded_accept=qualifies(burst,0xff,challenge,False),
                          guarded_accept=qualifies(burst,0xff,challenge,True)))
assert any(c['unguarded_accept'] for c in cases)
assert not any(c['guarded_accept'] for c in cases)
for c in (False,True):
    assert qualifies(registers(True,c),0x7f,c,True)
# A reset after the guard is a new event, outside this observed transaction.
assert qualifies(registers(True,False),0x7f,False,True)

# Invalid skipped by controller observation must not be overwritten by fast recovery.
class Latch:
    def __init__(self):self.fault_id=0; self.pending=None
    def fault(self):self.fault_id+=1;self.pending=self.fault_id
    def publish(self,recovered):return ('invalid',self.pending) if self.pending is not None else ('valid' if recovered else 'invalid',None)
    def acknowledge(self,snapshot,observed):
        if observed and snapshot[0]=='invalid' and snapshot[1]==self.pending:self.pending=None
l=Latch();l.fault();snapshot=l.publish(False)
l.acknowledge(snapshot,False);assert l.publish(True)==snapshot
l.fault();l.acknowledge(snapshot,True);assert l.pending==2
second=l.publish(True);l.acknowledge(second,True);assert l.publish(True)==('valid',None)

# Conservative timestamp preserves the oldest possible age inside acquisition.
start_us=1_000_000;finish_us=start_us+2999
assert finish_us-start_us<3000
sample_timestamp=start_us
held_timestamp=sample_timestamp
assert held_timestamp==sample_timestamp
at_core=start_us+20_000;assert at_core-sample_timestamp<=20_000
at_core+=1;assert at_core-sample_timestamp>20_000

result=dict(passed=True,scope='Abstract independent model only; production and HIL tests still required',reset_boundary_cases=cases,
   healthy_challenge_states=2,unguarded_accepted_reset_cases=sum(c['unguarded_accept'] for c in cases),
   guarded_accepted_reset_cases=sum(c['guarded_accept'] for c in cases),
   latch_checks=['invalid survives observation lock skip and fast recovery','old fault-id acknowledgment cannot clear newer fault','matching observed invalid allows later valid recovery'],
   clock_checks=['source stamp equals acquisition start','held stamp is retained','20ms freshness inclusive and20ms+1us stale'],
   unavoidable_limits=['reset after final guard is outside observed interval','fixed straps and loop do not uniquely identify accessory','two-wire contact continuity cannot be inferred'])
(OUT/'protocol-probe.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
