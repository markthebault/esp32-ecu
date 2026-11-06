#!/usr/bin/env python3
"""Run conditional IAC-DRAFT2 fault experiments in real ngspice.

This is a separately authored lumped circuit, not a manufacturer macro-model,
PCB parasitic extraction, closed-loop engine run or physical qualification.
The independent engine/Speeduino comparison remains in idle-control evidence.
"""
import argparse
import gzip
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCES=['tools/run_idle_circuit.py','hardware/idle-isolated/net_contract.json',
         'hardware/idle-isolated/isolated.kicad_pcb','hardware/a5-idle-interface/net_contract.json',
         'hardware/a5-idle-interface/esp32-ecu.kicad_pcb','firmware/include/ecu/idle_hardware.hpp']


def contract_binding():
    """Reject a stale circuit's fixed component values, without deriving its model."""
    accessory=json.loads((ROOT/SOURCES[1]).read_text())
    actual={x['reference']:x for x in accessory['parts']}
    expected={'R1':'1k 1%','R2':'2k2 1%','R3':'357R 1%','R4':'357R 1%',
              'R5':'100k','R6':'100k','R7':'1k','R8':'1k','R9':'1k','R10':'10k',
              'R11':'1k','R12':'4k7','R13':'33R','R14':'10k','R15':'120R 1%','R16':'374R 1%'}
    assert all(actual[k]['value']==v for k,v in expected.items()),'Circuit resistor values are stale'
    assert actual['NT1']['pins']=={'1':'ACT_GND','2':'LOGIC_GND'}
    assert actual['J1']['pins']=={'1':'IDLE_CMD','2':'RUN_5V','3':'CARRIER_5V','4':'CARRIER_GND'}
    assert actual['Q1']['pins']=={'1':'GATE','2':'IAC_LS','3':'ACT_GND'}
    carrier=json.loads((ROOT/SOURCES[3]).read_text());cp={x['ref']:x for x in carrier['parts']}
    assert all(cp[k]['value']==v for k,v in {'R47':'10k','R50':'1k','R53':'10k','R154':'2k2 1%'}.items())
    assert cp['J21']['pins']=={'1':'IDLE_CMD','2':'RUN_5V','3':'+5V','4':'GND'}
    return dict(accessory_resistors=expected,carrier_resistors={k:cp[k]['value'] for k in ('R47','R50','R53','R154')},
                qualification='Literal value/interface consistency only; no device dynamics derived from CAD')


@dataclass
class Case:
    name: str
    fault: str = 'none'
    supply: float = 12
    carrier: float = 5
    run: float = 5
    command: float = 3.3
    led_r_scale: float = 1
    bridge: bool = False
    opto_tau_us: float = .2
    pg_assert_us: float = 10
    pulse_us: float = 0
    cold: bool = False
    maximum_step_us: float = .5


