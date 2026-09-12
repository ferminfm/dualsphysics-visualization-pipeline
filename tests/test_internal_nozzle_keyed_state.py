import importlib.util,json
from pathlib import Path
import numpy as np
import pytest

s=importlib.util.spec_from_file_location('keyed',Path(__file__).resolve().parents[1]/'scripts/compare_internal_nozzle_keyed_state.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_native_leaf_flag_not_shadowed():
    source=(Path(__file__).resolve().parents[1]/'cases/basilisk/internal_nozzle_state_audit.h').read_text()
    assert 'char leaf[' not in source # is_leaf(cell) expands using Basilisk's leaf flag
    assert 'char snapshot_leaf[' in source

def test_compact_operator_hooks_are_bounded_observations():
    root=Path(__file__).resolve().parents[1]/'cases/basilisk'
    source=(root/'rectangular_internal_nozzle_convergence_visual.c').read_text()
    for name in ('prediction','projection'):
        body=source.split('void internal_nozzle_'+name+'_trace_stage',1)[1]
        compact=body.split('if (enable_forensic_probes == 2) {',1)[1].split('return;',1)[0]
        assert 'forensic_snapshot_end_time >= 0.' in compact
        assert 'internal_nozzle_state_audit(' in compact
        assert all(call not in compact for call in ('boundary(', 'restriction(', 'event(', 'project('))
    audit=(root/'internal_nozzle_state_audit.h').read_text()
    assert 'strcmp(phase, "before_prediction")' in audit
    assert 'strcmp(phase, "after_prediction_pre_projection")' in audit
    assert 't > forensic_snapshot_end_time + 1e-14' in audit

def write(p,delta=0,key=1,bad=None):
    h={'schema':'internal_nozzle_keyed_state_v1','endian':'little','phase':'synthetic_only','t':1.,'i':2,'dt':.1,'exit_x':2.,'cell_count':2,'face_count':3,'cell_bytes':168,'face_bytes':100}
    if bad:h.update(bad)
    c=np.zeros(2,dtype=m.DTYPES['cell']);f=np.zeros(3,dtype=m.DTYPES['face'])
    c['key'][:,0]=1;c['key'][:,1]=[key,2];c['key'][:,4:7]=1;c['geometry'][:,3]=1;c['value'][:,10]=1
    c['value'][0,7]=delta
    f['key'][:,0]=[0,1,2];f['geometry'][:,3]=1
    with p.open('wb') as out:out.write((json.dumps(h)+'\n').encode());c.tofile(out);f.tofile(out)

def test_identical_and_known_norm(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a);write(b)
    assert all(x['changed_count']==0 for x in m.compare(a,b)['summaries'].values())
    write(b,delta=.1);r=m.compare(a,b)['summaries']['cell/0/p']
    assert r['changed_count']==1 and r['max_absolute']==.1
    assert r['weighted_relative_l2']==pytest.approx(.1/np.sqrt(2))

@pytest.mark.parametrize('bad',[{'schema':'bad'},{'endian':'big'},{'cell_bytes':169},{'cell_count':0},{'i':3},{'t':2.}])
def test_wrong_header(tmp_path,bad):
    a,b=tmp_path/'a',tmp_path/'b';write(a);write(b,bad=bad)
    with pytest.raises(ValueError):m.compare(a,b)

def test_wrong_keys_nonfinite_truncation_and_symlink(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a);write(b,key=3)
    with pytest.raises(ValueError,match='not aligned'):m.compare(a,b)
    write(b,delta=float('nan'))
    with pytest.raises(ValueError,match='nonfinite'):m.compare(a,b)
    write(b);data=b.read_bytes();b.write_bytes(data[:-1])
    with pytest.raises(ValueError,match='truncated'):m.compare(a,b)
    link=tmp_path/'link';link.symlink_to(a)
    with pytest.raises(ValueError,match='nonregular'):m.compare(a,link)

def test_duplicate_header_and_missing(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';write(a);data=a.read_bytes();b.write_bytes(data.replace(b'{',b'{"schema":"duplicate",',1))
    with pytest.raises(ValueError,match='duplicate'):m.compare(a,b)
    with pytest.raises(ValueError,match='missing'):m.compare(a,tmp_path/'absent')
