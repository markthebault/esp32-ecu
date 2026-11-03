"""Bounded text IPC to actual non-UNIT_TEST Speeduino in a virtual native HAL."""
import math
import os
from pathlib import Path
import select
import subprocess

ROOT=Path(__file__).resolve().parents[1]


class SpeeduinoRuntime:
    def __init__(self,per_tooth=False):
        executable=ROOT/'.cache/engine/speeduino-sim/speeduino-sim'
        self.process=subprocess.Popen([str(executable),*(['--per-tooth'] if per_tooth else [])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,bufsize=0)
        self.buffer=b'';self.now=0
        try:self._initialize(per_tooth)
        except BaseException:self.close();raise

    def _initialize(self,per_tooth):
        ready=self._line()
        if not ready.startswith('ready '):raise RuntimeError('Unexpected native Speeduino greeting')
        pins=self._line().split()
        if pins[0]!='pins' or len(pins)!=9:raise RuntimeError('Incomplete native pin mapping')
        # Native channels are firing-order channels1,2,3,4. Our physical wiring
        # uses1,3,4,2. Both maps are explicit, including wasted-spark partners.
        canonical=(0,2,3,1,4,6,7,5)
        self.pin_map={int(pin):canonical[n] for n,pin in enumerate(pins[1:])}
        profile=self.command('profile')
        expected=[107,65,62,3,1,int(per_tooth)]
        if len(profile)!=1 or not profile[0].startswith('profile ') or list(map(int,profile[0].split()[1:]))!=expected:
            raise RuntimeError('Native setup did not preserve the declared benchmark protection/tune profile')
        self.profile=dict(zip(('reqFuel_point1ms','hard_limit_rpm100','soft_limit_rpm100',
                              'protection_type','hard_limit_mode','per_tooth'),expected))

    def _line(self):
        while b'\n' not in self.buffer:
            if not select.select([self.process.stdout],[],[],10)[0]:raise RuntimeError('Native Speeduino IPC timeout')
            block=os.read(self.process.stdout.fileno(),4096)
            if not block:
                error=self.process.stderr.read(4096).decode(errors='replace')
                raise RuntimeError('Native Speeduino exited: '+error)
            self.buffer+=block
            if len(self.buffer)>65536:raise RuntimeError('Unbounded native protocol line')
        line,self.buffer=self.buffer.split(b'\n',1)
        return line.decode('ascii')

    def command(self,text):
        self.process.stdin.write((text+'\n').encode('ascii'));self.process.stdin.flush()
        result=[]
        for _ in range(65536):
            line=self._line()
            if line=='ok':return result
            result.append(line)
        raise RuntimeError('Native response limit exceeded')

    def sensors(self,sample):
        values=[sample[k] for k in ('map_kpa','tps_pct','clt_c','iat_c','battery_v')]+[sample['lambda']*14.7]
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):raise ValueError('Invalid sensor values')
        self.command('sensors '+' '.join(format(v,'.12g') for v in values))

    def advance(self,time_us,tooth=False):
        if isinstance(time_us,bool) or not isinstance(time_us,int) or time_us<self.now or time_us>60_000_000:
            raise ValueError('Native benchmark time must be monotonic0..60s')
        self.now=time_us
        lines=self.command(('tooth' if tooth else 'advance')+' '+str(time_us))
        edges=[]
        for line in lines:
            fields=line.split()
            if len(fields)!=4 or fields[0]!='edge':raise RuntimeError('Unexpected native response: '+line)
            timestamp,pin,high=map(int,fields[1:])
            if pin in self.pin_map:edges.append((timestamp,self.pin_map[pin],bool(high),None,None))
        return edges

    def status(self):
        lines=self.command('status')
        if len(lines)!=2 or not lines[0].startswith('status ') or not lines[1].startswith('diagnostic '):
            raise RuntimeError('Unexpected Speeduino status response')
        values=list(map(int,lines[0].split()[1:]))
        keys=('time_us','rpm','pulse_us','advance_deg','map_kpa','ve_pct','correction_pct','clt_c','iat_c','battery_01v','sync',
              'fuel_channels','ignition_channels','soft_limit_active')
        if len(values)!=len(keys):raise RuntimeError('Incomplete native status')
        return dict(zip(keys,values))

    def close(self):
        if self.process:
            try:
                if self.process.poll() is None:
                    self.process.stdin.write(b'quit\n');self.process.stdin.flush();self.process.wait(timeout=2)
            finally:
                if self.process.poll() is None:self.process.kill();self.process.wait(timeout=2)
                self.process.stdin.close();self.process.stdout.close();self.process.stderr.close();self.process=None

    def halt(self):
        lines=self.command('halt');edges=[]
        for line in lines:
            fields=line.split()
            if len(fields)!=4 or fields[0]!='edge':raise RuntimeError('Unexpected halt response')
            timestamp,pin,high=map(int,fields[1:])
            if pin in self.pin_map:edges.append((timestamp,self.pin_map[pin],bool(high)))
        return edges
