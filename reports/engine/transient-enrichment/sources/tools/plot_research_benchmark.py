#!/usr/bin/env python3
"""Export standalone scientific figures and a theme-aware comparison report."""
import html
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];out=ROOT/'reports/engine'
report=json.loads((out/'full-controller-comparison.json').read_text())
if not report['passed']:raise RuntimeError('Do not publish plots as passed evidence for a failed matrix')
plt.rcParams.update({'font.size':8,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7,
                     'svg.fonttype':'none','svg.hashsalt':'ecu-external-research'})
series=(('ours','Project core','#0072b2'),('speeduino','Speeduino native','#d55e00'),
        ('speeduino_per_tooth','Native per tooth','#009e73'))


def draw(name,scenario,xlim,ylim,region=None,limit=False,legend=False):
    fig,ax=plt.subplots(figsize=(3.6,2.45),layout='constrained')
    fig.patch.set_alpha(0);ax.patch.set_alpha(0)
    for controller,label,color in series:
        result=json.loads((ROOT/f'.cache/engine/comparison/{controller}-{scenario}-250.json').read_text())
        trace=result['trace'];ax.plot([p['time'] for p in trace],[p['plant_rpm'] for p in trace],
                                    label=label,color=color,linewidth=1.3,alpha=.9)
    if region:ax.axvspan(*region,color='#777777',alpha=.12)
    if limit:ax.axhline(6500,color='#777777',linestyle='--',linewidth=.8)
    ax.set(xlabel='Virtual time (s)',ylabel='Free shaft speed (RPM)',xlim=xlim,ylim=ylim)
    ax.grid(color='#777777',alpha=.2,linewidth=.5)
    ax.tick_params(colors='#111111');ax.xaxis.label.set_color('#111111');ax.yaxis.label.set_color('#111111')
    for spine in ax.spines.values():spine.set_color('#777777')
    if legend:ax.legend(loc='upper right',frameon=False,fontsize=7)
    fig.savefig(out/(name+'.svg'),transparent=True)
    fig.savefig(out/(name+'.png'),dpi=220,facecolor='white',transparent=False)
    plt.close(fig)
    path=out/(name+'.svg');svg='\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n';path.write_text(svg)
    svg=svg[svg.index('<svg'):]
    for color,var in [('#111111','--foreground'),('#000000','--foreground'),('#777777','--border'),
                      ('#0072b2','--chart-1'),('#d55e00','--chart-2'),('#009e73','--chart-3')]:
        svg=svg.replace(color,f'var({var}, {color})')
    return svg


figures=[
    (draw('research-warm-start','warm_start',(0,4),(0,1450),legend=True),
     'Warm start','Actual injection and spark edges sustain rotation after the starter releases at2.5s.'),
    (draw('research-stall-restart','stall_restart',(0,12),(0,1450),region=(4,8)),
     'Signal loss and restart','Grey: trigger unavailable. A starter at8–10s restores rotation; each controller receives its own resulting teeth.'),
    (draw('research-hard-limit','overrev',(5.8,7),(5800,7000),region=(6,6.25),limit=True),
     'Verified hard-limit crossing','Grey: external motoring load. Dashed:6500RPM. Both fuel and ignition cuts are observed.'),
    (draw('research-trigger-dropout','trigger_dropout',(3.8,5.5),(0,1100),region=(4,4.7)),
     'Long dropout without starter','All three shafts stop. Restoring signal availability cannot rotate a stopped engine.')]
page='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{margin:0;background:transparent;color:var(--foreground,#111);font-family:var(--font-sans,sans-serif)}
.plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}figure{margin:0;min-width:0}
svg{display:block;width:100%;height:236px;fill:var(--foreground,#111)}figcaption{font-size:12px;line-height:1.5;color:var(--muted-foreground,#555)}
strong{color:var(--foreground,#111);font-weight:500}.scope{margin:12px 0 0;font-size:12px;line-height:1.5;color:var(--muted-foreground,#555)}
@media(max-width:480px){.plots{grid-template-columns:1fr}}</style></head><body><div class="plots">'''
for svg,title,caption in figures:
    page+='<figure>'+svg+'<figcaption><strong>'+html.escape(title)+'.</strong> '+html.escape(caption)+'</figcaption></figure>'
page+='</div><p class="scope">'+str(report['controller_cases'])+' controller cases and '+str(report['convergence_cases'])+' step-halving cases. Uncalibrated MVEM air path with local empirical combustion and shaft dynamics. Native HALs and virtual GPIO; physical engine outputs remain inhibited.</p></body></html>'
(out/'research-benchmark-charts.html').write_text(page+'\n')
print('Saved4 research comparison figures, PNG/SVG exports and inline HTML')
