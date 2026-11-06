"""Explicit16-GPIO benchmark runtime for genuine pinned production Speeduino.

This is a new native board fixture, not an extension of the v0.4 physical board.
All edges are observed GPIO changes. No missing output is synthesized or copied
to a second cylinder. Only the documented basic benchmark IPC is supported.
"""
import hashlib
import json
from pathlib import Path
import subprocess
from engine_geometry import EngineGeometry,INJECTOR_CHANNELS,COIL_CHANNELS
from speeduino_runtime import ROOT,SpeeduinoRuntime

PIN='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'
BASE_SHA='046389d754c996c34cb7e7171b1e42088f5ae6c0615133a3c5e74743f9f6d52c'
NATIVE_PINS=(22,23,25,26,27,28,29,30,31,32,33,34,35,36,37,38)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SpeeduinoProfilesRuntime:
    # Share bounded IPC and sensor/clock stimulus, never engine algorithms or
    # the old four-cylinder pin translation/configuration API.
    _line=SpeeduinoRuntime._line
    command=SpeeduinoRuntime.command
    sensors=SpeeduinoRuntime.sensors
    advance=SpeeduinoRuntime.advance
    input_edge=SpeeduinoRuntime.input_edge
    close=SpeeduinoRuntime.close

    def __init__(self,executable,geometry,mode='sequential',per_tooth=False,wiring_order=None):
        if not isinstance(geometry,EngineGeometry):raise ValueError('Explicit physical EngineGeometry required')
        if mode not in ('sequential','wasted_cop','semi') or type(per_tooth)is not bool:raise ValueError('Invalid fixture mode')
        if geometry.displacement_cc!=500*geometry.cylinders or geometry.tooth1_tdc_deg!=90 or geometry.cam_edge_deg!=540:
            raise ValueError('Reference fixture requires500cc/cylinder,90deg physical tooth1 and540deg cam')
        executable=Path(executable).resolve();manifest=executable.with_name('build-manifest.json')
        model=json.loads(manifest.read_text())
        if (model['scope']!='production_setup_and_sixteen_distinct_native_outputs' or model['unit_test']
                or model['speeduino_sha']!=PIN or model['timer_counter_bits']!=32
                or model['base_binary_sha256']!=BASE_SHA or model['numerical_relink_sha256']!=BASE_SHA
                or digest(executable)!=model['binary_sha256']):
            raise RuntimeError('Expanded production fixture attestation failed')
        for name,expected in model['fixture_sources'].items():
            if digest(ROOT/name)!=expected:raise RuntimeError('Expanded fixture source changed: '+name)
        self.geometry=geometry;self.mode=mode;self.timer_bits=32
        self.sequential=mode=='sequential';self.semi_sequential=mode=='semi'
        self.secondary_channels=None;self.edge_modes={};self.last_status={}
        self.buffer=b'';self.now=0;self.process=None
        self.mode_history=[];self._last_mode=None
        self.profile=dict(scope=model['scope'],speeduino_sha=PIN,binary_sha256=model['binary_sha256'],
            manifest_sha256=digest(manifest),requested_mode=mode,physical_geometry=geometry.summary(),
            per_tooth=per_tooth,reqFuel_point1ms=107,mode_history=self.mode_history,
            limitations=model['limits'])
        # Odd-cylinder WASTED angles are spaced360/N. Wire the actual pins to
        # physical TDCs modulo360. This permutation is static and disclosed.
        order=geometry.firing_order if wiring_order is None else tuple(wiring_order);n=geometry.cylinders
        if len(order)!=n or any(type(c)is not int for c in order) or order[0]!=1 or sorted(order)!=list(range(1,n+1)):
            raise ValueError('Native output wiring must start at1 and contain each physical cylinder once')
        self.profile['wiring_order']=list(order)
        coil_order=tuple(order[(i*((n+1)//2))%n] for i in range(n)) if mode!='sequential' and n in (3,5) else order
        self.pin_map={}
        wiring=[]
        for i,pin in enumerate(NATIVE_PINS):
            index=i%8
            physical=(order if i<8 else coil_order)[index]-1 if index<n else index
            channel=(INJECTOR_CHANNELS if i<8 else COIL_CHANNELS)[physical]
            self.pin_map[pin]=channel
            wiring.append(dict(native_pin=pin,kind='injector'if i<8 else'coil',native_ordinal=index+1,
                               physical_cylinder=physical+1,logical_channel=channel,active=index<n))
        self.profile['native_wiring']=wiring
        issues=[]
        if mode!='sequential' and n==2:
            issues.append('Fallback WASTED has0/180deg ignition schedules; equal-fire two-cylinder four-stroke TDCs coincide modulo360')
        if mode!='sequential' and n==7:
            issues.append('Fallback WASTED has only3 ignition schedules and3 primary injection schedules for7 physical cylinders')
        self.profile.update(physical_geometry_issues=issues,representable_ignition_geometry=not issues,
            injection_bank_caveat='Five-cylinder semi callbacks pair native pins3+5; retain actual phases'if mode!='sequential'and n==5 else None)
        try:
            self.process=subprocess.Popen([str(executable),str(n),mode,*(['--per-tooth']if per_tooth else[])],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
            if self._line()!=('ready_profiles 19 18'if self.sequential else'ready_profiles 19 0'):
                raise RuntimeError('Unexpected expanded reference greeting')
            line=self._line()
            if not line.startswith('geometry '):raise RuntimeError('Missing expanded reference startup profile')
            initial=json.loads(line.split(' ',1)[1]);self._validate_geometry(initial)
            self.profile['effective_before_start']=initial
            self._observe_mode(0,initial,source='setup')
        except BaseException:self.close();raise

    def _validate_geometry(self,g):
        n=self.geometry.cylinders
        if (g['requested_cylinders']!=n or g['cylinders']!=n or g['injectors']!=n
                or g['reqFuel_point1ms']!=107 or g['divider']!=n//2
                or (not self.sequential and g['n_squirts']!=2)
                or bool(g['per_tooth'])!=self.profile['per_tooth']
                or tuple(g['native_output_pins'])!=NATIVE_PINS
                or len(set(zip(g['native_port_ids'],g['native_port_masks'])))!=16
                or any(not v for v in g['native_port_masks'])
                or g['requested_spark_mode']!=(3 if self.sequential else 2)
                or g['requested_injection_layout']!=(3 if self.sequential else 1)):
            raise RuntimeError('Expanded reference profile did not survive setup/rebinding')

    def _observe_mode(self,time_us,g,source):
        keys=('sync_status','ignition_span_deg','injection_span_deg','effective_injection_layout',
              'ignition_outputs','primary_injector_outputs')
        mode={k:g[k]for k in keys};identity=tuple(mode.values())
        if identity!=self._last_mode:
            self.mode_history.append(dict(time_us=time_us,source=source,**mode));self._last_mode=identity
        return dict(**mode,effective_sequential=g['sync_status']==2 and g['ignition_span_deg']==720,
                    ignition_cycle_deg=g['ignition_span_deg'])

    def geometry_status(self):
        lines=self.command('geometry')
        if len(lines)!=1 or not lines[0].startswith('geometry '):raise RuntimeError('Missing expanded effective geometry')
        result=json.loads(lines[0].split(' ',1)[1]);self._validate_geometry(result)
        self._observe_mode(self.now,result,source='status');return result

    def status(self):
        result=SpeeduinoRuntime.status(self)
        effective=self.geometry_status();result['reference_effective']=effective
        self.profile['effective_latest']=effective
        return result

    def _edges(self,lines):
        result=[]
        for line in lines:
            fields=line.split()
            if len(fields)!=10 or fields[0]!='edge':raise RuntimeError('Malformed expanded reference edge: '+line)
            timestamp,pin,high,sync,ign_span,inj_span,layout,ign_outputs,inj_outputs=map(int,fields[1:])
            if pin not in self.pin_map or high not in (0,1) or not 0<=timestamp<=self.now:
                raise RuntimeError('Invalid expanded reference edge')
            channel=self.pin_map[pin]
            if channel not in self.geometry.injector_channels+self.geometry.coil_channels:
                raise RuntimeError('Production output outside the active physical profile')
            mode=self._observe_mode(timestamp,dict(sync_status=sync,ignition_span_deg=ign_span,
                injection_span_deg=inj_span,effective_injection_layout=layout,ignition_outputs=ign_outputs,
                primary_injector_outputs=inj_outputs),source='edge')
            self.edge_modes[(timestamp,channel,bool(high))]=mode
            result.append((timestamp,channel,bool(high),None,None))
        return result

    def halt(self):
        return [(us,ch,high)for us,ch,high,_,_ in self._edges(self.command('halt'))]
