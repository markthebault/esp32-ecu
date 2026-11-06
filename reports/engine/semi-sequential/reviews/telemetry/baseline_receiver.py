"""Reference authenticated engine receiver. No screen UI or ESP-NOW transport.

Inputs to receive() must be from the saved ECU MAC. Authentication is checked
before accepting sequence/freshness. Legacy sensor frames retain their own codec.
"""
import hmac,math,secrets,struct
from espnow_protocol import header,check,mac_bytes

CAP_SIZE=76;REPLY_SIZE=108;ENGINE_SIZE=232;ENGINE_BODY=200;ACK_SIZE=56
FEATURE_ENGINE=1;SCHEMA=1;UINT32_MAX=2**32-1;UINT64_MAX=2**64-1
INPUT_NAMES=('rpm','map_kpa','tps_pct','clt_c','iat_c','lambda','battery_v','sensor_v')
PROPOSAL_NAMES=('rpm','ve_pct','target_lambda','advance_deg','pulse_ms','dwell_ms','deadtime_ms','air_mg','warmup','afterstart','accel','ego','duty_pct','idle_pct')
PRESENT=1;INPUTS_FRESH=2;STORAGE_OK=4;CRANK_SYNC=8;PHASE_SYNC=16;PHASE_REQUIRED=32;SUBMITTED=64;DUMMY_POLICY=128;PHASE_CONTEXT_MATCH=256;PROPOSED_ACTIVE=512;FUEL_CUT=1024;SPARK_CUT=2048;PUMP=4096;FAN=8192;INPUTS_QUALIFIED=16384;DISPLAY_FRESH=32768

def uint(value,bits):
    if type(value) is not int or not 0<=value<2**bits:raise ValueError('Unsigned integer outside wire range')
    return value

def key_bytes(key,length):
    value=bytes.fromhex(key) if isinstance(key,str) else bytes(key)
    if len(value)!=length:raise ValueError('Incorrect key/nonce length')
    return value

def derive_engine_key(lmk,boot_nonce,session):
    return hmac.digest(key_bytes(lmk,16),b'ECU-NOW-ENGINE-v1'+key_bytes(boot_nonce,16)+struct.pack('<I',uint(session,32)),'sha256')

def capability_request(lmk,session=0,counter=0,features=0,nonce=None):
    nonce=secrets.token_bytes(16) if nonce is None else key_bytes(nonce,16)
    if features not in (0,1) or not counter and features:raise ValueError('Unsupported capability update/query')
    body=header(7,CAP_SIZE)+struct.pack('<II16sIII',uint(session,32),uint(counter,32),nonce,uint(features,32),SCHEMA if features else 0,0)
    return body+hmac.digest(key_bytes(lmk,16),body,'sha256')

def capability_reply(packet,lmk,nonce):
    check(packet,8,REPLY_SIZE)
    if not hmac.compare_digest(packet[76:],hmac.digest(key_bytes(lmk,16),packet[:76],'sha256')):raise ValueError('Capability authentication failed')
    session,counter,echo,features,schema,status,boot_nonce,floor,sent=struct.unpack_from('<II16sIII16sQQ',packet,8)
    if echo!=key_bytes(nonce,16) or not session or features not in (0,1) or schema!=(SCHEMA if features else 0) or status:raise ValueError('Unexpected capability reply')
    return dict(session=session,counter=counter,features=features,schema=schema,boot_nonce=boot_nonce,sequence_floor=floor,sent_esp_us=sent)

def engine_acknowledgement(session,sequence,data_key):
    body=header(10,ACK_SIZE)+struct.pack('<IQI',uint(session,32),uint(sequence,64),0)
    return body+hmac.digest(key_bytes(data_key,32),body,'sha256')

