"""Analyze two completed, exact-material diagnostic segments without CFD.

No acceptance from process RC alone. Structural differences remain explicit;
no field join by guessed row position and no pressure gauge adjustment.
"""
import argparse,csv,hashlib,importlib.util,json,pathlib,subprocess,sys

p=argparse.ArgumentParser()
for key in ('source-root','fresh','restored','freeze','output','reuse-metric-comparison'):
    p.add_argument('--'+key,type=pathlib.Path,required=True)
a=p.parse_args();sys.path.insert(0,str(a.source_root/'scripts'))
import compare_internal_nozzle_keyed_availability as fields

def atomic_new(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')

def terminal(root):
    paths=list((root/'supervision').glob('*/terminal.json'))
    if len(paths)!=1:raise ValueError('one terminal required per diagnostic')
    t=json.loads(paths[0].read_text())
    if t['returncode']!=0 or t['child_exists_after_wait'] is not False:
        raise ValueError('diagnostic lacks successful observable process terminal')
    for stream in ('stdout','stderr'):
        r=fields.identity(paths[0].parent/(stream+'.log'))
        if r['sha256']!=t[stream+'_sha256'] or r['size_bytes']!=t[stream+'_size_bytes']:
            raise ValueError('terminal stream identity mismatch')
    return fields.identity(paths[0]),t

def index(root):
    found={}
    paths=sorted((root/'forensic_probes').glob('state_*.bin'))
    if not paths:raise ValueError('keyed observations missing')
    if len(paths)>100:raise ValueError('unexpected snapshot volume')
    for path in paths:
        with fields.regular(path).open('rb') as f:h=fields.header(f)
        key=(h['phase'],h['i'])
        if key in found:raise ValueError('ambiguous observation stage/iteration')
        found[key]=(path,h)
    return found

if a.output.exists():raise ValueError('analysis output already exists; preserve earlier evidence')
lt,lterm=terminal(a.fresh);rt,rterm=terminal(a.restored)
li,ri=index(a.fresh),index(a.restored)
checkpoints=[(key,value) for key,value in li.items() if key[0]=='post_checkpoint']
if len(checkpoints)!=1:raise ValueError('expected one selected fresh diagnostic checkpoint snapshot')
cpkey,(cppath,cph)=checkpoints[0];cpiter=cpkey[1]
# A material mismatch is diagnostic only if explicitly declared; this matched
# pair deliberately requires the exact same new source and binary.
for field in ('source_commit','source_sha256','solver_sha256','execution_id'):
    # Scientific runtime contracts, not optional prose in supervisor metadata.
    contracts=[]
    for root in (a.fresh,a.restored):
        paths=list(root.glob('scientific_runtime_contract.*.json'))
        if len(paths)!=1:raise ValueError('ambiguous scientific runtime contract')
        contracts.append(json.loads(paths[0].read_text()))
    name='scientific_source_commit' if field=='source_commit' else field
    if contracts[0][name]!=contracts[1][name]:raise ValueError('different material/execution identity: '+name)

a.output.mkdir(parents=True)
jobs=[]
before_checkpoint=('post_projection',cpiter)
if before_checkpoint not in li:
    raise ValueError('missing fresh completed-projection state before checkpoint')
jobs.append(('fresh-post-projection-to-post-checkpoint',li[before_checkpoint][0],cppath))
for phase in ('post_restore_pre_centered','stability_post_sidecar'):
    key=(phase,cpiter)
    if key not in ri:raise ValueError('missing initial restored stage: '+str(key))
    jobs.append(('checkpoint-to-'+phase,cppath,ri[key][0]))
for phase in ('stability_post_sidecar','before_advection_term','before_projection','post_projection'):
    key=(phase,cpiter+1)
    if key not in li or key not in ri:raise ValueError('missing matched next-iteration stage: '+str(key))
    jobs.append(('matched-next-'+phase,li[key][0],ri[key][0]))
comparisons=[]
for label,left,right in jobs:
    output=a.output/(label+'.json')
    try:
        result=fields.compare(left,right,availability_diagnostic=True);atomic_new(output,result)
        changed={k:{n:v[n] for n in ('count','changed_count','max_absolute','max_point_normalized','weighted_relative_l2','support_min','support_max','finite_pair_count','nonfinite_left_count','nonfinite_right_count','nonfinite_bitwise_disagreement_count','norm_scope')} for k,v in result['summaries'].items() if v['changed_count'] or not v['complete_numeric_coverage']}
        comparisons.append({'label':label,'structural_join':'exact','comparison':fields.identity(output),'changed_fields':changed,
                            'complete_numeric_coverage':result['complete_numeric_coverage'],'availability_diagnostic':True})
    except ValueError as exc:
        # Preserve a structural failure, never turn it into a numerical pass.
        result={'label':label,'structural_join':'failed','error':str(exc),'left':fields.identity(left),'right':fields.identity(right)}
        atomic_new(output,result);comparisons.append(result)
    print(json.dumps({'label':label,'structural_join':comparisons[-1]['structural_join'],'changed_fields':list(comparisons[-1].get('changed_fields',{}))}),flush=True)
scalar_path=fields.regular(a.reuse_metric_comparison)
prior=json.loads(scalar_path.read_text())
allowed={str(root/name) for root in (a.fresh,a.restored) for name in ('hydraulic_plane_metrics.csv','raw_frame_summary.csv','solver_health_metrics.csv')}
if {v['path'] for v in prior['inputs']}!=allowed:raise ValueError('different cached comparison inputs')
for v in prior['inputs']:
    actual=fields.identity(pathlib.Path(v['path']))
    if actual['sha256']!=v['sha256'] or actual['size_bytes']!=v['size']:raise ValueError('changed cached comparison input')
summary={'schema':'internal_nozzle_diagnostic_first_divergence_packet_v1',
         'fresh_terminal':lt,'restored_terminal':rt,'checkpoint_iteration':cpiter,
         'checkpoint_time':cph['t'],'material_identity':{k:contracts[0][k] for k in ('execution_id','scientific_source_commit','source_sha256','solver_sha256')},
         'comparisons':comparisons,'frozen_scalar_comparison':fields.identity(scalar_path),
         'qualification':'not_inferred','availability_diagnostic':True,'claim_boundary':'Unavailable nonfinite state remains explicit. Finite-subset norms are not full-field equivalence. First observed state/event differences require discriminating evidence and unchanged criteria for causal repair.'}
atomic_new(a.output/'summary.json',summary)
print(json.dumps({'output':str(a.output/'summary.json'),'comparisons':len(comparisons),'qualification':'not_inferred'}))
