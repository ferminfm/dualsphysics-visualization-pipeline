"""Independently reconstruct accepted-step plane-flow endpoint trapezoids.

This checks bookkeeping and provenance, NOT restart or production acceptance.
The solver's staged VOF/velocity samples must be declared explicitly. Sparse
output reconstruction is a distinct approximation, never substituted here.
"""
import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import re

RTOL = 5e-8
ATOL = 1e-12
SCHEMA = 'internal_nozzle_accepted_step_integral_v1'
FUNCTIONAL = 'trapezoid_net_plane_Q_l_and_endpoint_clipped_net_Q_l'
STAGE = 'end_timestep_after_projection_before_adaptation'
PHASE_CONVENTION = 'VOF_at_step_midpoint_velocity_at_step_end'
QUADRATURE = 'exact_rectangular_aperture_leaf_overlap_v1'
STATE_KEYS = {'schema','accepted_steps','last_iteration','time','previous_flow',
              'net_volume','positive_volume','execution_id','case_role',
              'source_commit','solver_sha256','schedule_sha256','nozzle_scale_volume'}
ROW_KEYS = {'schema','step_index','iteration','accepted','begin','end','dt',
            'Q_left','Q_right','net_increment','positive_increment','net_volume',
            'positive_volume','normalized_net_volume','normalized_positive_volume',
            'stage','phase_convention','functional','plane','quadrature',
            'execution_id','case_role','source_commit','solver_sha256','schedule_sha256'}
CHECKPOINT_BASE_KEYS = set('''schema case_id execution_id segment_id case_role solver_sha256
predecessor_segment_id restore_checkpoint_sha256 restore_metadata_sha256 restore_closure_sha256
source_sha256 scientific_source_commit schedule_version schedule_sha256 master_tick target_time
actual_time iteration maxlevel grid_maxdepth domain_x0 domain_y0 domain_z0 domain_l0 initial_state
inlet_mode precursor_transfer_sha256 precursor_pressure_mode profile_bulk_velocity profile_target_flow
pressure_provenance gravity_enabled restored_from initial_liquid_volume cumulative_liquid_inflow
cumulative_liquid_outflow cumulative_nozzle_exit_discharge cumulative_nozzle_exit_net_volume
cumulative_discharged_liquid_volume cumulative_nozzle_exit_discharge_definition previous_liquid_inflow_rate
previous_liquid_outflow_rate previous_nozzle_exit_flow last_mass_balance_time last_nozzle_discharge_time
solver_dt solver_dtmax timestep_previous mgp_nrelax mgpf_nrelax mgu_nrelax initial_interface_proxy
max_interface_growth max_active_front max_post_tag_count max_detached_proxy_count max_one_cell_debris_count
prediction_closure_schema prediction_closure_state'''.split())
CHECKPOINT_STEP_KEYS = {'accepted_step_schema','accepted_step_count','accepted_step_iteration',
 'accepted_step_time','accepted_step_previous_Q','accepted_step_net_volume',
 'accepted_step_positive_volume','accepted_step_nozzle_scale'}

def checkpoint_state_from_fields(fields):
    if set(fields)!=CHECKPOINT_BASE_KEYS|CHECKPOINT_STEP_KEYS or fields['schema']!='internal_nozzle_checkpoint_metadata_v8':
        raise ValueError('unsupported/incomplete accepted-step checkpoint metadata')
    state=initial_state({'schema':fields['accepted_step_schema'],
        'accepted_steps':fields['accepted_step_count'],'last_iteration':fields['accepted_step_iteration'],
        'time':fields['accepted_step_time'],'previous_flow':fields['accepted_step_previous_Q'],
        'net_volume':fields['accepted_step_net_volume'],'positive_volume':fields['accepted_step_positive_volume'],
        'nozzle_scale_volume':fields['accepted_step_nozzle_scale'],'execution_id':fields['execution_id'],
        'case_role':fields['case_role'],'source_commit':fields['scientific_source_commit'],
        'solver_sha256':fields['solver_sha256'],'schedule_sha256':fields['schedule_sha256']})
    if state['last_iteration']!=integer(fields['iteration']) or state['time']!=number(fields['actual_time'])+number(fields['solver_dt']) or number(fields['solver_dt'])<=0:
        raise ValueError('accepted-step state contradicts native checkpoint interval')
    return state

