#!/usr/bin/env python3
"""Export standalone figures and trace-bound metrics for the semi benchmark."""
import argparse,base64,csv,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def plot(source,output):
 output.mkdir(parents=True,exist_ok=True);report=json.loads((source/'summary.json').read_text())
 assert report['passed']
 with (output/'metrics.csv').open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow(['profile','scenario','final_second_rpm','fuel_mg','max_injector_us','max_dwell_us','closing_error_after3s_deg','fault_mask','post_loss_rises','post_loss_last_edge_ms'])
  for r in report['rows']:writer.writerow([r['label'],r['scenario'],r['mean_final_second_rpm'],r['ledger']['fuel_in_mg'],r['max_injector_high_us'],r['max_dwell_high_us'],r['max_injection_closing_error_after_3s_deg'],r['project_fault_mask_seen'],r['output_rises_after_dropout'],r['last_output_after_dropout_ms']])
 fig,axes=plt.subplots(2,2,figsize=(11,7),sharex=True);profiles=[('target','Our ESP32 dispatcher','#28734f','-'),('speeduino32','Speeduino native32','#c15c31','--'),('speeduino16','Speeduino timer16','#2d67ac',':')]
 for ax,(scenario,title) in zip(axes.flat,[('warm_start','Warm start'),('throttle_step','Throttle step at3 s'),('trigger_dropout','Crank signal absent4–4.7 s'),('load_step','35 Nm load from4 s: stall')]):
  for label,name,color,style in profiles:
   data=json.loads((source/f'{label}-{scenario}-250.json').read_text())
   ax.plot([r['time'] for r in data['trace']],[r['plant_rpm'] for r in data['trace']],label=name,color=color,linestyle=style,linewidth=1.7)
  if scenario=='trigger_dropout':ax.axvspan(4,4.7,color='#aaa',alpha=.17)
  if scenario=='load_step':ax.axvline(4,color='#888',linewidth=.8)
  ax.set_title(title,loc='left',fontsize=11);ax.set_ylabel('Model RPM');ax.set_xlim(0,10);ax.set_ylim(bottom=0);ax.grid(alpha=.2)
 for ax in axes[-1]:ax.set_xlabel('Virtual time (s)')
 handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.94),ncol=3,frameon=False,fontsize=9)
 fig.suptitle('Semi-sequential control on an uncalibrated engine model',fontsize=15,y=.99)
 fig.text(.02,.018,'Executed actuator edges; independent fixed1-3-4-2 plant copies. Zero CPU/IRQ cost. Native16 is a timer model, not AVR emulation.\n28 scenario runs +8 step checks. Physical outputs inhibited in simulation; no engine or vehicle qualification.',fontsize=8,color='#444')
 fig.tight_layout(rect=(0,.07,1,.91));fig.savefig(output/'comparison.png',dpi=170);fig.savefig(output/'comparison.svg');plt.close(fig)
 image=base64.b64encode((output/'comparison.png').read_bytes()).decode()
 html='<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Semi-sequential comparison</title><style>body{margin:0;color:var(--foreground);font-family:var(--font-sans)}main{margin:0}img{display:block;width:100%;height:auto}p{margin:8px 0;line-height:1.5;color:var(--muted-foreground)}</style></head><body><main><img alt="Four engine-model RPM comparisons for our ECU and pinned Speeduino" src="data:image/png;base64,'+image+'"><p>The load stall and post-loss exposure remain recorded limitations. These traces test software; they are not vehicle calibration or physical qualification.</p></main></body></html>'
 (output/'comparison.html').write_text(html)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();plot(a.source,a.output)
