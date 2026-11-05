#!/usr/bin/env python3
"""Standalone scientific figures from saved evidence, plus a theme-aware report."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1]
plt.rcParams.update({'font.size':9,'axes.labelsize':9,'xtick.labelsize':8,'ytick.labelsize':8,'svg.fonttype':'none','svg.hashsalt':'ecu-first-increment'})
out=R/'reports/engine'
def figure(name,draw):
 fig,ax=plt.subplots(figsize=(3.4,2.55),layout='constrained')
 fig.patch.set_alpha(0);ax.patch.set_alpha(0)
 ax.tick_params(colors='#111111');ax.xaxis.label.set_color('#111111');ax.yaxis.label.set_color('#111111')
 for spine in ax.spines.values():spine.set_color('#777777')
 draw(ax);ax.grid(alpha=.18,color='#777777',linewidth=.6)
 fig.savefig(out/(name+'.svg'),transparent=True)
 fig.savefig(out/(name+'.png'),dpi=200,facecolor='white',transparent=False)
 plt.close(fig)
 path=out/(name+'.svg');text='\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n';path.write_text(text);text=text[text.index('<svg'):]
 for a,b in [('#111111','var(--foreground)'),('#000000','var(--foreground)'),('#777777','var(--border)'),('#0077bb','var(--chart-1)'),('#dd8811','var(--chart-2)')]:text=text.replace(a,b)
 return text
def traces(ax):
 for name,label,color in [('warm_start','Warm start','#0077bb'),('load_stall_restart','Load stall / restart','#dd8811')]:
  data=json.loads((R/f'.cache/engine/scenarios/{name}-seed17.json').read_text())['trace']
  ax.plot([p['time'] for p in data],[p['plant_rpm'] for p in data],color=color,label=label,linewidth=1.4)
 ax.set(xlabel='Virtual time (s)',ylabel='Plant speed (RPM)',xlim=(0,12),ylim=(0,1700))
 ax.set_xticks([0,4,8,12]);ax.legend(frameon=False,fontsize=7,loc='upper right')
def comparison(ax):
 data=json.loads((out/'speeduino-fuel-comparison.json').read_text())['rows']
 ax.scatter([p['speeduino_us']/1000 for p in data],[p['difference_us'] for p in data],s=12,color='#0077bb',alpha=.7)
 ax.axhline(0,color='#777777',linewidth=.8)
 ax.set(xlabel='Speeduino pulse width (ms)',ylabel='Our pulse minus reference (µs)',ylim=(-30,30))
 ax.set_yticks([-30,0,30]);ax.set_xticks([0,2,4,6,8])
a=figure('sil-start-restart',traces)
b=figure('speeduino-fuel-difference',comparison)
html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{margin:0;background:transparent;color:var(--foreground);font-family:var(--font-sans)}.plots{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}figure{margin:0;min-width:0}svg{display:block;width:100%;height:auto;fill:var(--foreground)}figcaption{font-size:13px;line-height:1.5;color:var(--muted-foreground)}strong{font-weight:500;color:var(--foreground)}</style></head><body>
<div class="plots"><figure>'''+a+'''<figcaption><strong>Unvalidated SIL, seed 17.</strong> A protected load stall recovers after stopped-state checks. Physical outputs inhibited.</figcaption></figure><figure>'''+b+'''<figcaption><strong>75 steady-state fuel cases.</strong> Max difference 22.69 µs. Compiled Speeduino fuel kernel only, not two complete ECUs.</figcaption></figure></div></body></html>'''
(out/'first-increment-charts.html').write_text('\n'.join(line.rstrip() for line in html.splitlines())+'\n')
print('Saved evidence plots and report')