def load_checkpoint_state(path):
    fields={}
    with regular(path).open() as stream:
        for line in stream:
            if '=' not in line:raise ValueError('malformed checkpoint metadata')
            key,value=line.rstrip('\n').split('=',1)
            if key in fields:raise ValueError('duplicate checkpoint metadata')
            fields[key]=value
    return checkpoint_state_from_fields(fields)

def unique(pairs):
    out={}
    for key,value in pairs:
        if key in out: raise ValueError('duplicate mapping key: '+key)
        out[key]=value
    return out

def regular(path):
    path=Path(path)
    if '..' in path.parts or any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():
        raise ValueError('missing, traversing, or nonregular input')
    return path

def file_identity(path):
    path=regular(path); h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(65536),b''): h.update(chunk)
    return {'path':str(path),'size_bytes':path.stat().st_size,'sha256':h.hexdigest()}

def number(value):
    if isinstance(value,bool): raise ValueError('boolean is not a numeric measurement')
    x=float(value)
    if not math.isfinite(x): raise ValueError('nonfinite number')
    return x

def integer(value):
    if isinstance(value,bool) or not re.fullmatch(r'-?(0|[1-9][0-9]*)',str(value)):
        raise ValueError('non-integer counter')
    return int(value)

def initial_state(state):
    if set(state)!=STATE_KEYS or state['schema']!=SCHEMA:
        raise ValueError('unsupported integral state')
    s=dict(state)
    for key in ('accepted_steps','last_iteration'): s[key]=integer(s[key])
    for key in ('time','previous_flow','net_volume','positive_volume','nozzle_scale_volume'): s[key]=number(s[key])
    if not 0<=s['accepted_steps']<2**64-1 or not -1<=s['last_iteration']<2**63-1 or s['accepted_steps']!=s['last_iteration']+1 or s['time']<0 or s['positive_volume']<0 or s['nozzle_scale_volume']<=0:
        raise ValueError('invalid integral state range')
    if not isinstance(s['execution_id'],str) or not s['execution_id'] or s['case_role'] not in ('A','B'):
        raise ValueError('invalid case/execution identity')
    for key,n in [('source_commit',40),('solver_sha256',64),('schedule_sha256',64)]:
        if not re.fullmatch('[0-9a-f]{'+str(n)+'}',s[key]): raise ValueError('malformed material identity')
    if s['accepted_steps']==0 and (s['last_iteration']!=-1 or s['time']!=0 or s['net_volume']!=0 or s['positive_volume']!=0):
        raise ValueError('nonzero initialization offset requires a bound prior checkpoint')
    return s

def close(a,b): return math.isclose(number(a),number(b),rel_tol=RTOL,abs_tol=ATOL)

