#!/usr/bin/env python3
"""Plot the declared load benchmark without treating simulation as qualification."""
import argparse,gzip,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def plot(directory,output):
 report=json.loads((directory/'summary.json').read_text());assert report['passed'];output.mkdir(parents=True,exist_ok=True)
 rows={(r['label'],r['case']):r for r in report['runs'] if r['step_us']==250}
 colors={'portable':'#2367a2','target':'#17836b','speeduino32':'#c56d2b','speeduino16':'#9a5798'}
 names={'portable':'Project portable','target':'Project target dispatcher','speeduino32':'Speeduino native32','speeduino16':'Speeduino native16 timer model'}
 fig,axes=plt.subplots(2,2,figsize=(13,8.5),layout='constrained');fig.suptitle('Load-source benchmark on the independent synthetic engine plant',fontsize=15)
 for label,color in colors.items():
  r=json.loads(gzip.decompress((directory/rows[(label,'alpha')]['trace_file']).read_bytes()))
  style='--' if label in ('target','speeduino16') else '-'
  axes[0,0].plot([x['time'] for x in r['trace']],[x['plant_rpm'] for x in r['trace']],style,color=color,lw=1.5,label=names[label])
  qualified=[x for x in r['trace'] if x['lambda_valid']]
  axes[0,1].plot([x['time'] for x in qualified],[x['lambda_measured'] for x in qualified],style,color=color,lw=1.5)
 axes[0,0].set(title='TPS map derived from independent steady FMU air flow',xlabel='Virtual time (s)',ylabel='Free-shaft RPM',xlim=(0,6))
 axes[0,0].legend(fontsize=8,loc='upper left');axes[0,1].set(title='Synthetic wideband after combustion; zoom 0.6..1.55',xlabel='Virtual time (s)',ylabel='Lambda',xlim=(0,6),ylim=(.6,1.55));axes[0,1].axhline(1,color='#6b7280',lw=.8,ls=':')
 labels=('Correct fixed datum','Correct live datum','Wrong fixed datum')
 for n,label in enumerate(('portable','speeduino32')):
  values=[rows[(label,c)]['metrics']['mean_cylinder_lambda_after4'] for c in ('baro_fixed','baro_live','baro_wrong_datum')]
  axes[1,0].bar([i+(.18 if n else -.18) for i in range(3)],values,width=.34,color=colors[label],label=names[label])
 axes[1,0].set(title='80 kPa physical ambient, declared 68% coefficient fixture',ylabel='Mean cylinder lambda after 4 s',xticks=range(3),xticklabels=labels);axes[1,0].axhline(1,color='#6b7280',ls=':',lw=.8);axes[1,0].legend(fontsize=8)
 for n,label in enumerate(('portable','speeduino32')):
  values=[rows[(label,c)]['summary']['final_rpm'] for c in ('zero_fuel','alpha_uncalibrated')]
  axes[1,1].bar([i+(.18 if n else -.18) for i in range(2)],values,width=.34,color=colors[label],label=names[label])
 axes[1,1].set(title='Calibration-failure controls: outcomes differ by controller',ylabel='Final free-shaft RPM',xticks=range(2),xticklabels=('Zero coefficient','Unchanged flat 85% TPS map'));axes[1,1].legend(fontsize=8)
 for ax in axes.flat:ax.grid(alpha=.2);ax.set_axisbelow(True)
 fig.supxlabel('All data are synthetic. Fixed empirical combustion/film; no engine or electrical qualification.\nStartup lambda excursions can exceed the zoomed axis. All values remain in the raw traces.\n12 calibration corners were outside the FMU pressure corridor and were not used by the Alpha-N trajectories.',fontsize=9)
 for suffix in ('png','svg'):fig.savefig(output/('load-comparison.'+suffix),dpi=160)
 plt.close(fig)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args();plot(a.directory,a.output)