def deck(c):
    stop = .8 if c.cold else (.0022 if c.pulse_us else .008)
    save_from = .0019 if c.pulse_us else 0
    dt = c.maximum_step_us * 1e-6
    command = f'DC {c.command}'
    if c.pulse_us:
        command = f'PULSE(0 {c.command} 2m 10n 10n {c.pulse_us*1e-6} 100m)'
    elif c.fault in {'command_low', 'drain_short'}:
        command = f'PWL(0 {c.command} 4m {c.command} 4.00001m 0)'
    run = f'DC {c.run}' if c.fault != 'run_low' else f'PWL(0 {c.run} 4m {c.run} 4.00001m 0)'
    supply = f'DC {c.supply}' if not c.cold else f'PWL(0 0 10m {c.supply})'
    j1power = 'PWL(0 1 4m 1 4.00001m 0)' if c.fault == 'carrier_power_open' else 'DC 1'
    j1return = 'PWL(0 1 4m 1 4.00001m 0)' if c.fault == 'carrier_return_open' else 'DC 1'
    actreturn = 'PWL(0 1 4m 1 4.00001m 0)' if c.fault == 'actuator_return_open' else 'DC 1'
    actpower = 'PWL(0 1 4m 1 4.00001m 0)' if c.fault == 'actuator_power_open' else 'DC 1'
    railfault = 'PWL(0 0 4m 0 4.00001m 1)' if c.fault == 'rail_drop' else 'DC 0'
    drainshort = 'PWL(0 0 4m 0 4.00001m 1)' if c.fault == 'drain_short' else 'DC 0'
    # Warm conditions are declared initial states. The cold-start case initializes
    # all capacitors at zero and includes an actual ramp and release interval.
    pwm_on = not c.pulse_us and c.command > 0
    ic = '' if c.cold else (f'.ic v(rail)=5.1645 v(pgstate)=1 v(pwf)={int(pwm_on)} '
        f'v(runf)={int(c.run>0)} v(pwmn)={.3826 if pwm_on else 5.1645} '
        f'v(runn)={.3826 if c.run>0 else 5.1645} v(vin)={c.supply} '
        f'v(drain)={c.supply} v(winding)={c.supply} v(gate)=0 v(cin5)={c.carrier}')
    return f'''IAC-DRAFT2 conditional lumped fault experiment / {c.name}
* Explicit assumptions, NOT vendor models. See ../results.json and source code.
.param VREG=5.1645 TAU={c.opto_tau_us*1e-6} PGDOWN={c.pg_assert_us*1e-6/.69314718056}
.options reltol=1e-5 abstol=1e-10 vntol=1e-7 method=gear
Vbat battery 0 {supply}
Vactpowerctl apctl 0 {actpower}
Sactpower battery vin apctl 0 WIRE
Rvinleak vin 0 1e12
Vcarrier c5 cg DC {c.carrier}
Vcarrier_reference cg 0 0
Vcarrier_return crwire cg 0
Vgpio gpiosrc cg {command}
Rgpio gpiosrc gpio 30
R154 gpio cg 2200
Vrun runsrc cg {run}
Rrun runsrc run 47
Rexistingrun run cg 10000
R50 run mainin 1000
R53 mainin cg 10000
* Conditional normal Q7 input-current proxy only. ST's500uA bound is at10V/25C,
* not this5V/full-temperature case, and fault sink can be20mA. No loading proof.
Bq7input mainin cg I=min(max(v(mainin,cg),0)/5,1)*500u
Rhctinputs run cg 500k
Vj1power pwrctl 0 {j1power}
Vj1return cgctl 0 {j1return}
Vactreturnctl agctl 0 {actreturn}
Sinputpower c5 cin5 pwrctl 0 WIRE
Sinputreturn gin crwire cgctl 0 WIRE
Sactreturn ag actret agctl 0 WIRE
Vactreturn actret 0 0
Rbridge ag gin {'.01' if c.bridge else '1e12'}
* J1 input buffers, actual resistor values and explicit generic BJT model.
R1 gpio pb 1000
R2 run rb 2200
R3 cin5 pla {357*c.led_r_scale}
R4 cin5 rla {357*c.led_r_scale}
Vpwmled pla pl 0
Vrunled rla rl 0
Dpwled pl pc LED
Drunled rl rc LED
Q2 pc pb gin NPNGEN
Q3 rc rb gin NPNGEN
R5 pb gin 100k
R6 rb gin 100k
D3 gin pb DIODE
D4 gin rb DIODE
C9 cin5 gin 100n
* No galvanic connection is introduced by optical transfer control variables.
Bpwr rawpw ag V=(i(Vpwmled)>0.005 ? 1 : 0)
Brun rawrun ag V=(i(Vrunled)>0.005 ? 1 : 0)
Rpwdelay rawpw pwf 1000
Crpw pwf ag {{TAU/1000}}
Rrundelay rawrun runf 1000
Crrun runf ag {{TAU/1000}}
Spwout pwmn ag pwf ag OPTO
Srunout runn ag runf ag OPTO
R7 rail pwmn 1000
R8 rail runn 1000
Cpwload pwmn ag 100p
Crunload runn ag 100p
* HCT02 conditional transfer. Below4.5V choose HIGH as an adverse sensitivity,
* not a claim of known invalid-rail behavior. The local supervisor must disable.
Bhct nor ag V=(v(rail,ag)>=4.5 ? (v(pwmn,ag)<0.8 && v(runn,ag)<0.8 ? v(rail,ag) : 0) : v(rail,ag))
R9 nor ina 1000
R10 ina ag 10000
Cina ina ag 15p
* MCP100 timer approximation: threshold4.725V; declared assertion10us typical,
* release350ms. First-order state crossing0.5, not an exact internal timer model.
Bpgtimer pgstate ag I=(v(rail,ag)>4.725 ? 1n*(v(pgstate,ag)-1)/0.504943264 : 1n*v(pgstate,ag)/PGDOWN)
Cpgstate pgstate ag 1n
Bpg pgout ag V=(v(pgstate,ag)>0.5 ? max(v(rail,ag),0) : 0)
R11 pgout ena 1000
R12 ena ag 4700
* Regulator draws its output current from the actual actuator branch. It is a
* bounded ideal pass-current approximation with3V headroom, not LM317 dynamics.
Breg vin rail I=max(min((min(VREG,max(v(vin,ag)-3,0))-v(rail,ag))*5,0.2),0)
R15 rail adj 120
R16 adj ag 374
Rquiescent rail ag 500
D2 rail vin DIODE
C6 vin ag 100u
C7 rail ag 22u
C8 vin ag 100n
C1 rail ag 100n
C2 rail ag 100n
C3 rail ag 100n
C5 rail ag 100n
C4 rail ag 100n
C10 rail ag 1u
* Force a known rail collapse, independent of unmodelled regulator dynamics.
Vrailfault rdropctl 0 {railfault}
Vlowrail lowrail ag 4.2
Srailfault rail lowrail rdropctl 0 CLAMP
* Gate driver sources/sinks actual gate capacitance from local supply/return.
* Below valid supply operation is deliberately allowed down to3.5V, adverse.
Bgcmd gcmd ag V=(v(ina,ag)>2.4 && v(ena,ag)>2.4 && v(rail,ag)>3.5 ? 1 : 0)
Bngcmd ngcmd ag V=(v(gcmd,ag)>0.5 ? 0 : 1)
Shigh rail drive gcmd ag DRIVER
Slow drive ag ngcmd ag DRIVER
R13 drive gate 33
R14 gate ag 10000
Cgate gate ag 2.5n
Cmiller gate drain 350p
* Generic level1 MOS channel and explicit flyback, not an IRLZ44N macro-model.
M1 drain gate ag ag FETGEN L=1u W=1u
Rcoil vin winding 8
Lcoil winding drain 12m
D1 drain vin FLYBACK
Vdrainshort shortctl 0 {drainshort}
Sdrainshort drain ag shortctl 0 CLAMP
.model WIRE SW(Ron=.01 Roff=1e9 Vt=.5 Vh=0)
.model CLAMP SW(Ron=.01 Roff=1e9 Vt=.5 Vh=0)
.model OPTO SW(Ron=80 Roff=1e9 Vt=.5 Vh=0)
.model DRIVER SW(Ron=2 Roff=1e9 Vt=.5 Vh=0)
.model NPNGEN NPN(Is=6.7e-15 Bf=150 Vaf=100 Cje=8p Cjc=4p Tf=.3n Tr=50n)
.model LED D(Is=1e-18 N=1.5 Rs=3 Cjo=15p)
.model DIODE D(Is=1e-9 N=1.7 Rs=.2 Cjo=5p)
.model FLYBACK D(Is=1e-8 N=1.2 Rs=.08 Cjo=100p)
.model FETGEN NMOS(Level=1 Vto=1.8 Kp=150 Lambda=.005 Rd=.02 Rs=.01)
{ic}
.control
set noaskquit
set wr_singlescale
set wr_vecnames
tran {dt} {stop} {save_from} {dt} uic
let rail_v=v(rail)-v(ag)
let gate_v=v(gate)-v(ag)
let ina_v=v(ina)-v(ag)
let ena_v=v(ena)-v(ag)
let drain_v=v(drain)-v(ag)
let gp_v=v(gpio)-v(cg)
wrdata trace.tsv rail_v gate_v ina_v ena_v drain_v gp_v v(ag) i(Lcoil) i(Vpwmled) i(Vrunled) i(Vcarrier_return) i(Vactreturn)
quit
.endc
.end
'''


