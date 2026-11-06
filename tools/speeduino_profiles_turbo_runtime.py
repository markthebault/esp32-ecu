"""Bounded actual-GPIO production reference for generalized turbo experiments.

The engine wiring/effective-mode contract follows the separate16-pin fixture.
Boost uses raw ADCs, actual production PWM and a fixed native loop calendar.
No missing pin edge or controller status is synthesized.
"""
import json,math,subprocess
from pathlib import Path
from engine_geometry import EngineGeometry,INJECTOR_CHANNELS,COIL_CHANNELS
from speeduino_profiles_runtime import SpeeduinoProfilesRuntime,PIN,BASE_SHA,NATIVE_PINS,digest,ROOT
from speeduino_turbo_runtime import SpeeduinoTurboRuntime

SCOPE='production_sixteen_engine_outputs_and_raw_adc_boost_PWM'


def validate_profile(geometry,engine_mode='sequential',mode='off',duty=40,target=150,
                     default_unarmed_compare=False,loop_period_us=1000,cut_kpa=220,protection_rpm=6500):
    if not isinstance(geometry,EngineGeometry)or geometry.tooth1_tdc_deg!=90 or geometry.cam_edge_deg!=540:
        raise ValueError('Declared geometry with90deg tooth1 and540deg cam required')
    if engine_mode not in ('sequential','semi','wasted_cop')or mode not in ('off','open_loop','closed_loop'):
        raise ValueError('Unknown engine/boost fixture mode')
    for value,lo,hi,quantum in ((duty,0,90,2),(target,50,210,2),(loop_period_us,100,10000,1),
                              (cut_kpa,100,300,2),(protection_rpm,0,6500,100)):
        if type(value)is not int or not lo<=value<=hi or value%quantum:raise ValueError('Unrepresentable production boost profile')
    if type(default_unarmed_compare)is not bool:raise ValueError('Timer negative control must be boolean')
    # Declared benchmark datum:500cc/cylinder,300cc/min gives10.7ms. This
    # quantization includes the historical450cc/cylinder ->9.6ms fixture.
    raw=round(107*geometry.displacement_cc/(500*geometry.cylinders))
    if not 1<=raw<=255:raise ValueError('Required fuel is outside the production0.1ms byte domain')
    return raw


