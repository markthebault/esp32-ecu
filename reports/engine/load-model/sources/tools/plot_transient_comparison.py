#!/usr/bin/env python3
"""Standalone research comparison figure; no physical acceptance implied."""
import argparse,gzip,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def plot(matrix,output):
 def read(name):
  p=matrix/name
  return json.loads(p.read_text()) if p.exists() else json.loads(gzip.decompress(p.with_suffix(p.suffix+'.gz').read_bytes()))
 summary=read('summary.json');assert summary['passed']
 fig,axes=plt.subplots(2,2,figsize=(11,6.5),layout='constrained');colors=('#166fbc','#b35b1c')
 for label,title,color in zip(('target','speeduino32'),('ESP32 target dispatcher','Pinned Speeduino32'),colors):
  rows=read(label+'-weak_reverse-250.json')['trace'];rows=[r for r in rows if 2.98<=r['time']<=3.38]
  axes[0,0].step([r['time'] for r in rows],[r['ecu']['transient_enrichment']['tps_dot_pct_s'] for r in rows],where='post',color=color,label=title)
  axes[0,1].step([r['time'] for r in rows],[r['ecu']['transient_enrichment']['correction_pct'] for r in rows],where='post',color=color,label=title)
  negative=[r for r in summary['negative'] if r['label']==label]
  for ax,case,title_ in ((axes[1,0],'tps_adder','Warm tip-in'),(axes[1,1],'cold_adder','Cold tip-in')):
   r=next(r for r in negative if r['case']==case);delta=r['on_metrics']['mean_abs_cylinder_lambda_error_3_to4_5']-r['off_metrics']['mean_abs_cylinder_lambda_error_3_to4_5']
   position=('target','speeduino32').index(label);ax.bar(position,delta,color=color,width=.55);ax.text(position,delta,f'{delta:+.5f}',ha='center',va='bottom' if delta>=0 else 'top',fontsize=10)
   ax.set_title(title_+': additive minus neutral');ax.set_xticks([0,1],['ESP32 target','Speeduino32']);ax.set_ylabel('Change in mean |cylinder lambda − 1|');ax.axhline(0,color='#666',linewidth=.8)
 axes[0,0].set_title('Measured rate during weaker reversal');axes[0,0].set_ylabel('TPS rate (%/s)');axes[0,1].set_title('Different declared hold/reversal policies');axes[0,1].set_ylabel('Nominal transient correction (%)')
 for ax in axes[0]:ax.set_xlabel('Model time (s)');ax.legend(fontsize=9);ax.axhline(0 if ax is axes[0,0] else 100,color='#999',linewidth=.6)
 for ax in axes.flat:ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
 fig.suptitle('Transient fueling in an uncalibrated independent engine plant',fontsize=14)
 fig.supxlabel('Executed-edge native comparison · fixed empirical film · mild comparison curves · no physical qualification',fontsize=9)
 output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(output,dpi=180);fig.savefig(output.with_suffix('.svg'));plt.close(fig)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('matrix',type=Path);p.add_argument('output',type=Path);a=p.parse_args();plot(a.matrix,a.output)
