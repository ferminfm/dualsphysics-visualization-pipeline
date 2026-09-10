import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
"""Synthetic reader negatives only; never scientific observations."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('restart_pair',Path(__file__).parents[1]/'scripts'/'audit_internal_nozzle_qualified_restart.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def row(tick=1,plane='exit',time=.1):
    return {'t':str(time),'master_tick':str(tick),'plane_label':plane,'i':'3'}

def test_exact_tick_and_plane_keys():
    out=m.indexed([row(),row(plane='inlet')],'hydraulic',.1)
    assert set(out)=={(1,'exit'),(1,'inlet')}

def test_duplicate_output_fails():
    with pytest.raises(ValueError,match='duplicate'):
        m.indexed([row(),row()],'hydraulic',.1)

def test_nonfinite_time_fails():
    with pytest.raises(ValueError,match='nonfinite'):
        m.indexed([row(time='nan')],'hydraulic',.1)

def test_off_schedule_fails():
    with pytest.raises(ValueError,match='off-schedule'):
        m.indexed([row(time=.10001)],'hydraulic',.1)

def test_integer_counts_not_coerced():
    assert m.exact_integer('12')==12
    for value in ('12.0','01','nan'):
        with pytest.raises(ValueError):m.exact_integer(value)

def test_duplicate_csv_header_fails(tmp_path):
    path=tmp_path/'SYNTHETIC.csv';path.write_text('t,t\n1,1\n')
    with pytest.raises(ValueError,match='columns'):m.rows(path)

def test_singleton_rows_have_closed_join_identity():
    assert set(m.indexed([row()],'raw',.1))=={(1,'singleton')}

def test_master_tick_never_overrides_actual_time():
    with pytest.raises(ValueError,match='off-schedule'):
        m.indexed([row(tick=21,time=.2)],'hydraulic',.1)

def test_physical_argv_identity_ignores_only_declared_metadata():
    left=['solver','--pressure','351.48','--forensic-probes','2','--segment-id','fresh']
    right=['solver','--pressure','351.48','--forensic-probes','2','--segment-id','restore',
           '--restore','checkpoint']
    m.same_physical_argv(left,right)
    right[2]='350'
    with pytest.raises(ValueError,match='physical'):m.same_physical_argv(left,right)

def test_instrumentation_control_requires_real_mode_contrast():
    left=['solver','--forensic-probes','2'];right=['solver','--forensic-probes','0']
    m.same_physical_argv(left,right,True)
    with pytest.raises(ValueError,match='contrast'):m.same_physical_argv(left,left,True)
    with pytest.raises(ValueError,match='physical'):m.same_physical_argv(left,right,False)

def test_duplicate_solver_option_fails():
    with pytest.raises(ValueError,match='duplicate'):
        m.solver_options(['solver','--pressure','351','--pressure','351'])
