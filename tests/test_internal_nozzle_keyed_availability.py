import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
"""Synthetic availability diagnostics do not weaken strict field comparison."""
import json
import numpy as np
import pytest
import compare_internal_nozzle_keyed_availability as m

def write(path,values=(0.,0.),key=1,geometry_nan=False):
    h={'schema':'internal_nozzle_keyed_state_v1','endian':'little','phase':'synthetic_only','t':1.,'i':2,'dt':.1,'exit_x':2.,'cell_count':2,'face_count':3,'cell_bytes':168,'face_bytes':100}
    c=np.zeros(2,dtype=m.DTYPES['cell']);f=np.zeros(3,dtype=m.DTYPES['face'])
    c['key'][:,0]=1;c['key'][:,1]=[key,2];c['key'][:,4:7]=1
    c['geometry'][:,3]=1;c['value'][:,9:11]=1;c['value'][:,7]=values
    if geometry_nan:c['geometry'][0,0]=np.nan
    f['key'][:,0]=[0,1,2];f['geometry'][:,3]=1
    with path.open('wb') as out:out.write((json.dumps(h)+'\n').encode());c.tofile(out);f.tofile(out)

def test_strict_default_still_rejects_nan(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a);write(b,(np.nan,0))
    with pytest.raises(ValueError,match='nonfinite'):m.compare(a,b)

def test_unavailable_is_not_zero_error_or_qualified(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a,(np.nan,2));write(b,(np.nan,2.1))
    r=m.compare(a,b,availability_diagnostic=True);s=r['summaries']['cell/0/p']
    assert r['complete_numeric_coverage'] is False
    assert s['count']==2 and s['finite_pair_count']==1
    assert s['nonfinite_left_count']==s['nonfinite_right_count']==1
    assert s['nonfinite_bitwise_disagreement_count']==0
    assert s['max_absolute']==pytest.approx(.1)
    assert s['weighted_relative_l2']==pytest.approx(.1/2.1)
    assert s['norm_scope']=='finite_paired_subset_only_not_full_field_equivalence'
    assert 'certificate' in r['claim_boundary']

def test_nonfinite_pattern_disagreement_retained(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a,(np.nan,2));write(b,(float('inf'),2))
    s=m.compare(a,b,availability_diagnostic=True)['summaries']['cell/0/p']
    assert s['nonfinite_bitwise_disagreement_count']==1
    assert s['nonfinite_support_min']==[0,0,0]

def test_all_unavailable_has_no_numeric_norm(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a,(np.nan,np.nan));write(b,(np.nan,np.nan))
    s=m.compare(a,b,availability_diagnostic=True)['summaries']['cell/0/p']
    assert s['finite_pair_count']==0 and s['weighted_relative_l2'] is None
    assert not s['complete_numeric_coverage']

def test_exact_topology_geometry_paths_still_required(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a);write(b,key=3)
    with pytest.raises(ValueError,match='not aligned'):m.compare(a,b,availability_diagnostic=True)
    write(a,geometry_nan=True);write(b,geometry_nan=True)
    with pytest.raises(ValueError):m.compare(a,b,availability_diagnostic=True)
    with pytest.raises(ValueError):m.compare(a,tmp_path/'missing',availability_diagnostic=True)

def test_finite_result_agrees_with_strict_mode(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a,(1,2));write(b,(1,2.1))
    strict=m.compare(a,b);diagnostic=m.compare(a,b,availability_diagnostic=True)
    assert strict['summaries']==diagnostic['summaries']
    assert diagnostic['complete_numeric_coverage'] is True