def analyze(c, a):
    t = a[:, 0]
    # wr_singlescale order: time, rail, gate, ina, ena, drain, gpio, ag,
    # coil current, PWM LED, RUN LED, carrier-return current, actuator return.
    pre = (t > .003) & (t < .0039)
    late = t > (t[-1]-(.00005 if c.pulse_us else .0005))
    after = t > .0041
    def average(column, mask):
        x=t[mask];y=a[mask,column]
        return float(np.trapezoid(y,x)/(x[-1]-x[0])) if len(x)>1 else None
    result = dict(case=asdict(c), rows=len(t), first_saved_time_s=float(t[0]),final_time_s=float(t[-1]),
                  final_average_window_s=[float(t[late][0]),float(t[late][-1])],
                  pre_fault_current_a=average(8,pre),
                  final_current_a=average(8,late),
                  maximum_coil_current_a=float(np.max(a[:, 8])),
                  final_rail_v=average(1,late),
                  final_gate_v=average(2,late),
                  gpio_loaded_high_v=float(np.max(a[:, 6])),
                  maximum_pwm_led_a=float(np.max(a[:, 9])),
                  maximum_run_led_a=float(np.max(a[:, 10])),
                  maximum_carrier_return_a=float(np.max(np.abs(a[:, 11]))),
                  maximum_carrier_return_is_physical_bound=False,
                  late_carrier_return_a=float(np.trapezoid(np.abs(a[late,11]),t[late])/(t[late][-1]-t[late][0])),
                  late_actuator_ground_v=average(7,late),
                  observed_gate_high_us=float(np.trapezoid((a[:, 2] > 4).astype(float), t)*1e6),
                  maximum_gate_after_4p1ms_v=float(np.max(a[after, 2])) if np.any(after) else None)
    invalid = (a[:, 1] < 4.5) & (a[:, 2] > 2)
    result['gate_above_2v_while_rail_invalid_us'] = float(np.trapezoid(invalid.astype(float), t)*1e6)
    if c.cold:
        high = np.flatnonzero(a[:, 2] > 4)
        result['first_gate_high_s'] = float(t[high[0]]) if len(high) else None
    return result


