"""Export source-labelled figures from completed coupled turbo experiments."""
import argparse
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS={'ours':'#087eaf','speeduino':'#cb6a18'}
LABELS={'ours':'Our ECU','speeduino':'Production Speeduino'}


def read(record):
    return [json.loads(line) for line in (Path(record['path'])/'trace.jsonl').read_text().splitlines()]


def select(records,**wanted):
    rows=[row for row in records if all(row[key]==value for key,value in wanted.items())]
    if len(rows)!=1:
        raise ValueError('Expected one declared experiment: '+str(wanted))
    return rows[0]


def plot(summary,output):
    output.mkdir(parents=True,exist_ok=False)
    records=json.loads(summary.read_text())['records']
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.22,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(3,2,figsize=(13,10),sharex=True,layout='constrained')
    fields=[('Free crank (rpm)',lambda r:r['plant_rpm']),
            ('Intake manifold (kPa absolute)',lambda r:r['gas']['map_kpa']),
            ('Turbo shaft (thousand rpm)',lambda r:r['gas']['turbo_rad_s']*30/math.pi/1000),
            ('Wastegate opening (%)',lambda r:r['valve']['wastegate_opening']*100),
            ('Solenoid mechanical position (%)',lambda r:r['valve']['coil']['opening_pct']),
            ('Intake gas temperature (°C)',lambda r:r['gas']['temperature_k']-273.15)]
    for controller in COLORS:
        for mode,style in [('open_loop','-'),('closed_loop','--')]:
            record=select(records,controller=controller,mode=mode,scenario='nominal',actuator='normal',step_us=500,requested_duty_pct=40,cut_kpa=220)
            rows=read(record);time=[r['time_us']/1e6 for r in rows]
            label=LABELS[controller]+' / '+('open40%' if mode=='open_loop' else 'closed150kPa')
            for axis,(ylabel,function) in zip(axes.flat,fields):
                axis.plot(time,[function(r) for r in rows],style,color=COLORS[controller],label=label,linewidth=1.5)
                axis.set_ylabel(ylabel)
    axes[0,1].axhline(150,color='#555555',linestyle=':',linewidth=1,label='Closed-loop target')
    for axis in axes[-1]:axis.set_xlabel('Simulated time (s)')
    for axis in axes.flat:
        axis.axvline(2.5,color='#888888',linestyle=':',linewidth=.8)
        axis.axvline(3,color='#888888',linestyle=':',linewidth=.8)
        axis.axvline(4,color='#888888',linestyle=':',linewidth=.8)
    axes[0,0].legend(fontsize=8,loc='upper left')
    fig.suptitle('Independent native controller runs on a source-backed research turbo model\nStarter ends2.5s; throttle60% at3s; load70Nm at4s. Uncalibrated; physical outputs inhibited.',fontsize=12)
    fig.savefig(output/'nominal.png',dpi=150);plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for controller,color in COLORS.items():
        label=LABELS[controller]
        for scenario,axis,ylabel,function in [
            ('trigger_dropout',axes[0,0],'Free crank (rpm)',lambda r:r['plant_rpm']),
            ('map_high_rail',axes[0,1],'Supplied / held MAP and plant MAP (kPa)',lambda r:r['control'].get('map_kpa',r['sensor_input']['map_kpa'])),
            ('throttle_blip',axes[1,0],'Intake temperature (°C)',lambda r:r['gas']['temperature_k']-273.15),
        ]:
            record=select(records,controller=controller,mode='open_loop',scenario=scenario,actuator='normal',step_us=500)
            rows=read(record);time=[r['time_us']/1e6 for r in rows]
            axis.plot(time,[function(r) for r in rows],color=color,label=label,linewidth=1.6)
            axis.set_ylabel(ylabel)
            if scenario=='map_high_rail':axis.plot(time,[r['gas']['map_kpa'] for r in rows],color=color,linestyle=':',label=label+' plant')
            if scenario=='throttle_blip' and controller=='speeduino':
                axis.plot(time,[r['control']['iat_c'] for r in rows],color=color,linestyle=':',label='Reference IAT readback')
        record=select(records,controller=controller,mode='open_loop',scenario='nominal',actuator='disconnected',step_us=500)
        rows=read(record);time=[r['time_us']/1e6 for r in rows]
        axes[1,1].plot(time,[r['gas']['map_kpa'] for r in rows],color=color,label=label,linewidth=1.6)
    for axis,title,end in [(axes[0,0],'Crank capture loss',6.3),(axes[0,1],'MAP ADC rail',6.25),(axes[1,0],'Throttle close / reopen',6.4)]:
        axis.axvspan(6,end,color='#aaaaaa',alpha=.2);axis.set_title(title);axis.set_xlim(5.5,8)
    axes[1,1].set_title('Disconnected boost solenoid');axes[1,1].set_ylabel('Intake manifold (kPa absolute)')
    for axis in axes.flat:axis.legend(fontsize=8);axis.set_xlabel('Simulated time (s)')
    fig.suptitle('Declared fault and transient fixtures, separate plant histories\nInput rails, production held readings and gas state are distinct. No physical qualification.',fontsize=12)
    fig.savefig(output/'faults.png',dpi=150);plt.close(fig)

    fig,axes=plt.subplots(3,1,figsize=(12,10),layout='constrained')
    for controller,color in COLORS.items():
        record=select(records,controller=controller,mode='open_loop',scenario='nominal',actuator='normal',step_us=500,cut_kpa=140)
        rows=read(record);time=[r['time_us']/1e6 for r in rows]
        axes[0].plot(time,[r['gas']['map_kpa'] for r in rows],color=color,label=LABELS[controller])
        axes[1].plot(time,[r['plant_rpm'] for r in rows],color=color,label=LABELS[controller])
        charged=select(records,controller=controller,mode='open_loop',scenario='charged_map_rail',actuator='normal',step_us=500)
        folder=Path(charged['path']);result=json.loads((folder/'result.json').read_text())
        start=result['stimulus']['charged_fault_start_us'];channel=result['stimulus']['charged_channels_at_start'][0]
        edges=[json.loads(line) for line in (folder/'edges.jsonl').read_text().splitlines()]
        offset=0 if controller=='ours' else 2;level=False;times=[-4.];levels=[]
        for row in edges:
            if row['ch']!=channel:continue
            relative=(row['time_us']-start)/1000
            if relative< -4:level=row['high'];continue
            if relative>4:break
            if not levels:levels.append(int(level)+offset)
            times.append(relative);levels.append(int(row['high'])+offset)
        if not levels:levels.append(int(level)+offset)
        times.append(4.);levels.append(levels[-1])
        axes[2].step(times,levels,where='post',color=color,label=LABELS[controller]+' coil channel'+str(channel))
    axes[0].axhline(140,color='#555555',linestyle=':',label='Declared140kPa threshold')
    axes[0].set_ylabel('Research gas MAP (kPa absolute)');axes[0].set_xlabel('Simulated time (s)')
    axes[0].set_title('Actual model pressure crossing; no supplied MAP override')
    axes[1].set_ylabel('Free crank (rpm)');axes[1].set_xlabel('Simulated time (s)')
    axes[1].set_title('Overboost response with reference0RPM full-cut masks; existing pulses may finish')
    axes[2].axvline(0,color='#555555',linestyle=':');axes[2].set_xlim(-4,4)
    axes[2].set_yticks((0,1,2,3),('Own low','Own high','Reference low','Reference high'))
    axes[2].set_xlabel('Time relative to each charged-coil fault (ms)')
    axes[2].set_title('Actual virtual GPIO transitions around the condition-triggered sensor fault')
    for axis in axes:axis.legend(fontsize=8)
    fig.suptitle('Reachable shutdown experiments with a common falling-edge actuator model\nStored coil charge can discharge after a cut request. Native SIL; physical outputs inhibited.',fontsize=12)
    fig.savefig(output/'critical.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();plot(args.summary,args.output)
