"""Isolated inert fixtures only; no compiler, CFD or real qualification claim."""
import copy
import pytest
from test_internal_nozzle_qualification import fixture,git,write
import internal_nozzle_qualification as gate

def frozen_fixture(tmp_path,monkeypatch):
    f=fixture(tmp_path,monkeypatch)
    c=f['contract'];a=f['authority'];root=f['root']
    original=a['source_commit']
    note=root/'docs/restart-pressure-repeatability-controller.md'
    note.parent.mkdir();note.write_text('SYNTHETIC controller identity, no CFD\n')
    git(root,'add','docs/restart-pressure-repeatability-controller.md')
    git(root,'commit','-qm','SYNTHETIC controller-only descendant')
    control=git(root,'rev-parse','HEAD')
    monkeypatch.setattr(gate,'FROZEN_REFERENCE_SOURCE',original)
    monkeypatch.setattr(gate,'FROZEN_REFERENCE_BINARY',c['solver']['sha256'])
    monkeypatch.setattr(gate,'FROZEN_REFERENCE_BUNDLE',c['source_bundle_manifest']['sha256'])
    c['restore']={'kind':'fresh'}
    c['solver_argv'][c['solver_argv'].index('--end-time')+1]=str(1.1*gate.DH)
    a.update(control_source_commit=control,purpose='instrumentation_equivalence',maximum_t_star=1.1,plan_t_star=1.1,plan_end_time=1.1*gate.DH,synthetic_root=None)
    a['binding']=gate.binding(c)
    write(f['a'],a)
    return f

def test_complete_frozen_science_separate_controller_validation(tmp_path,monkeypatch):
    f=frozen_fixture(tmp_path,monkeypatch)
    a=gate.validate(f['a'],f['contract'])
    assert a['source_commit']!=a['control_source_commit']
    assert not (f['run']/'SPAWN_MARKER').exists()

@pytest.mark.parametrize('defect',['wrong_control','production','restore','changed_source','changed_binary','changed_bundle','long_horizon','multiple_starts','synthetic_authority','noncontroller_diff','missing_control'])
def test_frozen_lane_fails_closed(tmp_path,monkeypatch,defect):
    f=frozen_fixture(tmp_path,monkeypatch);a=f['authority'];c=f['contract']
    if defect=='wrong_control':a['control_source_commit']='0'*40
    elif defect=='production':a['mode']='production'
    elif defect=='restore':c['restore']={'kind':'checkpoint'};a['binding']=gate.binding(c)
    elif defect=='changed_source':a['source_commit']='1'*40
    elif defect=='changed_binary':monkeypatch.setattr(gate,'FROZEN_REFERENCE_BINARY','2'*64)
    elif defect=='changed_bundle':monkeypatch.setattr(gate,'FROZEN_REFERENCE_BUNDLE','3'*64)
    elif defect=='long_horizon':a['maximum_t_star']=2.1
    elif defect=='multiple_starts':a['maximum_starts']=2
    elif defect=='synthetic_authority':a['synthetic_root']=str(f['s'])
    elif defect=='missing_control':a.pop('control_source_commit')
    elif defect=='noncontroller_diff':
        other=f['root']/'unrelated.txt';other.write_text('SYNTHETIC unauthorized change')
        git(f['root'],'add','unrelated.txt');git(f['root'],'commit','-qm','SYNTHETIC unauthorized difference');a['control_source_commit']=git(f['root'],'rev-parse','HEAD')
    write(f['a'],a)
    with pytest.raises(ValueError):gate.validate(f['a'],c)
    assert not (f['run']/'SPAWN_MARKER').exists()