def cases():
    result = [Case('warm_continuous'), Case('cold_start', cold=True, maximum_step_us=20)]
    for fault in ('command_low', 'run_low', 'carrier_power_open', 'carrier_return_open',
                  'actuator_return_open', 'actuator_power_open', 'rail_drop', 'drain_short'):
        result.append(Case(fault, fault=fault))
    result += [Case('return_open_deliberate_bridge', fault='actuator_return_open', bridge=True),
               Case('rail_drop_assertion_100us', fault='rail_drop', pg_assert_us=100)]
    for v, carrier, run, scale in ((9,4.75,4.4,1.01), (16,5.25,5.25,.99)):
        result.append(Case(f'supply_{v:g}v', supply=v, carrier=carrier, run=run, led_r_scale=scale))
    for us in (1,2,4,10,40):
        for tau in (.2,2):
            result.append(Case(f'pulse_{us}us_tau_{tau:g}us', pulse_us=us, opto_tau_us=tau,
                               maximum_step_us=.05))
    result.append(Case('pulse_1us_refinement', pulse_us=1, maximum_step_us=.025))
    return result


def validate(results):
    """Check conditional consequences, including controls that must stay unsafe."""
    r={x['case']['name']:x for x in results};checks=[]
    baseline=r['warm_continuous']['final_current_a']
    assert 1.4 < baseline < 1.6
    for name in ('command_low','run_low','carrier_power_open','carrier_return_open'):
        assert r[name]['final_gate_v'] < .1 and r[name]['final_current_a'] < baseline/10,name
        checks.append(name+': gate off and residual current decays in the declared model')
    assert r['actuator_return_open']['late_carrier_return_a'] < .05
    assert r['return_open_deliberate_bridge']['late_carrier_return_a'] > 1
    checks.append('Return-open negative control: deliberate domain bridge diverts >1A into the carrier return; intact barrier does not')
    assert r['drain_short']['final_gate_v'] < .1 and r['drain_short']['final_current_a'] > 1
    checks.append('Drain-source short keeps normal-current coil energized despite a low gate; a fuse alone cannot ensure closure')
    assert .15 < r['cold_start']['first_gate_high_s'] < .71
    checks.append('Cold-start model waits for its declared local rail/release timer')
    assert r['pulse_1us_tau_0.2us']['observed_gate_high_us'] > .4
    assert r['pulse_1us_tau_2us']['observed_gate_high_us'] < .1
    checks.append('The accepted1us command is transmitted or lost depending on assumed optical pole; no physical minimum is established')
    assert r['rail_drop_assertion_100us']['gate_above_2v_while_rail_invalid_us'] > r['rail_drop']['gate_above_2v_while_rail_invalid_us']*5
    checks.append('Longer assumed supervisor assertion leaves a larger invalid-rail gate interval; typical latency is not a maximum guarantee')
    a=r['pulse_1us_tau_0.2us']['maximum_coil_current_a'];b=r['pulse_1us_refinement']['maximum_coil_current_a']
    relative=abs(a-b)/max(a,b)
    assert relative < .05,relative
    return dict(passed=True,checks=checks,
                pulse_1us_maximum_current_relative_change_half_step=relative,
                qualification='Checks are conditional model consequences, not device/PCB/valve acceptance')


