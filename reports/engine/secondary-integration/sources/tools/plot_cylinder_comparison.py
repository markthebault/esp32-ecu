#!/usr/bin/env python3
"""Export scientific figures from the preserved cylinder comparison reports."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def plot(baseline,transients,output):
 output.mkdir(parents=True,exist_ok=True)
 r=json.loads((baseline/'summary.json').read_text());rows={(v['controller'],v['mode']):v for v in r['rows']}
 fig,axes=plt.subplots(2,2,figsize=(13,8.5),layout='constrained');colors=['#64748b','#007c91','#bd5d19']
 selections=[('ours',['neutral','corrected','swapped'],['Neutral','Inverse flow + spark','C2/C3 swapped']),
             ('speeduino',['neutral','corrected','total_pw_adjusted'],['Neutral','Same inverse flow','Total-PW adjusted at idle'])]
 for ax,(who,modes,labels) in zip(axes[0],selections):
  for mode,label,color in zip(modes,labels,colors):
   ax.plot([1,2,3,4],[c['mean_lambda'] for c in rows[who,mode]['metrics']['cylinders']],marker='o',color=color,label=label,lw=1.8)
  ax.set(title='Project: effective fuel before deadtime' if who=='ours' else 'Speeduino: total PW including deadtime',xlabel='Physical cylinder',ylabel='Mean model lambda, final 2 seconds',xticks=[1,2,3,4],ylim=(.6,1.02))
  ax.axhline(1,color='#555555',ls=':',lw=1);ax.grid(alpha=.2);ax.legend(fontsize=8,loc='upper right')
 ax=axes[1,0];width=.34;x=[0,1,2]
 for i,(who,modes) in enumerate([('ours',['neutral','corrected','swapped']),('speeduino',['neutral','total_pw_adjusted','swapped'])]):
  values=[100*rows[who,m]['metrics']['work_cv'] for m in modes]
  bars=ax.bar([v+(i-.5)*width for v in x],values,width,label='Project' if who=='ours' else 'Speeduino',color=['#007c91','#bd5d19'][i]);ax.bar_label(bars,fmt='%.3f',padding=3,fontsize=8)
 ax.set(title='Cylinder scheduled-combustion work spread',ylabel='Coefficient of variation (%)',xticks=x,xticklabels=['Neutral','Own policy calibration','C2/C3 swapped'],ylim=(0,9));ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
 ax=axes[1,1]
 for who,color in [('ours','#007c91'),('speeduino','#bd5d19')]:
  p=transients/(who+'-cam_dropout-250-sequential-timer16.json');data=json.loads(p.read_text());trace=data['trace'];ax.plot([v['time'] for v in trace],[v['plant_rpm'] for v in trace],label='Project: phase-loss cut' if who=='ours' else 'Speeduino: retain acquired phase',color=color,lw=1.8)
 ax.axvline(4,color='#555555',lw=1,ls=':');ax.set(title='Cam removed at 4 s, calibrated trims active',xlabel='Simulation time (s)',ylabel='Independent shaft speed (RPM)');ax.grid(alpha=.2);ax.legend(fontsize=8)
 fig.suptitle('Cylinder balance and declared phase-loss policies',fontsize=15)
 fig.supxlabel('Uncalibrated MVEM air path + local empirical combustion/free shaft. Rich absolute lambda remains; balancing is not optimal tuning.\nNative controller source, zero CPU/IRQ cost. Speeduino total-PW calibration uses known simulated flow/deadtime at one idle point.',fontsize=9)
 for ext in ('png','svg'):fig.savefig(output/('cylinder-comparison.'+ext),dpi=170)
 plt.close(fig)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('transients',type=Path);p.add_argument('output',type=Path);a=p.parse_args();plot(a.baseline,a.transients,a.output)