class SpeeduinoProfilesTurboRuntime(SpeeduinoProfilesRuntime):
    sensors=SpeeduinoTurboRuntime.sensors
    boost_status=SpeeduinoTurboRuntime.boost_status

    def __init__(self,executable,geometry,engine_mode='sequential',mode='off',duty=40,target=150,
                 default_unarmed_compare=False,loop_period_us=1000,cut_kpa=220,protection_rpm=6500,wiring_order=None):
        raw=validate_profile(geometry,engine_mode,mode,duty,target,default_unarmed_compare,loop_period_us,cut_kpa,protection_rpm)
        order=geometry.firing_order if wiring_order is None else tuple(wiring_order);n=geometry.cylinders
        if len(order)!=n or any(type(c)is not int for c in order)or order[0]!=1 or sorted(order)!=list(range(1,n+1)):
            raise ValueError('Native wiring must be a complete active-cylinder permutation starting at1')
        executable=Path(executable).resolve();manifest=executable.with_name('build-manifest.json');model=json.loads(manifest.read_text())
        if (model['scope']!=SCOPE or model['unit_test']or model['speeduino_sha']!=PIN or model['timer_counter_bits']!=32 or
                model['base_binary_sha256']!=BASE_SHA or model['numerical_relink_sha256']!=BASE_SHA or digest(executable)!=model['binary_sha256']):
            raise RuntimeError('Expanded boost reference attestation failed')
        for name,expected in model['fixture_sources'].items():
            if digest(ROOT/name)!=expected:raise RuntimeError('Expanded boost fixture source changed: '+name)
        for name,expected in model['generated_sources'].items():
            if digest(Path(name))!=expected:raise RuntimeError('Generated fixture symbol bridge changed')
        self.geometry=geometry;self.mode=engine_mode;self.timer_bits=32;self.required_fuel_raw=raw
        self.sequential=engine_mode=='sequential';self.semi_sequential=engine_mode=='semi'
        self.secondary_channels=None;self.edge_modes={};self.last_status={};self.buffer=b'';self.now=0;self.process=None
        self.mode_history=[];self._last_mode=None
        self.profile=dict(scope=SCOPE,speeduino_sha=PIN,binary_sha256=model['binary_sha256'],manifest_sha256=digest(manifest),
            requested_mode=engine_mode,physical_geometry=geometry.summary(),per_tooth=True,reqFuel_point1ms=raw,
            required_fuel_quantization='Nearest0.1ms, ties to even;10.7ms reference datum per500cc/cylinder at300cc/min',
            mode_history=self.mode_history,limitations=model['limits'],wiring_order=list(order))
        coil_order=tuple(order[(i*((n+1)//2))%n]for i in range(n))if engine_mode!='sequential'and n in (3,5)else order
        self.pin_map={};wiring=[]
        for i,pin in enumerate(NATIVE_PINS):
            index=i%8;physical=(order if i<8 else coil_order)[index]-1 if index<n else index
            channel=(INJECTOR_CHANNELS if i<8 else COIL_CHANNELS)[physical];self.pin_map[pin]=channel
            wiring.append(dict(native_pin=pin,kind='injector'if i<8 else'coil',native_ordinal=index+1,
                               physical_cylinder=physical+1,logical_channel=channel,active=index<n))
        issues=[]
        if engine_mode!='sequential'and n==2:issues.append('WASTED fallback0/180deg does not represent the declared equal-fire two-cylinder COP geometry')
        if engine_mode!='sequential'and n==7:issues.append('WASTED fallback has only3+3schedules for7physical cylinders')
        self.profile.update(native_wiring=wiring,physical_geometry_issues=issues,representable_ignition_geometry=not issues,
            injection_bank_caveat='Five-cylinder semi callbacks pair native pins3+5; retain actual phases'if engine_mode!='sequential'and n==5 else None)
        args=[str(executable),str(n),engine_mode,mode,str(duty),str(target),
              '--required-fuel='+str(raw),'--loop-period-us='+str(loop_period_us),
              '--cut-kpa='+str(cut_kpa),'--protect-rpm100='+str(protection_rpm//100)]
        if default_unarmed_compare:args.append('--default-unarmed-compare')
        try:
            self.process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
            if self._line()!=('ready_profiles_turbo 19 18'if self.sequential else'ready_profiles_turbo 19 0'):
                raise RuntimeError('Unexpected expanded turbo greeting')
            line=self._line()
            if not line.startswith('geometry '):raise RuntimeError('Missing expanded turbo startup geometry')
            initial=json.loads(line.split(' ',1)[1]);self._validate_geometry(initial)
            self.profile['effective_before_start']=initial;self._observe_mode(0,initial,source='setup')
            lines=self.command('boostprofile')
            if len(lines)!=1 or lines[0].split()[0]!='boostprofile':raise RuntimeError('Missing actual boost setup readback')
            values=list(map(int,lines[0].split()[1:]));expected=[int(mode!='off'),int(mode=='closed_loop'),12,cut_kpa//2,0,90,10,0,0,100,1000,
                int(default_unarmed_compare),loop_period_us,1,cut_kpa,protection_rpm//100,raw]
            if len(values)!=20 or values[:17]!=expected:raise RuntimeError('Production boost setup readback differs')
            boost_pin,port,mask=values[17:]
            if not 0<=boost_pin<70 or boost_pin in NATIVE_PINS or not mask or (port,mask)in zip(initial['native_port_ids'],initial['native_port_masks']):
                raise RuntimeError('Boost pin aliases a native engine output')
            maps=self.command('boostmaps');axis=[0,10,20,40,80,120,160,200];rpm=[5+10*i for i in range(8)];bins=[i*25 for i in range(9)]
            wanted=rpm+axis+[target//2 if mode=='closed_loop'else duty//2]*64+rpm+[50+25*i for i in range(8)]+[duty*2]*64+bins+[math.floor(100*298.15/(273.15+i-40)+.5)for i in bins]
            if len(maps)!=1 or maps[0].split()[0]!='boostmaps'or list(map(int,maps[0].split()[1:]))!=wanted:
                raise RuntimeError('Production boost/density tables differ')
            self.profile.update(boost_raw=values,boost_mode=mode,frequency_hz=24,target_kpa=target,duty_pct=duty,cut_kpa=cut_kpa,
                protection_max_rpm=protection_rpm,boost_and_density_raw_maps=wanted,native_boost_pin=boost_pin,
                main_loop_period_us=loop_period_us,main_loop_clock='Fixed absolute calendar, zero modeledCPU/IRQ cost',
                native_timer_initial_compare='UINT32_MAX negative control'if default_unarmed_compare else'explicit zero fixture',
                halt_scope='Explicit engine-only fixture stop; production boost timer/demand remain independent',physical_execution=False)
        except BaseException:self.close();raise

    def _validate_geometry(self,g):
        n=self.geometry.cylinders
        if (g['requested_cylinders']!=n or g['cylinders']!=n or g['injectors']!=n or g['reqFuel_point1ms']!=self.required_fuel_raw or
            g['divider']!=n//2 or(not self.sequential and g['n_squirts']!=2)or g['per_tooth']!=1 or
            tuple(g['native_output_pins'])!=NATIVE_PINS or len(set(zip(g['native_port_ids'],g['native_port_masks'])))!=16 or
            any(not v for v in g['native_port_masks'])or g['requested_spark_mode']!=(3 if self.sequential else 2)or
            g['requested_injection_layout']!=(3 if self.sequential else 1)):
            raise RuntimeError('Expanded turbo profile did not survive actual setup/rebinding')

    def _edges(self,lines):
        result=[]
        for line in lines:
            if line.startswith('boostedge '):
                fields=line.split()
                if len(fields)!=3 or fields[2]not in ('0','1'):raise RuntimeError('Invalid actual boost edge')
                stamp=int(fields[1])
                if not 0<=stamp<=self.now:raise RuntimeError('Boost edge outside bounded virtual clock')
                result.append((stamp,9,fields[2]=='1',None,None))
            else:result.extend(super()._edges([line]))
        return result

    def advance(self,time_us,tooth=False):
        if type(time_us)is not int or not self.now<=time_us<=60000000 or type(tooth)is not bool:raise ValueError('Invalid bounded native advance')
        previous=self.now;self.now=time_us
        result=self._edges(self.command(('tooth'if tooth else'advance')+' '+str(time_us)))
        for row in result:
            if not previous<=row[0]<=time_us:raise RuntimeError('Output outside ordered coupling interval')
            previous=row[0]
        return result

    def input_edge(self,time_us,channel,high):
        if type(time_us)is not int or not self.now<=time_us<=60000000 or type(channel)is not int or channel not in (0,1)or type(high)is not bool or channel==1 and not self.sequential:
            raise ValueError('Invalid configured native trigger edge')
        previous=self.now;self.now=time_us;rows=self._edges(self.command(f'input {time_us} {channel} {int(high)}'))
        for row in rows:
            if not previous<=row[0]<=time_us:raise RuntimeError('Input response outside ordered coupling interval')
            previous=row[0]
        return rows

    def halt(self):
        result=self._edges(self.command('halt'))
        if any(row[0]!=self.now or row[2]for row in result):raise RuntimeError('Unexpected explicit engine-halt edge')
        return result
