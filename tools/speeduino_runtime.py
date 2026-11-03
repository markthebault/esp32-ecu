"""Bounded text IPC to actual non-UNIT_TEST Speeduino in a virtual native HAL."""
import math
import os
from pathlib import Path
import select
import subprocess

ROOT=Path(__file__).resolve().parents[1]


class SpeeduinoRuntime:
    def __init__(self,per_tooth=False,logger_cam=False,sequential=False,timer_bits=32):
        if timer_bits not in (16,32):raise ValueError('Native timer width must be16or32')
        executable=ROOT/('.cache/engine/speeduino-sim/speeduino-sim' if timer_bits==32 else '.cache/engine/speeduino-sim16/speeduino-sim')
        self.timer_bits=timer_bits;self.edge_modes={};self.sequential=sequential
        self.process=subprocess.Popen([str(executable),*(['--per-tooth'] if per_tooth else []),*(['--logger-cam'] if logger_cam else []),*(['--sequential'] if sequential else [])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,bufsize=0)
        self.buffer=b'';self.now=0
        try:
            self._initialize(per_tooth)
            if sequential:
                lines=self.command("cycleprofile")
                expected=[3,3,0,0,1,540,540,540,540]
                if len(lines)!=1 or lines[0].split()[0]!="cycleprofile" or list(map(int,lines[0].split()[1:]))!=expected:raise RuntimeError("Sequential reference profile was not preserved by production setup")
                self.profile["cycle_profile"]=expected
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

    def logger_profile(self):
        lines=self.command('loggerprofile')
        if len(lines)!=1 or not lines[0].startswith('loggerprofile '):raise RuntimeError('Missing logger configuration')
        values=list(map(int,lines[0].split()[1:]))
        if len(values)!=5:raise RuntimeError('Incomplete logger configuration')
        return dict(zip(('crank_pin','cam_pin','crank_edge','cam_edge','injection_layout'),values))

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
        return self._edges(lines)

    def _edges(self,lines):
        edges=[]
        for line in lines:
            fields=line.split()
            if len(fields)!=6 or fields[0]!='edge':raise RuntimeError('Unexpected native response: '+line)
            timestamp,pin,high,sync,span=map(int,fields[1:])
            if pin in self.pin_map:
                ch=self.pin_map[pin];edges.append((timestamp,ch,bool(high),None,None))
                if self.sequential:self.edge_modes[(timestamp,ch,bool(high))]=dict(sync_status=sync,ignition_cycle_deg=span,effective_sequential=sync==2 and span==720)
        return edges

    def input_edge(self,time_us,channel,high):
        if isinstance(time_us,bool) or not isinstance(time_us,int) or not self.now<=time_us<=60_000_000 or type(channel) is not int or channel not in (0,1) or type(high) is not bool:
            raise ValueError('Invalid virtual trigger edge')
        self.now=time_us
        return self._edges(self.command(f'input {time_us} {channel} {int(high)}'))

    def logger(self,mode):
        if mode not in ('composite','tooth','stop'):raise ValueError('Invalid production logger mode')
        if self.command('logger '+mode):raise RuntimeError('Unexpected logger-start response')

    def trigger_log(self):
        lines=self.command('logread')
        if not lines or not lines[0].startswith('loginfo '):raise RuntimeError('Missing native logger header')
        _,kind,count,capacity,full=lines[0].split();count,capacity,full=map(int,(count,capacity,full))
        if not 0<=count<=capacity or capacity!=127 or len(lines)!=count+1:raise RuntimeError('Invalid native logger length')
        rows=[]
        for index,line in enumerate(lines[1:]):
            tag,number,value,flags=line.split()
            if tag!='logrow' or int(number)!=index:raise RuntimeError('Invalid native logger record')
            rows.append(dict(sequence=index+1,value=int(value),flags=int(flags)))
        return dict(mode=kind,count=count,capacity=capacity,full=bool(full),records=rows)

    def status(self):
        lines=self.command('status')
        if len(lines)!=2 or not lines[0].startswith('status ') or not lines[1].startswith('diagnostic '):
            raise RuntimeError('Unexpected Speeduino status response')
        values=list(map(int,lines[0].split()[1:]))
        keys=('time_us','rpm','pulse_us','advance_deg','map_kpa','ve_pct','correction_pct','clt_c','iat_c','battery_01v','sync',
              'fuel_channels','ignition_channels','soft_limit_active')
        if len(values)!=len(keys):raise RuntimeError('Incomplete native status')
        result=dict(zip(keys,values));mode=list(map(int,lines[1].split()[1:]))
        if len(mode)!=11:raise RuntimeError('Incomplete native mode diagnostics')
        result.update(ignition_cycle_deg=mode[-3],injection_cycle_deg=mode[-2],squirts_per_cycle=mode[-1],crank_synced=result['sync']>=1,phase_synced=result['sync']==2)
        return result

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
            if len(fields)!=6 or fields[0]!='edge':raise RuntimeError('Unexpected halt response')
            timestamp,pin,high,sync,span=map(int,fields[1:])
            if pin in self.pin_map:edges.append((timestamp,self.pin_map[pin],bool(high)))
        return edges
