"""Plot source-bound finite-step engine histories without resampling their physics."""
import argparse
import hashlib
import json
from pathlib import Path


def main(analysis,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    report=json.loads(analysis.read_text())
    output.mkdir(parents=True,exist_ok=False)
    figure,axes=plt.subplots(3,1,figsize=(10,8),sharex=True)
    inputs={str(analysis.resolve()):hashlib.sha256(analysis.read_bytes()).hexdigest()}
    for record in report['records']:
        if record['scenario']!='nominal':continue
        path=Path(record['path'])/'trace.jsonl'
        expected=record['raw_sha256']['trace.jsonl']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
        inputs[str(path.resolve())]=expected
        rows=[json.loads(line)for line in path.read_text().splitlines()]
        times=[row['time_us']/1e6 for row in rows]
        own=record['controller']=='ours'
        style={500:':',250:'--',125:'-'}[record['step_us']]
        label=('Project'if own else'Speeduino reference')+f" {record['step_us']} us"
        color='#167d48'if own else'#2369b5'
        values=([row['plant_rpm']for row in rows],
                [row['gas']['map_kpa']for row in rows],
                [row['gas']['turbo_rad_s']for row in rows])
        for axis,data in zip(axes,values):axis.plot(times,data,color=color,linestyle=style,label=label,linewidth=1.6)
    for axis,label in zip(axes,('Engine speed (RPM)','Manifold pressure (kPa absolute)','Turbo speed (rad/s)')):
        axis.set_ylabel(label);axis.grid(alpha=.2)
        axis.axvspan(0,2.5,color='gray',alpha=.07)
        axis.axvline(2.5,color='gray',linewidth=.8)
        axis.axvline(3,color='gray',linewidth=.8,linestyle=':')
    axes[-1].set_xlabel('Simulated time (s)')
    figure.suptitle('Uncalibrated 8-cylinder engine simulation\nStarter ends at 2.5 s; throttle opens to 20% at 3 s')
    handles,labels=axes[0].get_legend_handles_labels()
    figure.legend(handles,labels,loc='lower center',ncol=3,frameon=False,fontsize=9)
    figure.tight_layout(rect=(0,.065,1,.94))
    image=output/'refinement.png';figure.savefig(image,dpi=150);plt.close(figure)
    data=dict(plot_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              matplotlib_version=matplotlib.__version__,inputs=inputs,
              image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
              qualification='Actual saved trace points; no model calibration, controller equivalence or physical qualification')
    (output/'manifest.json').write_text(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.analysis,args.output)
