#!/usr/bin/env python3
"""Scientific exports of the actual native logger comparison traces."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];cache=ROOT/'.cache/engine/trigger-loggers';out=ROOT/'reports/engine/trigger-logging'
report=json.loads((cache/'summary.json').read_text())
if not report['passed']:raise RuntimeError('Do not publish failed comparison as passed')
plt.rcParams.update({'font.size':8,'svg.fonttype':'none','svg.hashsalt':'ecu-trigger-diagnostics'})
figures=[]
cases=[('tooth-1000-clean','Clean tooth intervals','Both endpoints lie inside the common capture window. The first reference interval begins outside it.'),
       ('composite-1000-noise','Raw intervals with short glitches','These intervals include reported noise edges. They are not Speeduino’s decoder-filtered tooth log.'),
       ('composite-1000-dropout','Raw intervals across signal loss','The prescribed 100 ms interruption remains visible in both raw recordings. No physical timing claim.')]
for name,title,caption in cases:
 result=json.loads((cache/(name+'.json')).read_text());rows=result['project_records']
 rising=[row['captured_us'] for row in rows if row['channel']=='crank' and row['high']]
 project=[b-a for a,b in zip(rising,rising[1:])];times=[(time-rising[0])/1000 for time in rising[1:]]
 if result['mode']=='tooth':reference=[row['value'] for row in result['reference']['records']][1:];project=project[:126];times=times[:126]
 else:
  native=[row['value'] for row in result['reference']['records'] if not row['flags']&8 and row['flags']&1]
  reference=[b-a for a,b in zip(native,native[1:])]
 if reference!=project:raise RuntimeError('Cannot plot nonmatching diagnostic intervals as equal')
 fig,ax=plt.subplots(figsize=(3.6,2.35),layout='constrained');fig.patch.set_alpha(0);ax.patch.set_alpha(0)
 ax.vlines(times,0,[value/1000 for value in project],label='Project raw recorder',color='#0072b2',linewidth=.9)
 ax.plot(times,[value/1000 for value in reference],label='Production Speeduino',color='#d55e00',linestyle='none',marker='o',markersize=2.6,markerfacecolor='none')
 ax.set(xlabel='Capture-relative time (ms)',ylabel='Rising interval (ms)');ax.grid(alpha=.2,color='#777777',linewidth=.5)
 if name=='composite-1000-noise':ax.set_xlim(0,40)
 if name=='tooth-1000-clean':ax.legend(frameon=False,fontsize=7,loc='upper right')
 fig.savefig(out/(name+'.png'),dpi=200,facecolor='white');fig.savefig(out/(name+'.svg'),transparent=True);plt.close(fig)
 path=out/(name+'.svg');svg='\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n';path.write_text(svg);svg=svg[svg.index('<svg'):]
 for color,var in [('#000000','--foreground'),('#777777','--border'),('#0072b2','--chart-1'),('#d55e00','--chart-2')]:svg=svg.replace(color,'var('+var+', '+color+')')
 figures.append('<figure>'+svg+'<figcaption><strong>'+title+'.</strong> '+caption+'</figcaption></figure>')
figures.append('<div class="explain"><strong>Native diagnostic coverage</strong><p>Seven raw composite cases and three clean tooth cases passed. Actual Speeduino logger functions and GPIO-dispatched interrupt wrappers are executed.</p><p>The cam reference fixture enables its sequential configuration to expose a secondary input. This project still uses batch/wasted operation. Phase and sync flags are not claimed equivalent.</p><p>The separate engine-plant matrix remains an uncalibrated software test. Physical capture integrity and interrupt latency require hardware measurements.</p></div>')
page='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
html,body{margin:0;color:var(--foreground,#111);font-family:var(--font-sans,sans-serif)}
.plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}figure{margin:0;min-width:0}
svg{display:block;width:100%;height:230px;fill:var(--foreground,#111)}figcaption,.explain{font-size:12px;line-height:1.6;color:var(--muted-foreground,#555)}
strong{color:var(--foreground,#111);font-weight:500}.explain{padding-top:12px}.explain p{margin:10px 0}
@media(max-width:480px){.plots{grid-template-columns:1fr}}</style></head><body><div class="plots">'''+''.join(figures)+'</div></body></html>'
(out/'logger-comparison.html').write_text(page+'\n');print('Saved three native diagnostic figures and logger-comparison.html')
