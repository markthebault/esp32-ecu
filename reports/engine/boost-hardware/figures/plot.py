"""Plot raw circuit traces, without smoothing or physical qualification claims."""
import hashlib, json, platform
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import cairosvg
root=Path(__file__).resolve().parent
study=root.parent/'boost-circuit-full-003'
fig,axes=plt.subplots(3,2,figsize=(11,7.5),sharex=True,constrained_layout=True)
sources={}
for col,(case,label) in enumerate([('engine_edges_2','Own controller: charged MAP-rail fault'),('engine_edges_3','Production Speeduino: corresponding source run')]):
    path=study/case/'trace.tsv';data=np.loadtxt(path,skiprows=1);t=data[:,0]+5.9
    sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    axes[0,col].set_title(label,fontsize=11)
    for row,index,ylabel in [(0,6,'Carrier command (V)'),(1,2,'MOSFET gate (V)'),(2,8,'Coil current (A)')]:
        ax=axes[row,col];ax.plot(t,data[:,index],color=['#2763a5','#7546a0','#16805b'][row],linewidth=1)
        ax.set_ylabel(ylabel);ax.grid(alpha=.22);ax.set_xlim(5.9,6.1501)
        if col==0:ax.axvline(6.03,color='#b33b37',linestyle='--',linewidth=.8)
        if row==2:ax.set_xlabel('Original source time (s)')
    axes[0,col].set_ylim(-.2,3.7);axes[1,col].set_ylim(-.3,5.8);axes[2,col].set_ylim(-.02,.37)
axes[0,0].text(6.033,3.47,'Delivered control cut',color='#b33b37',fontsize=8)
fig.suptitle('Conditional boost electrical replay: retained fault edge versus continuing PWM\n36Ω / 30mH model coil, fixed12V, zero initial current; no engine feedback or physical validation',fontsize=12)
fig.savefig(root/'charged-cut-replay.png',dpi=160);fig.savefig(root/'charged-cut-replay.svg')
plt.close(fig)
for path in sorted(root.glob('*.svg')):
    if path.name=='charged-cut-replay.svg':continue
    cairosvg.svg2png(url=str(path),write_to=str(path.with_suffix('.png')),output_width=1300)
(root/'plot-provenance.json').write_text(json.dumps(dict(tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    input_sha256=sources,python=platform.python_version(),numpy=np.__version__,matplotlib=matplotlib.__version__,physical_qualification=False),indent=2)+'\n')
print('Rendered assembly views and raw charged-cut comparison')
