"""Reference codec for a future screen; no screen UI or radio transport is built here."""
import hashlib, hmac, math, secrets, struct
MAGIC=b'ECN1'
CHANNEL=6

def header(kind, size):
    return struct.pack('<4sBBH', MAGIC, 1, kind, size)

def check(packet, kind, size):
    if len(packet)!=size or packet[:8]!=header(kind,size):
        raise ValueError('Unsupported protocol, type or packet length')

def mac_bytes(mac):
    raw=bytes.fromhex(mac.replace(':','')) if isinstance(mac,str) else bytes(mac)
    if len(raw)!=6 or raw[0]&1 or not any(raw):
        raise ValueError('Expected a unicast MAC')
    return raw

def pairing_request(beacon, ecu_mac, screen_mac, setup_key, name, nonce=None):
    check(beacon,1,24)
    key=bytes.fromhex(setup_key) if isinstance(setup_key,str) else setup_key
    if len(key)!=16:
        raise ValueError('Setup key must be 16 bytes')
    name=name.encode('ascii')
    if not 1<=len(name)<=23 or any(c<32 or c>126 for c in name):
        raise ValueError('Use 1-23 printable ASCII characters')
    name=name.ljust(24,b'\0');nonce=nonce if nonce is not None else secrets.token_bytes(16)
    if len(nonce)!=16:
        raise ValueError('Nonce must be 16 bytes')
    transcript=b'ECU-NOW-PAIR-v1'+beacon[8:]+mac_bytes(ecu_mac)+mac_bytes(screen_mac)+nonce+name
    proof=hmac.digest(key,transcript,'sha256')
    lmk=hmac.digest(key,b'K'+transcript[1:],'sha256')[:16]
    return header(2,96)+beacon[8:]+nonce+name+proof,lmk

def accepted(window, lmk):
    prefix=header(3,56)+window
    if len(window)!=16 or len(lmk)!=16:
        raise ValueError('Invalid window or key')
    return prefix+hmac.digest(lmk,prefix,'sha256')

def verify_accepted(packet, window, lmk):
    check(packet,3,56)
    if not hmac.compare_digest(packet,accepted(window,lmk)):
        raise ValueError('Key confirmation failed')

def acknowledgement(session, sequence, lmk):
    prefix=header(6,52)+struct.pack('<III',session,sequence,0)
    return prefix+hmac.digest(lmk,prefix,'sha256')

def telemetry(packet):
    check(packet,4,88)
    session,sequence,uptime,revision=struct.unpack_from('<IIII',packet,8)
    flags,valid,confirmed=struct.unpack_from('<HBB',packet,24)
    raw=struct.unpack_from('<8H',packet,28)
    values=struct.unpack_from('<9f',packet,44)
    return dict(session=session,sequence=sequence,uptime_ms=uptime,revision=revision,
                flags=flags,outputs_inhibited=bool(flags&16),raw=raw,rpm=values[0],
                battery_v=values[1],sensor_5v=values[2],
                sensors=[dict(value=values[3+i] if valid&(1<<i) and math.isfinite(values[3+i]) else None,
                              confirmed=bool(confirmed&(1<<i))) for i in range(6)],
                can_frames=struct.unpack_from('<I',packet,80)[0],sample_age_ms=struct.unpack_from('<I',packet,84)[0])