def engine_telemetry(packet,data_key):
    check(packet,9,ENGINE_SIZE)
    if not hmac.compare_digest(packet[ENGINE_BODY:],hmac.digest(key_bytes(data_key,32),packet[:ENGINE_BODY],'sha256')):raise ValueError('Engine authentication failed')
    session,packet_sequence,schema,flags,sample_age,control_age,tune,sensors=struct.unpack_from('<IQHHIIII',packet,8)
    proposal_sequence,worker_sequence,phase_epoch,worker_epoch,faults,losses,rejected,cam_error=struct.unpack_from('<QQIIIIIf',packet,40)
    state,strategy,source,phase_reason,valid,timing,last_timing,virtual,physical,board=struct.unpack_from('<10B',packet,80)
    sent,worker_tune,worker_sensors,worker_age=struct.unpack_from('<QIII',packet,92)
    inputs=struct.unpack_from('<8f',packet,112);proposals=struct.unpack_from('<14f',packet,144)
    if schema!=SCHEMA or not session or not packet_sequence or not proposal_sequence or not flags&PRESENT or source not in (1,2) or state>5 or strategy>1 or phase_reason>9 or timing>16 or last_timing>16 or board&~15 or packet[90:92]!=b'\0\0':raise ValueError('Invalid engine schema or enum')
    if bool(flags&DISPLAY_FRESH)!=(sample_age<=1000 and control_age<=1000):raise ValueError('Inconsistent source display freshness')
    limits=((0,12000),(10,110),(0,100),(-40,140),(-40,110),(.65,1.5),(7,18),(4.75,5.25))
    for i,value in enumerate(inputs):
        if valid&(1<<i):
            # Wire floats are float32, so permit only their rounding at limits.
            low,high=limits[i]
            if not math.isfinite(value) or not low-1e-5<=value<=high+1e-5:raise ValueError('Valid input outside its physical range')
        elif not math.isnan(value):raise ValueError('Invalid input must remain NaN')
    if any(math.isinf(value) for value in proposals) or math.isinf(cam_error):raise ValueError('Infinite engine value')
    age=lambda n:None if n==UINT32_MAX else n
    return dict(session=session,packet_sequence=packet_sequence,schema_version=schema,flags=flags,
                source='target_control_observation' if source==1 else 'synthetic_control_observation',source_code=source,scalar_proposal_basis='untrimmed_base_demand',per_cylinder_available=False,
                sample_age_ms=age(sample_age),control_age_ms=age(control_age),source_display_fresh=bool(flags&DISPLAY_FRESH),
                tune_revision=tune,sensor_revision=sensors,proposal_sequence=proposal_sequence,phase_epoch=phase_epoch,phase_epoch_domain='external_configuration_context',
                state_code=state,strategy_code=strategy,phase_reason_code=phase_reason,input_valid_mask=valid,
                controller_faults=faults,phase_losses=losses,cam_rejected=rejected,cam_error_deg=cam_error if math.isfinite(cam_error) else None,
                inputs={k:v if valid&(1<<i) else None for i,(k,v) in enumerate(zip(INPUT_NAMES,inputs))},
                proposals={k:v if math.isfinite(v) else None for k,v in zip(PROPOSAL_NAMES,proposals)},board_flags=board,
                sent_esp_us=sent,worker_observation=dict(command_sequence=worker_sequence,epoch=worker_epoch,epoch_domain='executor_generation',tune_revision=worker_tune,sensor_revision=worker_sensors,age_ms=age(worker_age),timing_fault_code=timing,last_timing_fault_code=last_timing,virtual_high_mask=virtual,physical_command_mask=physical),
                inputs_fresh_at_control=bool(flags&INPUTS_FRESH),proposal_submitted=bool(flags&SUBMITTED),physical_policy='dummy_loads_only' if flags&DUMMY_POLICY else 'inhibited')

