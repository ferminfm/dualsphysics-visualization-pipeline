"""Synthetic persistence/parser regression, not a numerical qualification."""
import ctypes as ct,json,pathlib,subprocess,sys
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]/'scripts'))
import verify_internal_nozzle_step_integral as verifier
from test_internal_nozzle_step_metadata import PythonCheckpointTests

ROOT=pathlib.Path(__file__).parents[1]
class State(ct.Structure):
    _fields_=[('seen',ct.c_uint),('bc',ct.c_int*7)]

@pytest.fixture(scope='module')
def native(tmp_path_factory):
    folder=tmp_path_factory.mktemp('SYNTHETIC-stencil-parser');lib=folder/'parser.so'
    code='#include "internal_nozzle_stencil_metadata.h"\nint field(const char*l,InternalNozzleStencilMetadata*s){return internal_nozzle_stencil_metadata_field(l,s);}\nint complete(const InternalNozzleStencilMetadata*s){return internal_nozzle_stencil_metadata_complete(s);}\n'
    subprocess.run(['cc','-std=c11','-shared','-fPIC','-x','c','-I'+str(ROOT/'cases/basilisk'),'-o',str(lib),'-'],input=code,text=True,check=True,capture_output=True,timeout=30)
    out=ct.CDLL(str(lib));out.field.argtypes=[ct.c_char_p,ct.POINTER(State)];out.complete.argtypes=[ct.POINTER(State)];return out

def parse(native,lines):
    s=State()
    for line in lines:
        if native.field((line+'\n').encode(),ct.byref(s))!=1:return False,s
    return native.complete(ct.byref(s))==1,s

BASE=['stencil_closure_schema=internal_nozzle_stencil_bc_v1','stencil_bc=0,1,2,3,4,5,7']
def test_native_roundtrip_preserves_dirty_and_valid_bits(native):
    good,s=parse(native,BASE);assert good;assert list(s.bc)==[0,1,2,3,4,5,7]

@pytest.mark.parametrize('lines',[BASE[:1],BASE[1:],BASE+[BASE[0]],BASE+[BASE[1]],
    [BASE[0],'stencil_bc=0,1,2,3,4,5,8'],[BASE[0],'stencil_bc=0,1,2,3,4,5,-1'],
    [BASE[0],'stencil_bc=0,1,2,3,4,5,7tail'],[BASE[0],'stencil_bc=0,1,2,3,4,5,7,0'],
    [BASE[0],'stencil_bc=00,1,2,3,4,5,7'],[BASE[0],'stencil_bc=0,1,2,3,4,5'],
    [BASE[0].replace('_v1','_v2'),BASE[1]],[BASE[0],'stencil_unknown=0']])
def test_native_rejects_missing_duplicate_unknown_or_invalid(native,lines):
    assert not parse(native,lines)[0]

def test_python_v9_retains_v8_and_original_volume_criteria():
    old=PythonCheckpointTests().fields();new=dict(old,schema='internal_nozzle_checkpoint_metadata_v9',
        stencil_closure_schema='internal_nozzle_stencil_bc_v1',stencil_bc='0,1,2,3,4,5,7')
    assert verifier.checkpoint_state_from_fields(old)==verifier.checkpoint_state_from_fields(new)
    assert verifier.checkpoint_stencil_from_fields(new)==[0,1,2,3,4,5,7]
    assert (verifier.RTOL,verifier.ATOL)==(5e-8,1e-12)
    for key in verifier.CHECKPOINT_STENCIL_KEYS:
        bad=dict(new);del bad[key]
        with pytest.raises(ValueError):verifier.checkpoint_state_from_fields(bad)
    bad=dict(old,stencil_closure_schema='internal_nozzle_stencil_bc_v1',stencil_bc='0,1,2,3,4,5,7')
    with pytest.raises(ValueError):verifier.checkpoint_state_from_fields(bad)

def test_source_uses_recorded_flags_after_exact_value_restoration():
    s=(ROOT/'cases/basilisk/rectangular_internal_nozzle_convergence_visual.c').read_text()
    block=s.split('event stability (i++, last) {',1)[1].split('event pressure_update',1)[0]
    assert block.index('internal_nozzle_restore_prediction_closure_v4')<block.index('internal_nozzle_write_prediction_closure_v4')<block.index('internal_nozzle_apply_stencil_metadata')<block.index('write_forensic_probe')
    assert 'for (scalar s in fields) s.stencil.bc = pending_stencil_metadata.bc[k++]' in s
    assert 'for (scalar s in fields) state.bc[k++] = s.stencil.bc' in s
    assert 'fields[k].stencil' not in s
    assert 'metadata without stencil closure is historical-diagnostic-only' in s
    prior=subprocess.check_output(['git','show','0cf0732d761d3a2cffdaae83087343533bf89491:cases/basilisk/rectangular_internal_nozzle_convergence_visual.c'],cwd=ROOT,text=True)
    assert 'internal_nozzle_apply_stencil_metadata' not in prior
