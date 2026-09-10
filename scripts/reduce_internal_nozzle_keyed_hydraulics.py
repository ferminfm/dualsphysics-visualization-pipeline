"""Independent streaming quadrature on a keyed observation, not live CFD.

Same declared exact rectangular y-z overlap, half-open x plane convention,
fluid-leaf cs>1e-8 mask and clamped liquid fraction as the frozen reducer.
The pressure gauge is retained; no fitted offset or different normalization.
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np

import compare_internal_nozzle_keyed_state as keyed

PLANES = [(0.,'inlet_boundary_adjacent'),(.5,'upstream_plenum'),(1.75,'pre_contraction'),
          (5.25,'post_contraction'),(10.,'mid_straight'),(14.5,'legacy_exit_inner'),
          (15.,'geometric_nozzle_exit'),(15.25,'near_exit_projected_aperture')]

def geometry(g):
    keys={'width','height','Dh','plenum_Dh','contraction_Dh','straight_Dh','plenum_scale','rho_l','rho_g','ambient_pressure'}
    if set(g)!=keys or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in g.values()):
        raise ValueError('invalid declared geometry/properties')
    if any(g[k]<=0 for k in keys-{'ambient_pressure'}) or abs(g['Dh']-2*g['width']*g['height']/(g['width']+g['height']))>1e-14:
        raise ValueError('inconsistent hydraulic diameter or nonpositive property')
    return g

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate geometry key')
        result[key]=value
    return result

def aperture(g,p):
    if p<=g['plenum_Dh']: scale=g['plenum_scale']
    elif p<=g['plenum_Dh']+g['contraction_Dh']:
        a=(p-g['plenum_Dh'])/g['contraction_Dh'];blend=a*a*(3-2*a)
        scale=(1-blend)*g['plenum_scale']+blend
    else:scale=1.
    return g['width']*scale,g['height']*scale

def chunk_integrals(c,g,planes):
    # Explicit keyed identity determines which records are actual fluid leaves.
    k=c['key']; v=c['value']; xyz=c['geometry']; result={}
    if not np.isfinite(xyz).all() or (xyz[:,3]<=0).any():
        raise ValueError('nonfinite/invalid snapshot cell')
    physical_leaf=(k[:,4]!=0)&(k[:,5]!=0)&(k[:,6]!=0)&(k[:,7]==0)
    # Inactive/coarse ghost values are not plane quadrature nodes. Their
    # nonfinite availability is reported separately by reduce(), never used
    # as zero or accepted as numerical equality. Physical leaf values remain
    # strict, including the mask coefficient itself.
    if not np.isfinite(v[physical_leaf]).all():
        raise ValueError('nonfinite physical-leaf snapshot field')
    active=physical_leaf&(v[:,9]>1e-8)
    for plane,label in planes:
        xp=plane*g['Dh']; d=xyz[:,3]
        m=active & (xyz[:,0]-.5*d<=xp) & (xp<xyz[:,0]+.5*d)
        x=xyz[m];values=v[m];dd=x[:,3]
        w,h=aperture(g,min(plane,g['plenum_Dh']+g['contraction_Dh']+g['straight_Dh']))
        aw=np.maximum(0,np.minimum(x[:,1]+dd/2,w/2)-np.maximum(x[:,1]-dd/2,-w/2))*np.maximum(0,np.minimum(x[:,2]+dd/2,h/2)-np.maximum(x[:,2]-dd/2,-h/2))
        keep=aw>0;aw=aw[keep];values=values[keep]
        f=np.clip(values[:,0],0,1);u=values[:,1];p=values[:,7];rho=g['rho_g']+f*(g['rho_l']-g['rho_g'])
        arrays={'fluid_area':aw,'liquid_area':f*aw,'Q_l':f*u*aw,'Q_g':(1-f)*u*aw,
                'I2_liquid':f*u*u*aw,'I3_liquid':f*u*u*u*aw,
                'J_k_mixture':rho*u*u*aw,'J_p':(p-g['ambient_pressure'])*aw}
        result[label]={name:math.fsum(a.tolist()) for name,a in arrays.items()}
        result[label]['intersecting_leaf_count']=int(keep.sum())
    return result

def finalize(totals,g):
    result={}
    for label,t in totals.items():
        a,l,q=t['fluid_area'],t['liquid_area'],t['Q_l']
        if not a>0:raise ValueError('zero declared plane area: '+label)
        p=t['J_p']/a+g['ambient_pressure']; u=q/l if l>0 else 0.
        qg=t['Q_g'];i2=t['I2_liquid'];i3=t['I3_liquid']
        result[label]={**t,'mdot_l':g['rho_l']*q,'mdot_mix':g['rho_l']*q+g['rho_g']*qg,
                       'J_k_liquid':g['rho_l']*i2,'J_total':t['J_k_mixture']+t['J_p'],
                       'area_mean_pressure':p,'area_weighted_liquid_velocity':u,
                       'flux_weighted_liquid_velocity':i2/q if abs(q)>1e-30 else 0.,
                       'beta':i2*l/(q*q) if l>0 and abs(q)>1e-30 else 0.,
                       'alpha':i3*l*l/(q*q*q) if l>0 and abs(q)>1e-30 else 0.,
                       'momentum_equivalent_velocity':math.sqrt(max(0,i2/l)) if l>0 else 0.,
                       'legacy_Q_l_times_area_weighted_velocity':q*u}
    if 'inlet_boundary_adjacent' in result:
        inlet=result['inlet_boundary_adjacent']['area_mean_pressure']
        for t in result.values():t['forcing_to_plane_pressure_drop']=inlet-t['area_mean_pressure']
    return result

def reduce(path,g,planes=PLANES,chunk_size=4096):
    geometry(g);path=keyed.regular(path);sums={label:{} for _,label in planes}
    availability={'total_cells':0,'physical_leaf_cells':0,'excluded_nonfinite_cells':0,
                  'excluded_nonfinite_values':0,'nonfinite_physical_leaf_values':0}
    if chunk_size<1:raise ValueError('invalid chunk size')
    with path.open('rb') as f:
        h=keyed.header(f)
        expected_exit=(g['plenum_Dh']+g['contraction_Dh']+g['straight_Dh'])*g['Dh']
        if abs(h['exit_x']-expected_exit)>1e-14:raise ValueError('snapshot/declared geometry mismatch')
        for start in range(0,h['cell_count'],chunk_size):
            c=np.fromfile(f,dtype=keyed.DTYPES['cell'],count=min(chunk_size,h['cell_count']-start))
            partial=chunk_integrals(c,g,planes)
            k=c['key'];leaf=(k[:,4]!=0)&(k[:,5]!=0)&(k[:,6]!=0)&(k[:,7]==0)
            unavailable=~np.isfinite(c['value'][~leaf])
            availability['total_cells']+=len(c)
            availability['physical_leaf_cells']+=int(leaf.sum())
            availability['excluded_nonfinite_cells']+=int(unavailable.any(axis=1).sum())
            availability['excluded_nonfinite_values']+=int(unavailable.sum())
            for label,values in partial.items():
                for name,value in values.items():sums[label].setdefault(name,[]).append(value)
    totals={label:{k:math.fsum(v) for k,v in values.items()} for label,values in sums.items()}
    return {'schema':'internal_nozzle_independent_keyed_hydraulics_v1','input':keyed.identity(path),
            'observation':h,'declared_geometry':g,'quadrature':'exact_rectangular_aperture_leaf_overlap_v1',
            'planes':finalize(totals,g),'availability':availability,
            'claim_boundary':'Same physical-leaf snapshot/plane integration only; excluded ghost availability is not equality or a production certificate.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','geometry','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();g=json.loads(keyed.regular(a.geometry).read_text(),object_pairs_hook=unique)
    r=reduce(a.snapshot,g);r['geometry_input']=keyed.identity(a.geometry)
    with a.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'planes':len(r['planes']),'output':str(a.output),'state_phase':r['observation']['phase']}))

if __name__=='__main__':main()
