import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
"""Synthetic parser/unit checks; these are not measured CFD observations."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('health',Path(__file__).parents[1]/'scripts'/'audit_internal_nozzle_executed_solver_health.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def row():
    return {'dt':'.0004','DT':'.0004','CFL':'.5','grid_maxdepth':'8','maxlevel':'8',
            'total_grid_cells':'300000','mgp_i':'2','mgpf_i':'2','mgu_i':'12',
            'mgp_resa':'20','mgpf_resa':'80','mgu_resa':'0.000006'}

def test_native_projection_residual_normalization():
    values,failures=m.health_row(row())
    assert not failures
    assert values['mgp']==pytest.approx(3.2e-6)
    assert values['mgpf']==pytest.approx(3.2e-6)

@pytest.mark.parametrize('key,value,reason',[
    ('mgp_resa','100','mgp_convergence'),('mgpf_resa','300','mgpf_convergence'),
    ('mgu_resa','.00002','mgu_convergence'),('mgp_i','101','mgp_convergence'),
    ('dt','.001','timestep_or_CFL'),('CFL','.9','timestep_or_CFL'),
    ('grid_maxdepth','7','physical_grid_identity')])
def test_unchanged_executed_limits_fail_closed(key,value,reason):
    value_row=row();value_row[key]=value
    assert reason in m.health_row(value_row)[1]

def test_nonfinite_health_rejected():
    value_row=row();value_row['mgu_resa']='nan'
    with pytest.raises(ValueError,match='nonfinite'):m.health_row(value_row)

def test_negative_residual_rejected():
    value_row=row();value_row['mgpf_resa']='-1'
    assert 'mgpf_convergence' in m.health_row(value_row)[1]