def plot(out, traces):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True, constrained_layout=True)
    for name, label in [('run_low','RUN cut'), ('actuator_return_open','Actuator return open'),
                        ('return_open_deliberate_bridge','Return open + deliberate ground bridge')]:
        a = traces[name]
        axes[0].plot(a[:,0]*1000,a[:,8],label=label)
        axes[1].plot(a[:,0]*1000,a[:,2],label=label)
        axes[2].plot(a[:,0]*1000,a[:,11],label=label)
    for ax, title, unit in zip(axes, ('Coil current','Gate relative to source','Carrier return current'),('A','V','A')):
        ax.set_ylabel(f'{title} ({unit})');ax.grid(alpha=.25);ax.axvline(4,color='gray',ls=':')
    axes[0].legend(fontsize=8);axes[-1].set_xlabel('Time (ms), fault at4ms')
    fig.suptitle('Conditional ngspice fault model, not physical qualification',fontsize=11)
    fig.savefig(out/'return-faults.png',dpi=160);fig.savefig(out/'return-faults.svg');plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(9,5),sharex=True, constrained_layout=True)
    for name in ('pulse_1us_tau_0.2us','pulse_1us_tau_2us','pulse_40us_tau_2us'):
        a=traces[name];axes[0].plot((a[:,0]-.002)*1e6,a[:,2],label=name.replace('pulse_',''))
        axes[1].plot((a[:,0]-.002)*1e6,a[:,8])
    axes[0].legend(fontsize=8);axes[0].set_ylabel('Gate (V)');axes[1].set_ylabel('Coil (A)')
    axes[1].set_xlim(-2,50);axes[1].set_xlabel('Time from input pulse (µs)')
    for ax in axes:ax.grid(alpha=.25)
    fig.suptitle('Short-pulse sensitivity to assumed optical delay, not a device bound',fontsize=11)
    fig.savefig(out/'pulse-sensitivity.png',dpi=160);fig.savefig(out/'pulse-sensitivity.svg');plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice',type=Path,required=True)
    parser.add_argument('--report-dir',type=Path,required=True)
    parser.add_argument('--case',action='append',default=[])
    args=parser.parse_args();binary=args.ngspice.resolve();out=args.report_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    binding=contract_binding()
    frozen={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}
    version=subprocess.check_output([str(binary),'--version'],text=True)
    results=[];traces={}
    for c in cases():
        if args.case and c.name not in args.case:continue
        d=out/c.name;d.mkdir();(d/'circuit.cir').write_text(deck(c))
        run=subprocess.run([str(binary),'-b','circuit.cir'],cwd=d,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        (d/'ngspice.log').write_text(run.stdout)
        assert run.returncode==0 and (d/'trace.tsv').exists(),(c.name,run.stdout[-3000:])
        a=np.loadtxt(d/'trace.tsv',skiprows=1)
        assert a.shape[1]==13 and np.all(np.isfinite(a)),(c.name,a.shape)
        target=.8 if c.cold else (.0022 if c.pulse_us else .008)
        assert a[-1,0] >= target-1e-8,'Incomplete transient'
        results.append(analyze(c,a));traces[c.name]=a
        with (d/'trace.tsv.gz').open('wb') as target:
            with gzip.GzipFile(filename='',fileobj=target,mode='wb',mtime=0) as stream:stream.write((d/'trace.tsv').read_bytes())
        (d/'trace.tsv').unlink()
        print(c.name,results[-1]['final_current_a'],results[-1]['final_gate_v'],flush=True)
    assert frozen=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},'Source changed during circuit run'
    report=dict(scope=__doc__,ngspice_version=version,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        source_sha256=frozen,source_unchanged_during_run=True,contract_consistency=binding,
        numpy_version=np.__version__,results=results,
        assumptions=dict(model='Separately authored conditional lumped network, no vendor macro-models',
          coil_ohm=8,coil_henry=.012,regulator='Ideal current-limited pass control,5.1645V target/3V headroom, no real stability/thermal model',
          input='Generic NPN/LED models with actual resistor values, R47/R50/R53 plus conditional500uA normalQ7 proxy and10uA HCT input proxy, not temperature/process/loaded-GPIO/RUN guarantees; Q7 fault sink unmodelled',
          optical='5mA detection,80ohm output,100pF load,first-order0.2us or2us pole, not6N137 timing bounds',
          supervisor='4.725V threshold,350ms release,10us or100us assumed assertion, actual maximum unspecified',
          logic='TTL0.8V low, below4.5V deliberately choose adverse high; actual invalid-rail state unknown',
          driver='Ideal2ohm switches,2.4V input threshold, assumed operation down to3.5V as adverse sensitivity',
          mosfet='Generic level1 NMOS, assumed2.5nF+350pF gate capacitance; notIRLZ44N switching/thermal data',
          layout='No PCB/lead/harness inductance extraction, no isolation capacitance, no EMI/surge, no case fit',
          warm='Declared rail/supervisor/opto/coil-terminal initial states; pulse traces retain1.9-2.2ms around their2ms edge, other warm cases0-8ms',
          cold='Carrier5V DC applied at time0 to an initially uncharged ideal100nF and ideal10mohm wires; actuator input ramps0-12V over10ms. Sampled carrier inrush is timestep/ideal-model dependent, not a physical current bound. Late currents are separate.',
          physical_outputs_enabled=False,engine_coupled=False))
    if not args.case:report['validation']=validate(results)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    if not args.case:plot(out,traces)


if __name__=='__main__':main()
