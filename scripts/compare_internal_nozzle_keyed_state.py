"""Streaming, identity-exact field comparison of bounded native observations.

Does not certify a restart. Different stage labels remain explicit in output.
Weights are cell metric volume on active cells, geometric volume on inactive
cells, and geometric area on faces. Spatial support includes every changed row.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

CELL_FIELDS = 'f ux uy uz gx gy gz p pf cs cm un rho'.split()
FACE_FIELDS = 'uf fs fm a alpha mu'.split()
DTYPES = {'cell': np.dtype([('key','<i4',8),('geometry','<f8',4),('value','<f8',13)]),
          'face': np.dtype([('key','<i4',5),('geometry','<f8',4),('value','<f8',6)])}


def regular(path):
    path = Path(path)
    if '..' in path.parts or any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():
        raise ValueError('missing/traversing/nonregular state')
    return path


def identity(path):
    h=hashlib.sha256()
    with regular(path).open('rb') as f:
        for block in iter(lambda:f.read(65536),b''): h.update(block)
    return {'path':str(path),'size_bytes':path.stat().st_size,'sha256':h.hexdigest()}


def header(f):
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out: raise ValueError('duplicate header key')
            out[k]=v
        return out
    line=f.readline(4097)
    if len(line)>4096 or not line.endswith(b'\n'): raise ValueError('malformed bounded header')
    h=json.loads(line,object_pairs_hook=unique)
    required={'schema','endian','phase','t','i','dt','exit_x','cell_count','face_count','cell_bytes','face_bytes'}
    if set(h)!=required or h['schema']!='internal_nozzle_keyed_state_v1' or h['endian']!='little':
        raise ValueError('unsupported state schema/header')
    for k in ('cell','face'):
        if type(h[k+'_count']) is not int or not 0<h[k+'_count']<=10**8 or h[k+'_bytes']!=DTYPES[k].itemsize:
            raise ValueError('invalid count/record ABI')
    if not all(np.isfinite(h[k]) for k in ('t','dt','exit_x')): raise ValueError('nonfinite header')
    if type(h['i']) is not int or h['i']<0 or not isinstance(h['phase'],str): raise ValueError('bad stage identity')
    expected=len(line)+sum(h[k+'_count']*h[k+'_bytes'] for k in ('cell','face'))
    if Path(f.name).stat().st_size!=expected: raise ValueError('truncated/trailing state payload')
    return h


def compare(left,right):
    left,right=regular(left),regular(right); summaries={}
    with left.open('rb') as l,right.open('rb') as r:
        lh,rh=header(l),header(r)
        if lh['i']!=rh['i'] or abs(lh['t']-rh['t'])>1e-12 or lh['exit_x']!=rh['exit_x']:
            raise ValueError('different time/iteration/geometry identity')
        for kind,labels in [('cell',CELL_FIELDS),('face',FACE_FIELDS)]:
            count=lh[kind+'_count']
            if count!=rh[kind+'_count']: raise ValueError('different topology count')
            for start in range(0,count,4096):
                n=min(4096,count-start); x=np.fromfile(l,dtype=DTYPES[kind],count=n); y=np.fromfile(r,dtype=DTYPES[kind],count=n)
                if not np.array_equal(x['key'],y['key']) or not np.array_equal(x['geometry'],y['geometry']):
                    raise ValueError('key/order/geometry not aligned; no positional bypass')
                if not np.isfinite(x['value']).all() or not np.isfinite(y['value']).all(): raise ValueError('nonfinite observed field')
                if (x['geometry'][:,3]<=0).any(): raise ValueError('invalid cell size')
                if kind=='cell':
                    k=x['key']; active=(k[:,4]!=0)&(k[:,5]!=0)&(k[:,6]!=0)&(k[:,7]==0)
                    groups=np.where(active,np.where(x['geometry'][:,0]<=lh['exit_x'],0,1),2)
                    weights=x['geometry'][:,3]**3*np.where(active,np.clip(x['value'][:,10],0,1),1)
                else:
                    groups=x['key'][:,0]; weights=x['geometry'][:,3]**2
                    if not np.isin(groups,[0,1,2]).all(): raise ValueError('invalid face axis')
                for group in (0,1,2):
                    mask=groups==group
                    if not mask.any():continue
                    w=weights[mask]; xx=x['value'][mask]; yy=y['value'][mask]; xyz=x['geometry'][mask,:3]
                    for col,label in enumerate(labels):
                        key=f'{kind}/{group}/{label}'
                        s=summaries.setdefault(key,{'count':0,'changed_count':0,'max_absolute':0.,'max_point_normalized':0.,'weight_sum':0.,'squared_difference':0.,'squared_left':0.,'squared_right':0.,'support_min':None,'support_max':None})
                        a,b=xx[:,col],yy[:,col]; d=np.abs(a-b); changed=d!=0
                        s['count']+=len(a);s['changed_count']+=int(changed.sum())
                        s['max_absolute']=max(s['max_absolute'],float(d.max()))
                        s['max_point_normalized']=max(s['max_point_normalized'],float((d/np.maximum(1,np.maximum(np.abs(a),np.abs(b)))).max()))
                        s['weight_sum']+=float(w.sum()); s['squared_difference']+=float(np.sum(w*d*d))
                        s['squared_left']+=float(np.sum(w*a*a));s['squared_right']+=float(np.sum(w*b*b))
                        if changed.any():
                            lo=xyz[changed].min(axis=0);hi=xyz[changed].max(axis=0)
                            s['support_min']=lo.tolist() if s['support_min'] is None else np.minimum(lo,s['support_min']).tolist()
                            s['support_max']=hi.tolist() if s['support_max'] is None else np.maximum(hi,s['support_max']).tolist()
    for s in summaries.values():
        weight=s['weight_sum']
        s['weighted_rms_difference']=float(np.sqrt(s['squared_difference']/weight)) if weight else None
        s['weighted_relative_l2']=float(np.sqrt(s['squared_difference'])/max(np.sqrt(weight),np.sqrt(s['squared_left']),np.sqrt(s['squared_right']))) if weight else None
    return {'schema':'internal_nozzle_keyed_state_comparison_v1','left':identity(left),'right':identity(right),
            'left_header':lh,'right_header':rh,'exact_keys_and_geometry':True,'summaries':summaries,
            'claim_boundary':'Observed fields and stage identity; no production/restart certificate inferred.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('left','right','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();result=compare(a.left,a.right)
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'changed_fields':[k for k,v in result['summaries'].items() if v['changed_count']], 'output':str(a.output)}))


if __name__=='__main__':main()
