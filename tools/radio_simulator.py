"""Synthetic radio state for UI/API checks. No ESP-NOW hardware or encryption."""
import json, os, secrets, tempfile, time

class RadioSimulator:
    def __init__(self, path):
        self.path = path
        self.peers = []
        self.storage_ok = True
        self.error = ''
        self.deadline = 0
        self.window = self.key = ''
        self.candidate = None
        if path.exists():
            try:
                peers = json.loads(path.read_text())
                if not isinstance(peers, list) or len(peers) > 4:
                    raise ValueError()
                macs = set()
                for p in peers:
                    if set(p) != {'mac', 'name'} or not isinstance(p['name'], str) or not 1 <= len(p['name']) < 24:
                        raise ValueError()
                    raw = bytes.fromhex(p['mac'].replace(':', ''))
                    if len(raw) != 6 or raw[0] & 1 or not any(raw) or p['mac'] in macs:
                        raise ValueError()
                    macs.add(p['mac'])
                self.peers = peers
            except (ValueError, TypeError, KeyError, OSError):
                self.storage_ok = False
                self.error = 'Simulated peer storage invalid; file not overwritten.'

    def close(self):
        self.deadline = 0
        self.window = self.key = ''
        self.candidate = None

    def expire(self):
        if self.deadline and time.monotonic() >= self.deadline:
            self.close()

    def save(self, peers):
        if not self.storage_ok:
            return False
        temp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as f:
                temp = f.name
                f.write(json.dumps(peers).encode())
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, self.path)
        except OSError:
            if temp and os.path.exists(temp):
                os.unlink(temp)
            self.error = 'Simulated peer storage write failed.'
            return False
        self.peers = peers
        self.error = ''
        return True

    def status(self):
        self.expire()
        return dict(available=True, storage_ok=self.storage_ok, simulator=True,
                    pairing=bool(self.deadline), remaining_s=max(0, int(self.deadline-time.monotonic()+.999)) if self.deadline else 0,
                    error=self.error, window=self.window, setup_key=self.key,
                    candidate=self.candidate, peers=[dict(p, connected=False, last_ack_ms=-1) for p in self.peers],
                    led='red_blink' if not self.storage_ok else 'blue_blink' if self.deadline else 'green',
                    channel=6, max_peers=4, mac='02:EC:00:00:00:01')

    def command(self, body):
        self.expire()
        if not isinstance(body, dict):
            return 422, {'error': 'Invalid radio command.'}
        action = body.get('action')
        if action == 'open':
            if not self.storage_ok:
                return 503, {'error': self.error}
            if len(self.peers) >= 4:
                return 409, {'error': 'Screen limit reached; unpair a screen first.'}
            self.close()
            self.window, self.key = secrets.token_hex(16).upper(), secrets.token_hex(16).upper()
            self.deadline = time.monotonic() + 30
        elif action == 'simulate' and self.deadline and not self.candidate:
            # Deliberately no radio authentication: this is a labelled UI fixture.
            used = {p['mac'] for p in self.peers}
            mac = next(f'02:EC:00:00:01:{i:02X}' for i in range(1, 6) if f'02:EC:00:00:01:{i:02X}' not in used)
            self.candidate = dict(name='Synthetic screen', mac=mac, approved=False)
        elif action == 'confirm' and self.deadline and self.candidate:
            if body.get('window') != self.window or body.get('mac') != self.candidate['mac']:
                return 409, {'error': 'Pairing candidate changed.'}
            if not self.save(self.peers + [{k: self.candidate[k] for k in ('mac', 'name')}]):
                return 507, {'error': self.error}
            self.close()
        elif action == 'cancel' and self.deadline and body.get('window') == self.window:
            self.close()
        elif action == 'unpair' and any(p['mac'] == body.get('mac') for p in self.peers):
            if not self.save([p for p in self.peers if p['mac'] != body['mac']]):
                return 507, {'error': self.error}
        else:
            return 422, {'error': 'Invalid command or pairing is closed.'}
        return 202, {'queued': True}