def verify(rows,state,expected_steps,expected_end,expected_final_state=None):
    """Rows are consumed once, in native order; never sorted or gap-filled.

    Independent Decimal summation cross-checks the float serial sum. Expected
    coverage comes from a separately bound terminal/checkpoint contract.
    """
    expected_steps=integer(expected_steps)
    if expected_steps<0:raise ValueError('negative expected step count')
    s=initial_state(state); original=dict(s); failures=[]; counts=0
    with localcontext() as ctx:
        ctx.prec=50
        decimal_net=Decimal.from_float(s['net_volume'])
        decimal_pos=Decimal.from_float(s['positive_volume'])
        for row in rows:
            if set(row)!=ROW_KEYS: raise ValueError('missing/unknown accepted-step columns')
            if row['schema']!=SCHEMA or row['stage']!=STAGE or row['phase_convention']!=PHASE_CONVENTION or row['functional']!=FUNCTIONAL or row['plane']!='exit' or row['quadrature']!=QUADRATURE:
                raise ValueError('different stage/phase/functional/plane/quadrature')
            for key in ('execution_id','case_role','source_commit','solver_sha256','schedule_sha256'):
                if row[key]!=s[key]: raise ValueError('contradictory material identity: '+key)
            if str(row['accepted']).lower()!='true': raise ValueError('rejected/unknown step in accepted-step trace')
            step,iteration=integer(row['step_index']),integer(row['iteration'])
            if step!=s['accepted_steps']+1 or iteration!=s['last_iteration']+1 or not 0<=iteration<2**63-1 or not 1<=step<2**64-1:
                raise ValueError('duplicate, omitted, permuted, or wrong restart step')
            begin,end,dt=map(number,(row['begin'],row['end'],row['dt']))
            left,right=map(number,(row['Q_left'],row['Q_right']))
            if abs(begin-s['time'])>1e-12 or not end>begin or not math.isclose(dt,end-begin,rel_tol=1e-14,abs_tol=1e-15):
                raise ValueError('noncontiguous or zero/rejected time interval')
            if left!=s['previous_flow']: raise ValueError('previous sample not restored exactly')
            delta=end-begin
            net=0.5*(left+right)*delta
            pos=0.5*(max(left,0.)+max(right,0.))*delta
            s['net_volume']+=net; s['positive_volume']+=pos
            dd=Decimal.from_float(end)-Decimal.from_float(begin)
            decimal_net+=(Decimal.from_float(left)+Decimal.from_float(right))*dd/2
            decimal_pos+=(max(Decimal.from_float(left),Decimal(0))+max(Decimal.from_float(right),Decimal(0)))*dd/2
            expected={'net_increment':net,'positive_increment':pos,'net_volume':s['net_volume'],
                      'positive_volume':s['positive_volume'],
                      'normalized_net_volume':s['net_volume']/s['nozzle_scale_volume'],
                      'normalized_positive_volume':s['positive_volume']/s['nozzle_scale_volume']}
            for key,value in expected.items():
                if not close(row[key],value): failures.append({'step':step,'metric':key,'observed':number(row[key]),'independent':value})
            s.update(accepted_steps=step,last_iteration=iteration,time=end,previous_flow=right)
            counts+=1
        if counts!=expected_steps or abs(s['time']-number(expected_end))>1e-12:
            raise ValueError('incomplete accepted-step coverage against declared terminal')
        for key,high_precision in [('net_volume',decimal_net),('positive_volume',decimal_pos)]:
            if not close(s[key],float(high_precision)): failures.append({'metric':'high_precision_'+key,'observed':s[key],'independent':float(high_precision)})
        if expected_final_state is not None:
            final=initial_state(expected_final_state)
            for key in STATE_KEYS:
                same=close(final[key],s[key]) if key in ('net_volume','positive_volume') else final[key]==s[key]
                if not same: raise ValueError('final checkpoint integral state mismatch: '+key)
        return {'schema':SCHEMA+'_verification','passed':not failures,'checked_steps':counts,
                'absolute_tolerance':ATOL,'relative_tolerance':RTOL,'initial_state':original,
                'computed_final_state':s,'decimal_net_volume':str(decimal_net),'decimal_positive_volume':str(decimal_pos),
                'failures':failures,'scientific_claim':'same-step bookkeeping only; no restart or production certificate inferred'}

def load_state(path):
    return json.loads(regular(path).read_text(),object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def csv_rows(path):
    with regular(path).open(newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames is None or len(reader.fieldnames)!=len(set(reader.fieldnames)):
            raise ValueError('duplicate/missing CSV header')
        yield from reader

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('trace','initial-state','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--final-state',type=Path);p.add_argument('--expected-steps',type=int,required=True);p.add_argument('--expected-end',type=float,required=True)
    a=p.parse_args()
    result=verify(csv_rows(a.trace),load_state(a.initial_state),a.expected_steps,a.expected_end,load_state(a.final_state) if a.final_state else None)
    result['inputs']=[file_identity(x) for x in (a.trace,a.initial_state,a.final_state) if x]
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'passed':result['passed'],'checked_steps':result['checked_steps'],'failures':len(result['failures'])}))
    raise SystemExit(0 if result['passed'] else 1)

if __name__=='__main__': main()
