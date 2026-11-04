#!/usr/bin/env python3
"""Standalone scientific plots from preserved source-execution traces."""
import argparse,json,tarfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

def plot(source,output):
 output.mkdir(parents=True,exist_ok=True)
 colors=['#007c91','#bd5d19','#7258a2'];labels=['Our target dispatcher, native','Speeduino, native 32-bit timers','Speeduino, 16-bit timer model'];ids=['native_esp32_dispatcher','speeduino_native32','speeduino_megalike16'];styles=['-','--',':']
 with tarfile.open(source) as archive:
  def read(label,scenario):return json.load(archive.extractfile(label+'-'+scenario+'-250.json'))
  fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
  for ax,scenario,title in zip(axes.flat,('warm_start','throttle_step','cam_dropout'),('Warm start','Throttle step at 3 s','Cam signal removed at 4 s')):
   for label,name,color,style in zip(ids,labels,colors,styles):
    r=read(label,scenario);ax.plot([s['time'] for s in r['trace']],[s['plant_rpm'] for s in r['trace']],label=name,color=color,ls=style,lw=1.8)
   ax.set(title=title,xlabel='Simulation time (s)',ylabel='Independent shaft speed (RPM)');ax.grid(alpha=.2);ax.yaxis.set_major_locator(MaxNLocator(5))
   if scenario=='cam_dropout':ax.axvline(4,color='#555555',lw=1);ax.text(4.2,1100,'Our phase-loss cut;\nreference retains phase',fontsize=9)
  ax=axes[1,1];values=[read(label,'warm_start')['summary']['first_sync_s'] for label in ids]
  bars=ax.barh(labels,values,color=colors);ax.invert_yaxis();ax.set(title='First full 720° synchronization',xlabel='Simulation time (s)',xlim=(0,1.9));ax.bar_label(bars,fmt='%.2f s',padding=4);ax.grid(axis='x',alpha=.2)
  axes[0,0].legend(fontsize=8,loc='lower right')
  fig.suptitle('Four-cylinder sequential control on an uncalibrated research plant',fontsize=15)
  fig.supxlabel('MVEM air path + local empirical combustion/free shaft. Zero CPU/IRQ cost. Software comparison only; physical outputs inhibited.',fontsize=9)
  for ext in ('png','svg'):fig.savefig(output/('sequential-comparison.'+ext),dpi=180)
  plt.close(fig)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();plot(a.source,a.output)
