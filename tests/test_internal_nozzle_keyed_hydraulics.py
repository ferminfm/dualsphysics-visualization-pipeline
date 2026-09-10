import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import importlib.util,json,sys
from pathlib import Path
import numpy as np
import pytest

import reduce_internal_nozzle_keyed_hydraulics as m
G={'width':2.,'height':1.,'Dh':4/3,'plenum_Dh':2.,'contraction_Dh':3.,'straight_Dh':10.,'plenum_scale':3.,'rho_l':1.,'rho_g':.1,'ambient_pressure':0.}
P=[(15.,'geometric_nozzle_exit')]

def cells():
    c=np.zeros(8,dtype=m.keyed.DTYPES['cell']);c['key'][:,0]=3;c['key'][:,1]=np.arange(8);c['key'][:,4:7]=1
    c['geometry'][:,0]=20.;c['geometry'][:,1]=np.repeat([-.75,-.25,.25,.75],2)
    c['geometry'][:,2]=np.tile([-.25,.25],4);c['geometry'][:,3]=.5
    c['value'][:,0]=1;c['value'][:,1]=2;c['value'][:,7]=3;c['value'][:,9:11]=1
    return c

def reduced(c):return m.finalize(m.chunk_integrals(c,G,P),G)['geometric_nozzle_exit']

def test_uniform_exact_integrals():
    r=reduced(cells())
    for k,v in {'fluid_area':2,'liquid_area':2,'Q_l':4,'mdot_l':4,'mdot_mix':4,'I2_liquid':8,'I3_liquid':16,'J_k_liquid':8,'J_k_mixture':8,'J_p':6,'J_total':14,'beta':1,'alpha':1,'momentum_equivalent_velocity':2,'area_weighted_liquid_velocity':2,'flux_weighted_liquid_velocity':2}.items():assert r[k]==pytest.approx(v)

def test_variable_profile_and_mixture():
    c=cells();c['value'][:,1]=np.arange(1,9);c['value'][:,0]=.5
    r=reduced(c);q=.125*sum(range(1,9));i2=.125*sum(x*x for x in range(1,9));i3=.125*sum(x**3 for x in range(1,9))
    assert r['Q_l']==q;assert r['I2_liquid']==i2;assert r['I3_liquid']==i3
    assert r['beta']==pytest.approx(i2/(q*q));assert r['J_k_mixture']==pytest.approx(.55*.25*sum(x*x for x in range(1,9)))

def test_cs_is_mask_not_area_weight():
    c=cells();c['value'][:,9]=.2
    assert reduced(c)['Q_l']==4
    c['value'][0,9]=1e-9;assert reduced(c)['Q_l']==3.5

def test_inactive_boundary_and_plane_half_open():
    c=cells();c['key'][0,7]=1;c['key'][1,5]=0;c['geometry'][2,0]=19.75
    assert reduced(c)['intersecting_leaf_count']==5
    c['geometry'][2,0]=20.25
    assert reduced(c)['intersecting_leaf_count']==6

def test_order_permutation_and_aperture_cut():
    c=cells();assert reduced(c)==reduced(c[::-1])
    c['geometry'][0,1]=-1.;r=reduced(c);assert r['fluid_area']==pytest.approx(1.875)

def test_nonfinite_and_geometry_fail():
    c=cells();c['value'][0,1]=np.nan
    with pytest.raises(ValueError):reduced(c)
    g=dict(G,Dh=2)
    with pytest.raises(ValueError):m.geometry(g)

def test_streaming_chunks_and_exact_file_length(tmp_path):
    p=tmp_path/'synthetic-state.bin';c=cells();face=np.zeros(3,dtype=m.keyed.DTYPES['face'])
    h={'schema':'internal_nozzle_keyed_state_v1','endian':'little','phase':'synthetic_only','t':1.,'i':2,'dt':.1,'exit_x':20.,'cell_count':8,'face_count':3,'cell_bytes':168,'face_bytes':100}
    with p.open('wb') as f:f.write((json.dumps(h)+'\n').encode());c.tofile(f);face.tofile(f)
    assert m.reduce(p,G,P,1)['planes']==m.reduce(p,G,P,8)['planes']
    with p.open('ab') as f:f.write(b'x')
    with pytest.raises(ValueError,match='trailing'):m.reduce(p,G,P)

def test_negative_flow_signed_moments():
    c=cells();c['value'][:,1]=-2;r=reduced(c)
    assert r['Q_l']==-4;assert r['I3_liquid']==-16;assert r['J_k_liquid']==8;assert r['beta']==1;assert r['alpha']==1

def test_excluded_ghost_unavailable_values_are_not_integrands():
    c=cells();c['key'][0,5]=0;c['value'][0,:]=np.nan
    r=reduced(c)
    assert r['Q_l']==3.5
    assert r['intersecting_leaf_count']==7

def test_physical_mask_and_auxiliary_nonfinite_fail_closed():
    for field in (0,1,7,8,9):
        c=cells();c['value'][0,field]=np.nan
        with pytest.raises(ValueError,match='physical-leaf'):reduced(c)
