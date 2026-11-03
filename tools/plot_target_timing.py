#!/usr/bin/env python3
"""Standalone scientific figures for the shared target-dispatcher comparison."""
import html
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'reports/engine/target-timing';cache=ROOT/'.cache/engine/target-scenarios'
report=json.loads((cache/'summary.json').read_text())
if not report['passed']:raise RuntimeError('Comparison failed; do not publish passed figures')
plt.rcParams.update({'font.size':8,'svg.fonttype':'none','svg.hashsalt':'ecu-target-timing'})
series=(('native_esp32_dispatcher','Project target kernel','#0072b2'),('speeduino','Speeduino native','#d55e00'))
cases=[('warm_start','Warm start',(0,4),(0,1450),None,
        'Pulse-driven rotation continues after starter release at 2.5 s.'),
       ('stall_restart','Signal loss and restart',(0,12),(0,1450),(4,8),
        'Grey: crank signal absent. Starter assistance at 8–10 s restores rotation.'),
       ('sensor_short','MAP rail fault',(3.8,6),(0,1200),(4,5),
        'Project inhibits; this Speeduino profile continues. Different fault policies remain visible.'),
       ('overrev','Hard rev limit',(5.8,7),(5800,7000),(6,6.25),
        'Grey: declared motoring load. Dashed: 6500 RPM. Both hard cuts are exercised.')]
figures=[]
for scenario,title,xlim,ylim,region,caption in cases:
    fig,ax=plt.subplots(figsize=(3.6,2.35),layout='constrained')
    fig.patch.set_alpha(0);ax.patch.set_alpha(0)
    for controller,label,color in series:
        trace=json.loads((cache/(controller+'-'+scenario+'-250.json')).read_text())['trace']
        ax.plot([r['time'] for r in trace],[r['plant_rpm'] for r in trace],label=label,color=color,linewidth=1.4)
    if region:ax.axvspan(*region,color='#777777',alpha=.13)
    if scenario=='overrev':ax.axhline(6500,color='#777777',linestyle='--',linewidth=.8)
    ax.set(xlabel='Virtual time (s)',ylabel='Free shaft speed (RPM)',xlim=xlim,ylim=ylim)
    ax.grid(alpha=.2,color='#777777',linewidth=.5)
    if scenario=='warm_start':ax.legend(frameon=False,fontsize=7)
    name='comparison-'+scenario
    fig.savefig(out/(name+'.png'),dpi=200,facecolor='white');fig.savefig(out/(name+'.svg'),transparent=True);plt.close(fig)
    svg='\n'.join(line.rstrip() for line in (out/(name+'.svg')).read_text().splitlines())+'\n'
    (out/(name+'.svg')).write_text(svg);svg=svg[svg.index('<svg'):]
    for color,var in [('#000000','--foreground'),('#777777','--border'),('#0072b2','--chart-1'),('#d55e00','--chart-2')]:
        svg=svg.replace(color,'var('+var+', '+color+')')
    figures.append('<figure>'+svg+'<figcaption><strong>'+html.escape(title)+'.</strong> '+html.escape(caption)+'</figcaption></figure>')
page='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
html,body{margin:0;color:var(--foreground,#111);font-family:var(--font-sans,sans-serif)}
.plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}figure{margin:0;min-width:0}
svg{display:block;width:100%;height:230px;fill:var(--foreground,#111)}figcaption,p{font-size:12px;line-height:1.5;color:var(--muted-foreground,#555)}
strong{color:var(--foreground,#111);font-weight:500}p{margin:12px 0 0}@media(max-width:480px){.plots{grid-template-columns:1fr}}
</style></head><body><div class="plots">'''+''.join(figures)+'''</div><p>14 controller/scenario cases and 4 step-halving checks passed. Both use 5 ms sensor injection. Uncalibrated MVEM air path plus empirical combustion/free shaft; native execution with zero CPU cost. Physical outputs remain inhibited; target jitter is unmeasured.</p></body></html>'''
(out/'comparison.html').write_text(page+'\n')
print('Saved four PNG/SVG figures and comparison.html')
