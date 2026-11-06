"""Bounded text IPC to actual non-UNIT_TEST Speeduino in a virtual native HAL."""
import math
import json,hashlib
import os
from pathlib import Path
import select
import subprocess

ROOT=Path(__file__).resolve().parents[1]


class SpeeduinoRuntime:
    def __init__(self,per_tooth=False,logger_cam=False,sequential=False,timer_bits=32,semi_sequential=False):
        if timer_bits not in (16,32):raise ValueError('Native timer width must be16or32')
        if semi_sequential and (sequential or logger_cam):raise ValueError('Conflicting cycle profiles')
        executable=ROOT/('.cache/engine/speeduino-sim/speeduino-sim' if timer_bits==32 else '.cache/engine/speeduino-sim16/speeduino-sim')
        manifest=json.loads(executable.with_name('build-manifest.json').read_text())
        if hashlib.sha256(executable.read_bytes()).hexdigest()!=manifest['binary_sha256']:raise RuntimeError('Reference executable differs from its build manifest')
        self.timer_bits=timer_bits;self.edge_modes={};self.sequential=sequential;self.semi_sequential=semi_sequential;self.spark_trims=[0]*4;self.last_status={}
        self.process=subprocess.Popen([str(executable),*(['--per-tooth'] if per_tooth else []),*(['--logger-cam'] if logger_cam else []),*(['--sequential'] if sequential else []),*(['--semi-sequential'] if semi_sequential else [])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,bufsize=0)
        self.buffer=b'';self.now=0
        self.idle_profile=None
        try:
            self._initialize(per_tooth)
            if sequential:
                lines=self.command("cycleprofile")
                expected=[3,3,0,0,1,540,540,540,540]
                if len(lines)!=1 or lines[0].split()[0]!="cycleprofile" or list(map(int,lines[0].split()[1:]))!=expected:raise RuntimeError("Sequential reference profile was not preserved by production setup")
                self.profile["cycle_profile"]=expected
            if semi_sequential:
                for command,expected in [('cycleprofile',[1,2,0,0,1,180,180,180,180]),('injectorprofile',[1,1,1,0,2,360,2,2])]:
                    lines=self.command(command)
                    if len(lines)!=1 or lines[0].split()[0]!=command or list(map(int,lines[0].split()[1:]))!=expected:raise RuntimeError('Semi-sequential reference profile was not preserved by production setup: '+repr(lines))
                    self.profile[command]=expected
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

    def configure_idle(self,tune,seeded=True,invert=False):
        if self.idle_profile is not None:raise ValueError('Reference idle profile is before-start only')
        c=tune['idle_control'];s=tune['settings'];tick=16 if self.timer_bits==16 else 4
        hz=round(c['frequency_hz']/2)*2;counts=int(1e6/(tick*hz))
        # Documented normalized gain mapping; actual upstream integer cadence is retained.
        kp=round(s['idle_kp']*128*counts/100);ki=round(s['idle_ki']*128*counts/100);kd=round(c['kd']*128*counts/25)
        if any(not 0<=v<=255 for v in (kp,ki,kd)):raise ValueError('Reference gains cannot be represented by uint8 raw gains')
        def interp(values,x):
            axis=c['coolant_c']
            if x<=axis[0]:return values[0]
            for i in range(1,len(axis)):
                if x<=axis[i]:return values[i-1]+(values[i]-values[i-1])*(x-axis[i-1])/(axis[i]-axis[i-1])
            return values[-1]
        args=[{'on_off':1,'open_loop':2,'closed_loop':6}[c['algorithm']],hz,kp,ki,kd,round(c['tps_closed_pct']*2),round(c['exit_rpm_above']/10),round(c['afterstart_taper_s']*10),round(c['min_pct']),round(c['max_pct']),round(c['fast_idle_temp_c']+40),int(seeded),int(invert)]
        for x in range(-40,141,20):args += [round(interp(c['run_pct'],x)),round((s['idle_target_rpm']+interp(c['target_add_rpm'],x))/10)]
        args += [round(interp(c['crank_pct'],x)) for x in (-40,20,80,140)]
        lines=self.command('idleconfig '+' '.join(map(str,args)));registers=[l for l in lines if l.startswith('idleregisters ')]
        if len(registers)!=1:raise RuntimeError('Missing reference idle initialization registers')
        fields=list(map(int,registers[0].split()[1:]));self.pin_map[fields[5]]=8
        self.idle_profile=dict(algorithm=args[0],requested_hz=c['frequency_hz'],represented_hz=hz,tick_us=tick,raw_kp=kp,raw_ki=ki,raw_kd=kd,initial_registers=fields,seeded=seeded,invert=invert,gain_mapping='nominal normalized gain; actual integer PID cadence/rounding retained')
        return self._edges([l for l in lines if l.startswith('edge ')])

    def idle_status(self):
        lines=self.command('idlestatus')
        if len(lines)!=1 or not lines[0].startswith('idlestatus '):raise RuntimeError('Missing idle status')
        fields=list(map(int,lines[0].split()[1:]))
        return dict(zip(('algorithm','frequency_hz','reported_duty_pct','target_rpm','on','physical_level','counter','compare'),fields))

    def cylinder_trims(self,trims):
        if not self.sequential:raise ValueError('Reference cylinder trims require sequential profile')
        if not isinstance(trims,dict) or set(trims)!={'enabled','spark_deg','fuel_maps'} or type(trims['enabled']) is not bool or len(trims['spark_deg'])!=4 or len(trims['fuel_maps'])!=4:raise ValueError('Invalid reference trim configuration')
        values=[int(trims['enabled'])];order=[0,2,3,1]
        for physical in order:
            spark=trims['spark_deg'][physical];m=trims['fuel_maps'][physical]
            if type(spark) not in (int,float) or not math.isfinite(spark) or spark!=int(spark) or not -20<=spark<=20:raise ValueError('Reference spark trim uses integer degrees')
            if not isinstance(m,dict) or set(m)!={'rpm','load','cells'} or len(m['rpm'])!=6 or len(m['load'])!=6 or len(m['cells'])!=36 or any(type(v) not in (int,float) or not math.isfinite(v) for values_ in m.values() for v in values_):raise ValueError('Reference six-by-six finite trim map expected')
            if any(not 50<=v<=150 for v in m['cells']):raise ValueError('Reference fuel trim range')
            rpm=[max(1,round(v/100)) for v in m['rpm']];load=[round(v/2) for v in m['load']];pct=[round(v-100) for v in m['cells']]
            for original,quantized in [(m['rpm'],rpm),(m['load'],load)]:
                if any(original[i]>=original[i+1] or quantized[i]>=quantized[i+1] for i in range(5)) or any(not 1<=v<=255 for v in quantized):raise ValueError('Reference axes cannot be represented after RPM/100 or load/2 quantization')
            values += [int(spark) if trims['enabled'] else 0,*rpm,*load,*pct]
        if self.command('trimconfig '+' '.join(map(str,values))):raise RuntimeError('Unexpected reference trim response')
        self.spark_trims=[int(v) for v in trims['spark_deg']] if trims['enabled'] else [0]*4

    def trim_lookup(self,rpm,load):
        lines=self.command(f'trimlookup {int(rpm)} {int(load)}')
        if len(lines)!=1 or not lines[0].startswith('trimlookup '):raise RuntimeError('Invalid trim lookup')
        values=list(map(int,lines[0].split()[1:]));result=[0]*4
        for native,physical in enumerate((0,2,3,1)):result[physical]=values[native]
        return result

    def channel_pulses(self):
        lines=self.command('channelpw')
        if len(lines)!=1 or not lines[0].startswith('channelpw '):raise RuntimeError('Invalid channel pulse response')
        values=list(map(int,lines[0].split()[1:]));result=[0]*4
        for native,physical in enumerate((0,2,3,1)):result[physical]=values[native]
        return result

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
                ch=self.pin_map[pin]
                advance=self.last_status.get('advance_deg',0)+self.spark_trims[ch-4] if ch>=4 and self.sequential and sync==2 and any(self.spark_trims) else None
                edges.append((timestamp,ch,bool(high),advance,None))
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
        self.last_status=result;return result

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
