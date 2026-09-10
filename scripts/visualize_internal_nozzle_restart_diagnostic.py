"""Produce descriptive views of an already-computed diagnostic comparison.

No CFD launch, acceptance decision, invented frame, or geometry rescaling.
All field joins must be exact; original hydraulic tolerances are plotted as-is.
"""
import argparse,csv,hashlib,json,math
from pathlib import Path
import sys

p=argparse.ArgumentParser(description=__doc__)
for name in ('source-root','comparison','output'):
    p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--comparison-label',required=True,
               help='Literal observed case/source qualification label; never inferred from a filename')
p.add_argument('--view-half-width-dh',type=float,required=True,
               help='Fixed displayed transverse half-width in hydraulic diameters')
a=p.parse_args();sys.path.insert(0,str(a.source_root/'scripts'))
if not math.isfinite(a.view_half_width_dh) or a.view_half_width_dh<=0:
    raise ValueError('positive finite fixed camera width required')
import compare_internal_nozzle_keyed_state as keyed
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle
from matplotlib.colors import LinearSegmentedColormap
BLUE='#365f95';ORANGE='#bb6b39';INK='#25282c'
BLUE_MAP=LinearSegmentedColormap.from_list('declared_blue',['#f4f6f8',BLUE,'#183350'])
SIGNED_MAP=LinearSegmentedColormap.from_list('declared_signed',[BLUE,'#f6f6f4',ORANGE])
plt.rcParams.update({'font.family':'DejaVu Sans','text.color':INK,'axes.labelcolor':INK,
                     'axes.titlecolor':INK,'axes.spines.top':False,'axes.spines.right':False})

if a.output.exists():raise ValueError('preserve prior visual package; choose a new output')
summary=json.loads(keyed.regular(a.comparison/'summary.json').read_text())
metric_path=keyed.regular(Path(summary['frozen_scalar_comparison']['path']))
if keyed.identity(metric_path)!=summary['frozen_scalar_comparison']:raise ValueError('changed metric comparison bytes')
metric=json.loads(metric_path.read_text())
records=[]
for comp in summary['comparisons']:
    if comp['structural_join']=='exact':
        path=Path(comp['comparison']['path'])
        if keyed.identity(path)!=comp['comparison']:raise ValueError('changed comparison bytes')
        records.append((comp['label'],json.loads(path.read_text())))
if not records:raise ValueError('no exact field comparison to visualize')
a.output.mkdir(parents=True)
files=[]
def save(fig,name):
    path=a.output/name;fig.savefig(path,dpi=150,bbox_inches='tight');plt.close(fig)
    from PIL import Image
    with Image.open(path) as im:im.verify()
    files.append(keyed.identity(path))

rows=[r for r in metric['comparisons'] if r['tolerance'] is not None]
groups=[]
for row in rows:
    key=(row['family'],row['plane'],row['group'])
    if key not in groups:groups.append(key)
ratio=[max(r['normalized_error']/r['tolerance'] for r in rows
           if (r['family'],r['plane'],r['group'])==key) for key in groups]
fig,ax=plt.subplots(figsize=(12,7))
bars=ax.barh(range(len(groups)),np.maximum(ratio,1e-14),color=[ORANGE if x>1 else BLUE for x in ratio],edgecolor=INK,linewidth=.5)
for bar,value in zip(bars,ratio):
    if value>1:bar.set_hatch('//')
ax.set_yticks(range(len(groups)),[' / '.join(k) for k in groups],fontsize=8)
ax.set_xscale('log');ax.axvline(1,color='black',linestyle='--',label='Original tolerance')
ax.set_xlabel('Maximum observed normalized error / original tolerance (zero shown at 1e-14)')
ax.set_title(a.comparison_label+' — original metric groups\nMetric visualization alone does not qualify a precursor or production case')
ax.legend();ax.grid(axis='x',alpha=.2);save(fig,'original-tolerance-ratios.png')

fields=['f','ux','uy','uz','p','pf','rho']
matrix=[]
unavailable=[]
for label,r in records:
    matrix.append([max(r['summaries']['cell/'+str(g)+'/'+k]['max_point_normalized']
                       for g in (0,1,2) if 'cell/'+str(g)+'/'+k in r['summaries']) for k in fields])
    unavailable.append([any(not r['summaries']['cell/'+str(g)+'/'+k].get('complete_numeric_coverage',True)
                            for g in (0,1,2) if 'cell/'+str(g)+'/'+k in r['summaries']) for k in fields])
