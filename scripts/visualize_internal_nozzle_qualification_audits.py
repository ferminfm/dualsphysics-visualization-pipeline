"""Deterministic evidence plots from completed audits; no simulation or fitting."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

def load(path):
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('duplicate key')
            out[k]=v
        return out
    return json.loads(path.read_text(),object_pairs_hook=unique)

def identity(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(65536),b''):digest.update(b)
    return {'path':str(path),'size_bytes':path.stat().st_size,'sha256':digest.hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cumulative',type=Path,required=True)
    p.add_argument('--restart',type=Path,action='append',default=[])
    p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image
    colors=['#1764AB','#E17C21','#757575']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'axes.titleweight':'normal','savefig.facecolor':'white'})
    cumulative=load(a.cumulative);qualification=load(a.qualification)
    if cumulative.get('schema')!='internal_nozzle_cumulative_same_step_campaign_audit_v1':
        raise ValueError('wrong completed cumulative audit')
    if qualification.get('schema')!='internal_nozzle_observed_qualification_status_v1':
        raise ValueError('wrong observed qualification status')
    a.output.mkdir(parents=True,exist_ok=False)
    files=[]
    def save(fig,name,caption):
        fig.text(.01,.012,caption,fontsize=8,wrap=True)
        fig.tight_layout(rect=(0,.06,1,.99))
        path=a.output/name;fig.savefig(path,dpi=160);plt.close(fig)
        with Image.open(path) as im:im.verify()
        with Image.open(path) as im:im.load();dimensions=[im.width,im.height]
        if path.stat().st_size<=0:raise ValueError('empty visual')
        files.append({**identity(path),'decoded':True,'dimensions':dimensions,'caption':caption})
    fresh=cumulative['runs'][0];scale=fresh['initial_state']['nozzle_scale_volume']
    Dh=(2/3)*(2*3.141592653589793/144)**.5
    step=fresh['step_history'];sparse=fresh['sparse']['history']
    fig,ax=plt.subplots(2,1,figsize=(9,6.5),sharex=True)
    ax[0].plot([r['end']/Dh for r in step],[r['net_volume']/scale for r in step],
               color=colors[0],label='Every accepted step',linewidth=1.8)
    ax[0].plot([r['time']/Dh for r in sparse],[r['net_volume']/scale for r in sparse],
               color=colors[1],label='Sparse same-stage approximation',linestyle='--',marker='o',markersize=3)
    ax[0].set(ylabel='Signed net volume / (A0 Dh)',title='Accepted-step and sparse cumulative flow')
    ax[0].legend(loc='best',frameon=False)
    ax[1].plot([r['time']/Dh for r in sparse],
               [(r['net_volume']-r['same_step_net_volume'])/scale for r in sparse],
               color=colors[1],marker='o',markersize=3)
    ax[1].axhline(0,color='#444444',linewidth=.8)
    ax[1].set(xlabel='t_star = t / Dh (U_ref = 1)',ylabel='Sparse minus stepwise / (A0 Dh)')
    for item in ax:item.grid(axis='y',color='#DDDDDD',linewidth=.5)
    save(fig,'accepted-step-versus-sparse-cumulative.png',
         'Endpoint trapezoids of net liquid plane flow; VOF at midpoint and velocity at step end. Sparse reconstruction is not the same-step acceptance test. Historical failures remain excluded.')
    gates=qualification['gates'];allowed={'pass','fail','not_run','insufficient','blocked'}
    if not gates or any(g['status'] not in allowed for g in gates):raise ValueError('invalid observed gate status')
    fig,ax=plt.subplots(figsize=(10,max(4,len(gates)*.45+1)))
    for y,g in enumerate(gates):
        status=g['status'];color=colors[0] if status=='pass' else colors[1] if status=='fail' else colors[2]
        ax.barh(y,1,color=color,alpha=.8,hatch='' if status=='pass' else '///')
        ax.text(.02,y,status.upper(),va='center',color='white',fontweight='bold')
        ax.text(1.04,y,g['detail'],va='center',fontsize=8)
    ax.set_yticks(range(len(gates)),[g['name'] for g in gates]);ax.invert_yaxis()
    ax.set_xlim(0,3.9);ax.set_xticks([]);ax.set_title('Observed qualification gates — separate from reporting completion')
    ax.spines['left'].set_visible(False);ax.spines['bottom'].set_visible(False)
    save(fig,'observed-qualification-gates.png',qualification['claim_boundary'])
    if a.restart:
        audits=[load(path) for path in a.restart]
        fig,axes=plt.subplots(len(audits),1,figsize=(10,3.2*len(audits)),squeeze=False)
        for ax,audit in zip(axes[:,0],audits):
            categories={'Core planes':[],'Profile/moments':[],'Raw morphology':[],'Exact counters':[]}
            for row in audit['comparisons']:
                category={'restart_core':'Core planes','restart_profile':'Profile/moments',
                          'restart_raw':'Raw morphology','exact_count':'Exact counters'}[row['criterion']]
                if row['tolerance']:
                    ratio=row['normalized_error']/row['tolerance']
                else:
                    ratio=0 if row['normalized_error']==0 else float('inf')
                categories[category].append(ratio)
            for index,(name,ratios) in enumerate(categories.items()):
                maximum=max(ratios)
                if maximum==float('inf'):
                    ax.text(index,1.1,'NONZERO EXACT ERROR',ha='center',fontsize=8,color=colors[1])
                else:
                    ax.bar(index,maximum,color=colors[0] if maximum<=1 else colors[1],
                           hatch='' if maximum<=1 else '///')
                    ax.text(index,maximum+.04,f'{maximum:.3g}',ha='center',fontsize=8)
            ax.axhline(1,color='#333333',linestyle='--',label='Original tolerance')
            ax.set_xticks(range(4),list(categories));ax.set_ylabel('Maximum error / tolerance')
            ax.set_title(f'Checkpoint tick {audit["checkpoint_tick"]}, comparison tick {audit["comparison_tick"]}: {audit["comparison_count"]} checks')
            ax.legend(loc='upper right',frameon=False)
        # Common y-axis for like-for-like checkpoint comparisons.
        limit=max(ax.get_ylim()[1] for ax in axes[:,0])
        for ax in axes[:,0]:ax.set_ylim(0,limit)
        save(fig,'same-source-restart-tolerance-ratios.png',
             'All registered metrics retained; normalized floor 1, original core/profile/raw criteria. Exact counters require zero discrepancy. Field-stage and cumulative qualification remain separate.')
    record={'schema':'internal_nozzle_visual_evidence_index_v1','files':files,
            'inputs':[identity(p) for p in (a.cumulative,a.qualification,*a.restart)],
            'style':'fixed scales; blue/orange; explicit text and hatching; no inferred data'}
    with (a.output/'visual-index.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps({'decoded_files':len(files),'output':str(a.output)}))

if __name__=='__main__':main()
