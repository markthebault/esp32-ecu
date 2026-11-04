#!/usr/bin/env python3
"""Standalone scientific figures from retained idle benchmark traces."""
import argparse,gzip,json,math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1]
COLORS={'ours':'#2673b8','speeduino':'#d36b28'}
def read(folder,name):return json.loads(gzip.decompress((folder/(name+'.json.gz')).read_bytes()))
def finish(fig,out,name):
 fig.tight_layout();fig.savefig(out/(name+'.svg'));fig.savefig(out/(name+'.png'),dpi=150);plt.close(fig)
def style(ax):ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
def duty_bins(run):
 events=[r for r in run['edges'] if r[1]==8];i=0;high=False;points=[]
 for left in range(0,round(run['summary']['duration_s']*1e6),100000):
  right=left+100000;last=left;area=0
  while i<len(events) and events[i][0]<right:
   stamp=events[i][0];area+=max(0,stamp-last)*high;last=max(left,stamp);high=events[i][2];i+=1
  area+=(right-last)*high;points.append(((left+right)/2e6,area/1000))
 return list(zip(*points))
def plot(matrix,followup,out):
 out.mkdir(parents=True,exist_ok=True);plt.rcParams.update({'font.size':10,'svg.fonttype':'none','axes.titlesize':12})
 fig,axes=plt.subplots(4,1,figsize=(9,9),sharex=True)
 for who in ('ours','speeduino'):
  run=read(matrix,who+'-load');trace=run['trace'];t=[r['time'] for r in trace];color=COLORS[who]
  axes[0].plot(t,[r['plant_rpm'] for r in trace],color=color,label={'ours':'Project','speeduino':'Speeduino'}[who])
  x,y=duty_bins(run);axes[1].plot(x,y,color=color,label={'ours':'Project','speeduino':'Speeduino'}[who])
  axes[2].plot(t,[r['ecu']['idle_valve']['opening_pct'] for r in trace],color=color)
  xs=[];ys=[]
  for a,b in zip(trace[::5],trace[5::5]):
   dt=b['time']-a['time'];energy=b['ecu']['idle_valve']['copper_j']-a['ecu']['idle_valve']['copper_j'];xs.append((a['time']+b['time'])/2);ys.append(math.sqrt(max(0,energy)/(8*dt)))
  axes[3].plot(xs,ys,color=color)
 for ax,label in zip(axes,['Shaft speed (RPM)','Virtual GPIO duty (%)\n100 ms bins','Model opening (%)','Model coil RMS (A)\n100 ms bins']):
  style(ax);ax.set_ylabel(label);ax.axvspan(5,9,alpha=.08,color='black')
 axes[0].axhline(900,color='#555555',ls=':',lw=1,label='900 RPM target');axes[0].legend(ncol=3,loc='lower right')
 axes[0].set_title('Executed idle output and independent valve model / load 5 → 9 → 5 Nm')
 axes[-1].set_xlabel('Virtual time (s)');finish(fig,out,'idle-load-step')
 fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True)
 for name,label,color in [('load','normal','#2673b8'),('disconnected','disconnected','#777777'),('stuck-open','stuck open','#b34b45'),('inverted-drive','logical inversion','#7a5ba7')]:
  run=read(matrix,'ours-'+name);trace=run['trace'];t=[r['time'] for r in trace]
  axes[0].plot(t,[r['plant_rpm'] for r in trace],label=label,color=color);axes[1].plot(t,[r['ecu']['idle_valve']['opening_pct'] for r in trace],color=color)
 for ax,label in zip(axes,['Shaft speed (RPM)','Model opening (%)']):style(ax);ax.set_ylabel(label);ax.axvspan(5,9,alpha=.08,color='black')
 axes[0].legend(ncol=2);axes[0].set_title('Failed-actuator negative controls / project controller');axes[1].set_xlabel('Virtual time (s)');finish(fig,out,'idle-actuator-faults')
 fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True)
 for who in ('ours','speeduino'):
  trace=read(followup,who+'-reachable-target')['trace'];t=[r['time'] for r in trace]
  axes[0].plot(t,[r['plant_rpm'] for r in trace],color=COLORS[who],label={'ours':'Project','speeduino':'Speeduino'}[who]);axes[1].plot(t,[r['ecu']['idle_valve']['opening_pct'] for r in trace],color=COLORS[who])
 for ax,label in zip(axes,['Shaft speed (RPM)','Model opening (%)']):style(ax);ax.set_ylabel(label);ax.axvspan(5,9,alpha=.08,color='black')
 axes[0].axhline(1100,color='#555555',ls=':',lw=1,label='1100 RPM target');axes[0].legend(ncol=3,loc='lower right');axes[0].set_title('Target within valve authority / explicit model-specific P/I = 0.06/0.06')
 axes[1].set_xlabel('Virtual time (s)');finish(fig,out,'idle-reachable-target')
 fig,axes=plt.subplots(2,1,figsize=(9,4),sharex=True)
 probes=json.loads((matrix/'reference-pwm.json').read_text())
 for ax,bits in zip(axes,(32,16)):
  case=next(r for r in probes if r.get('bits')==bits and r.get('seeded') is True and r.get('mode')=='closed_loop')
  t=[0];v=[case['reported_before_disable']['physical_level']]
  for stamp,channel,high,*_ in case['post_disable_edges']:t.append((stamp-100000)/1000);v.append(int(high))
  t.append(50);v.append(v[-1]);ax.step(t,v,where='post',color=COLORS['speeduino']);style(ax);ax.set_yticks([0,1]);ax.set_ylim(-.15,1.15);ax.set_ylabel(f'Native {bits}\nGPIO level')
 axes[0].set_title('Unmodified Speeduino PWM_OLCL continues after disableIdle()')
 axes[-1].set_xlabel('Timer-only time after disable (ms), outside engine coupling');finish(fig,out,'idle-reference-disable')
 html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>
 body{font-family:var(--font-sans,system-ui);color:var(--foreground);margin:0}select{background:var(--secondary);color:var(--foreground);border:1px solid var(--border);border-radius:var(--radius,8px);padding:8px;max-width:100%}.chart{overflow:auto;margin-top:10px}.chart[hidden]{display:none}.chart img{display:block;width:100%;min-width:640px;height:540px;object-fit:contain}p{color:var(--muted-foreground,#777);font-size:13px;line-height:1.45}label{font-size:14px}</style></head><body><label for="case">Experiment </label><select id="case" onchange="document.querySelectorAll('.chart').forEach((x,i)=>x.hidden=i!==this.selectedIndex)">'''
 names=[('idle-load-step','Load step: executed output, valve and RPM'),('idle-actuator-faults','Disconnected, stuck-open and inverted drive'),('idle-reachable-target','Reachable target with explicit model tune'),('idle-reference-disable','Reference PWM after production disable')]
 html+=''.join('<option>'+label+'</option>' for _,label in names)+'</select>'
 html+=''.join(f'<div class="chart" {"hidden" if i else ""}><img src="{name}.svg" alt="{label}"></div>' for i,(name,label) in enumerate(names))
 html+='<p>Uncalibrated Modelica air path plus empirical combustion and valve. Native controller code, virtual GPIO, zero CPU/IRQ cost. Shaded interval: added load. No physical engine qualification. Scroll figures horizontally on narrow screens.</p></body></html>'
 (out/'charts.html').write_text(html)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--matrix-dir',type=Path,default=R/'.cache/engine/idle/matrix');p.add_argument('--followup-dir',type=Path,default=R/'.cache/engine/idle/followups');p.add_argument('--output-dir',type=Path,default=R/'reports/engine/idle-control');a=p.parse_args();plot(a.matrix_dir,a.followup_dir,a.output_dir)