fig,ax=plt.subplots(figsize=(10,6))
z=np.log10(np.maximum(np.array(matrix),1e-16))
im=ax.imshow(z,aspect='auto',vmin=-16,vmax=0,cmap=BLUE_MAP)
ax.set_xticks(range(len(fields)),fields)
ax.set_yticks(range(len(records)),[x[0] for x in records],fontsize=8)
for row in range(len(records)):
    for col in range(len(fields)):
        if unavailable[row][col]:ax.text(col,row,'?',ha='center',va='center',color=ORANGE,fontsize=12,
                                        bbox={'facecolor':'white','edgecolor':INK,'boxstyle':'square,pad=0.1'})
ax.set_title('Descriptive finite-pair state differences — not an acceptance test\n? means incomplete numeric coverage; see retained nonfinite counts, never interpret as full equality')
fig.colorbar(im,ax=ax,label='log10 max point-normalized difference; exact zero displayed at -16')
save(fig,'state-event-difference-map.png')

selected=[(label,r) for label,r in records if label=='matched-next-post_projection']
if len(selected)!=1:raise ValueError('one matched completed-projection pressure state required')
label,r=selected[0]
for side in ('left','right'):
    if keyed.identity(Path(r[side]['path']))!=r[side]:
        raise ValueError('changed observed field bytes')
def slice_data(left,right):
    out=[]
    with keyed.regular(left).open('rb') as f,keyed.regular(right).open('rb') as g:
        h,j=keyed.header(f),keyed.header(g)
        if h['cell_count']!=j['cell_count']:raise ValueError('different topology')
        for start in range(0,h['cell_count'],4096):
            n=min(4096,h['cell_count']-start)
            x=np.fromfile(f,dtype=keyed.DTYPES['cell'],count=n)
            y=np.fromfile(g,dtype=keyed.DTYPES['cell'],count=n)
            if not np.array_equal(x['key'],y['key']) or not np.array_equal(x['geometry'],y['geometry']):
                raise ValueError('field-slice join mismatch')
            k=x['key'];b=x['geometry'];v=x['value'];dh=h['exit_x']/15
            keep=(k[:,4]!=0)&(k[:,5]!=0)&(k[:,6]!=0)&(k[:,7]==0)&(v[:,9]>1e-8)
            keep&=(b[:,2]-.5*b[:,3]<=0)&(0<b[:,2]+.5*b[:,3])&(b[:,0]>=0)&(b[:,0]<=h['exit_x']+dh)
            if keep.any():out.append(np.column_stack((b[keep,:2],b[keep,3],v[keep,7],y['value'][keep,7])))
    if not out:raise ValueError('empty actual midplane slice')
    return h,np.concatenate(out)
h,data=slice_data(Path(r['left']['path']),Path(r['right']['path']))
lo=float(min(data[:,3].min(),data[:,4].min()));hi=float(max(data[:,3].max(),data[:,4].max()))
delta=data[:,4]-data[:,3];dmax=float(max(abs(delta.min()),abs(delta.max()),1e-16))
fig,axes=plt.subplots(3,1,figsize=(13,7),sharex=True,sharey=True)
for ax,values,title,lims,cmap in zip(axes,[data[:,3],data[:,4],delta],
    ['Continuous','Restored','Restored minus continuous'],[(lo,hi),(lo,hi),(-dmax,dmax)],[BLUE_MAP,BLUE_MAP,SIGNED_MAP]):
    patches=[Rectangle((x-d/2,y-d/2),d,d) for x,y,d in data[:,:3]]
    pc=PatchCollection(patches,cmap=cmap,edgecolor='none');pc.set_array(values);pc.set_clim(*lims)
    ax.add_collection(pc);ax.set_xlim(0,h['exit_x']*16/15)
    ax.set_ylim(-a.view_half_width_dh*h['exit_x']/15,a.view_half_width_dh*h['exit_x']/15)
    ax.set_aspect('equal');ax.set_ylabel('y [code length]');ax.set_title(title,fontsize=10)
    fig.colorbar(pc,ax=ax,label='p [code pressure]',shrink=.8)
axes[-1].set_xlabel('x [code length]')
fig.suptitle(f'Actual z=0 intersecting liquid-path cells; {label}; i={h["i"]}, t={h["t"]:.17g}\nShared coordinate and absolute-pressure limits; no pressure-offset subtraction',fontsize=10)
save(fig,'same-stage-pressure-midplane.png')
manifest={'schema':'internal_nozzle_diagnostic_visual_index_v1','source_comparison':keyed.identity(a.comparison/'summary.json'),
          'metric_comparison':keyed.identity(metric_path),
          'files':files,'comparison_label':a.comparison_label,
          'fixed_view_half_width_dh':a.view_half_width_dh,'pressure_event':label,
          'claim_boundary':'Observed diagnostic comparison; no restart/precursor/production acceptance inferred from the visualization.'}
with (a.output/'visual-index.json').open('x') as f:json.dump(manifest,f,indent=2);f.write('\n')
print(json.dumps({'decoded_files':len(files),'output':str(a.output)}))