class EngineReceiver:
    """Saved-peer engine protocol state and conservative display-age bound.

    A timed authenticated query supplies a sequence floor and clock interval.
    Refresh at most5s later. A generous2% drift allowance+2ms quantization is
    included; this is an explicit clock assumption, not RF/engine qualification.
    """
    query_lifetime_ms=1000
    clock_lifetime_ms=5000
    def __init__(self,ecu_mac,lmk):
        self.ecu_mac=mac_bytes(ecu_mac);self.lmk=key_bytes(lmk,16);self.pending=None
        self.session=None;self.counter=0;self.features=0;self.data_key=None;self.reply=None
        self.latest=None;self.received_ms=None;self.last_packet=0;self.last_snapshot=0;self.last_sent_esp=0
        self.rejected=0;self.immutable=None
    def _time(self,ms):return uint(ms,64)
    def _peer(self,mac):
        if mac_bytes(mac)!=self.ecu_mac:raise ValueError('Packet is not from saved ECU')
    def query(self,now_ms,nonce=None):
        now_ms=self._time(now_ms);packet=capability_request(self.lmk,nonce=nonce)
        self.pending=dict(packet=packet,sent_ms=now_ms,counter=0,features=None)
        self.data_key=None;self.latest=None;self.received_ms=None;return packet
    def update(self,enabled,now_ms,nonce=None):
        if type(enabled) is not bool or self.session is None or self.counter==UINT32_MAX:raise ValueError('Query current capability state first')
        now_ms=self._time(now_ms);packet=capability_request(self.lmk,self.session,self.counter+1,int(enabled),nonce)
        self.pending=dict(packet=packet,sent_ms=now_ms,counter=self.counter+1,features=int(enabled));return packet
    def retry(self):
        if self.pending is None:raise ValueError('No pending request')
        return self.pending['packet']
    def receive_reply(self,packet,mac,now_ms):
        self._peer(mac);now_ms=self._time(now_ms)
        if self.pending is None:raise ValueError('Unsolicited capability reply')
        pending=self.pending;reply=capability_reply(packet,self.lmk,pending['packet'][16:32])
        if now_ms<pending['sent_ms'] or now_ms-pending['sent_ms']>self.query_lifetime_ms:raise ValueError('Capability query expired')
        if pending['counter'] and (reply['session']!=self.session or reply['counter']!=pending['counter'] or reply['features']!=pending['features']):raise ValueError('Capability update changed')
        self.session=reply['session'];self.counter=reply['counter'];self.features=reply['features']
        self.data_key=derive_engine_key(self.lmk,reply['boot_nonce'],reply['session']);self.reply=dict(reply,query_sent_ms=pending['sent_ms'],received_ms=now_ms)
        self.last_packet=reply['sequence_floor'];self.last_snapshot=0;self.last_sent_esp=reply['sent_esp_us'];self.latest=None;self.received_ms=None;self.pending=None;self.immutable=None
        return reply
    def receive(self,packet,mac,now_ms):
        try:return self._receive(packet,mac,now_ms)
        except (ValueError,TypeError):
            self.rejected+=1;raise
    def _receive(self,packet,mac,now_ms):
        self._peer(mac);now_ms=self._time(now_ms)
        if self.data_key is None or not self.features&FEATURE_ENGINE or self.reply is None:raise ValueError('Fresh engine negotiation required')
        if now_ms<self.reply['received_ms'] or now_ms-self.reply['received_ms']>self.clock_lifetime_ms:raise ValueError('Refresh engine clock query')
        if (self.received_ms is not None and (now_ms<self.received_ms or now_ms-self.received_ms>1000)) or (self.received_ms is None and now_ms-self.reply['received_ms']>1000):raise ValueError('Stale gap requires a fresh query')
        data=engine_telemetry(packet,self.data_key)
        if data['session']!=self.session or data['packet_sequence']<=self.last_packet or data['proposal_sequence']<self.last_snapshot or data['sent_esp_us']<self.last_sent_esp:raise ValueError('Old session, duplicate, clock reversal or out-of-order observation')
        immutable=(packet[20:22],data['flags']&~DISPLAY_FRESH,packet[32:92],packet[100:108],packet[112:200])
        if data['proposal_sequence']==self.last_snapshot and immutable!=self.immutable:raise ValueError('Repeated snapshot payload changed')
        local_elapsed=now_ms-self.reply['query_sent_ms'];sender_elapsed=(data['sent_esp_us']-self.reply['sent_esp_us'])/1000
        uncertainty=2+math.ceil(local_elapsed*.02)
        if sender_elapsed<0 or sender_elapsed>local_elapsed+uncertainty:raise ValueError('Sender clock outside negotiated interval')
        transit=max(0,local_elapsed-sender_elapsed)+uncertainty
        data['transport_age_bound_ms']=math.ceil(transit)
        repeated=self.latest is not None and data['proposal_sequence']==self.last_snapshot
        for key,current in [('sample_age_ms',data['sample_age_ms']),('control_age_ms',data['control_age_ms']),('worker_age_ms',data['worker_observation']['age_ms'])]:
            # The2% clock assumption also applies to ages accumulated BEFORE
            # the query. A slow source clock must not understate that history.
            bounded=None if current is None else (current*100+97)//98+math.ceil(transit)
            if repeated:
                previous=self.latest.get('bounded_'+key)
                # A repeated unknown age cannot become fresh by transport alone.
                bounded=None if bounded is None or previous is None else max(bounded,previous+now_ms-self.received_ms)
            data['bounded_'+key]=bounded
        data['worker_observation']['bounded_age_ms']=data['bounded_worker_age_ms']
        self.latest=data;self.received_ms=now_ms;self.last_packet=data['packet_sequence'];self.last_snapshot=data['proposal_sequence'];self.last_sent_esp=data['sent_esp_us'];self.immutable=immutable
        return data
    def status(self,now_ms):
        now_ms=self._time(now_ms);elapsed=now_ms-self.received_ms if self.received_ms is not None and now_ms>=self.received_ms else None
        clock_valid=self.data_key is not None and self.reply is not None and self.reply['received_ms']<=now_ms<=self.reply['received_ms']+self.clock_lifetime_ms
        gap_valid=(elapsed is not None and elapsed<=1000) if self.received_ms is not None else bool(self.reply is not None and self.reply['received_ms']<=now_ms<=self.reply['received_ms']+1000)
        active=self.latest is not None and clock_valid and gap_valid
        ages={key:None if not active or self.latest.get('bounded_'+key) is None else self.latest['bounded_'+key]+elapsed for key in ('sample_age_ms','control_age_ms','worker_age_ms')}
        return dict(negotiated=self.data_key is not None,engine_enabled=bool(self.features&1),fresh=active and all(ages[k] is not None and ages[k]<=1000 for k in ('sample_age_ms','control_age_ms')),query_required=not(clock_valid and gap_valid),rejected=self.rejected,source=self.latest['source'] if self.latest else 'no_observation',**ages)
    def acknowledgement(self):
        if self.latest is None or self.data_key is None:raise ValueError('No authenticated engine frame')
        return engine_acknowledgement(self.session,self.last_packet,self.data_key)
