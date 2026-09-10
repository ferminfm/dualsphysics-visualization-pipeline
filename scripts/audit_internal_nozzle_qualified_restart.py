"""Offline, fail-closed full-metric audit of a same-source diagnostic pair.

No solver start and no production certificate creation. Both complete runs and
their native terminal records must exist. A selected checkpoint is checked as
an exact three-member identity, not inferred from a matching time label.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys


def need(condition, message):
    if not condition:
        raise ValueError(message)


def rows(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        need(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)),
             'missing/duplicate CSV columns: ' + str(path))
        return list(reader)


def exact_integer(value):
    x = int(value)
    need(str(x) == str(value), 'non-integer counter')
    return x


def solver_options(argv):
    need(isinstance(argv,list) and len(argv)>1 and len(argv[1:])%2==0,
         'malformed exact solver argv')
    out={}
    for key,value in zip(argv[1::2],argv[2::2]):
        need(isinstance(key,str) and key.startswith('--') and key not in out,
             'duplicate/malformed solver option')
        out[key]=value
    return argv[0],out


def same_physical_argv(left,right,instrumentation_control=False):
    lb,lo=solver_options(left);rb,ro=solver_options(right)
    need(lb==rb,'different solver executable')
    metadata={'--output-dir','--end-time','--segment-id','--restore',
        '--restore-sha256','--restore-metadata-sha256','--restore-closure-sha256',
        '--predecessor-segment-id','--forensic-start-time','--forensic-end-time',
        '--forensic-snapshot-end-time'}
    if instrumentation_control:
        need({lo.get('--forensic-probes'),ro.get('--forensic-probes')}=={'0','2'},
             'instrumentation control does not contrast modes 0 and 2')
        metadata.add('--forensic-probes')
    need({k:v for k,v in lo.items() if k not in metadata}==
         {k:v for k,v in ro.items() if k not in metadata},
         'different physical or output configuration in solver argv')


def indexed(data, kind, tick_dt):
    out = {}
    for row in data:
        time = float(row['t'])
        need(math.isfinite(time), 'nonfinite time')
        tick = int(row['master_tick']) if 'master_tick' in row else round(time/tick_dt)
        need(abs(time - tick*tick_dt) <= 1e-12, 'off-schedule metric row')
        key = (tick, row['plane_label'] if kind == 'hydraulic' else 'singleton')
        need(key not in out, 'duplicate metric output: ' + repr(key))
        out[key] = row
    return out


def audit_run(root, gate, inputs, expected_restore=None):
    prepared_path = root/'prepared-qualified-launch.json'
    prepared = gate.load(prepared_path)
    contract = prepared['contract']
    segment = contract['segment_id']
    terminal_path = root/'supervision'/segment/'terminal.json'
    terminal = gate.verify_terminal(gate.file_record(terminal_path))
    need(terminal['cwd'] == str(root), 'terminal cwd mismatch')
    need(terminal['argv'] == contract['solver_argv'], 'terminal argv mismatch')
    runtime_path = root/('scientific_runtime_contract.'+segment+'.json')
    init_path = root/('initialization_contract.'+segment+'.json')
    runtime, init = gate.load(runtime_path), gate.load(init_path)
    schedule_path = root/'run_schedule_contract.json'
    need(gate.digest(schedule_path) == runtime['schedule_sha256'], 'schedule changed')
    identity = {
        'execution_id': contract['execution_id'], 'segment_id': segment,
        'case_role': contract['case_role'],
        'scientific_source_commit': contract['scientific_source_commit'],
        'solver_sha256': contract['solver']['sha256'],
        'schedule_sha256': gate.digest(schedule_path),
        'source_sha256': contract['source_bundle_manifest']['sha256'],
    }
    for key, value in identity.items():
        need(runtime[key] == init[key] == value, 'runtime/init/launch identity mismatch: '+key)
    observed_restore = runtime['segment_start'] == 'native_restore'
    need(observed_restore == (expected_restore is not None), 'wrong initialization kind')
    if expected_restore:
        for key, member in [('restore_checkpoint_sha256','checkpoint'),
                            ('restore_metadata_sha256','metadata'),
                            ('restore_closure_sha256','prediction_closure')]:
            record = contract['restore'][member]
            need(gate.digest(record['path']) == record['sha256'], 'changed restore member')
            need(runtime[key] == init[key] == record['sha256'], 'actual restore mismatch: '+key)
            need(Path(record['path']) == expected_restore[member], 'wrong selected generation')
            inputs.append(gate.file_record(record['path']))
        need(runtime['predecessor_segment_id'] == expected_restore['segment_id'], 'wrong predecessor')
        need(init['native_restore_unchanged'] is True, 'native restore not preserved')
    checkpoint_index = root/'checkpoint_index.csv'
    checkpoint_manifest = root/'checkpoint_manifest.json'
    cp_rows = rows(checkpoint_index)
    cp_manifest = gate.load(checkpoint_manifest)
    need(cp_manifest['checkpoint_count'] == len(cp_rows), 'checkpoint inventory incomplete')
    need(cp_manifest['execution_id'] == contract['execution_id'] and
         cp_manifest['final_segment_id'] == segment, 'checkpoint manifest identity')
    seen_ticks = set()
    for cp in cp_rows:
        tick = int(cp['master_tick'])
        need(tick not in seen_ticks, 'duplicate checkpoint tick')
        seen_ticks.add(tick)
        for key, value in identity.items():
            need(cp[key] == value, 'checkpoint identity: '+key)
        for key in ('filename', 'metadata_file', 'prediction_closure_state_v4_file'):
            member = gate.regular(cp[key])
            need(member.is_relative_to(root/'checkpoints'), 'checkpoint escapes run root')
            inputs.append(gate.file_record(member))
    for path in (prepared_path, runtime_path, init_path, schedule_path,
                 checkpoint_index, checkpoint_manifest):
        inputs.append(gate.file_record(path))
    # Disabled exporters legitimately have header-only inventories. Any
    # produced member must have a unique filename and a regular in-scope file.
    for name in ('field_frame_manifest.csv','visual_frame_manifest.csv',
                 'surface_manifest.csv'):
        path=root/name
        inventory=rows(path);seen_files=set()
        for item in inventory:
            filename=item.get('filename')
            need(filename and filename not in seen_files,'duplicate/missing output member: '+name)
            seen_files.add(filename)
            member=Path(filename)
            if not member.is_absolute():member=root/member
            member=gate.regular(member)
            need(member.is_relative_to(root),'output member escapes its run')
        inputs.append(gate.file_record(path))
    return runtime, contract, terminal_path, cp_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('source-root','left','right','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--checkpoint-tick',type=int,required=True)
    parser.add_argument('--comparison-tick',type=int,required=True)
    parser.add_argument('--generation-root',type=Path,
                        help='Explicit fresh generation source when comparing two restored instrumentation controls')
    args = parser.parse_args()
    sys.path.insert(0,str(args.source_root/'scripts'))
    import internal_nozzle_qualification as gate
    from verify_internal_nozzle_step_integral import load_checkpoint_state
    inputs = []
    need(args.left.resolve()!=args.right.resolve(),'self-comparison is not independent evidence')
    generation_root=args.generation_root or args.left
    gruntime, gcontract, gterminal, cp_rows = audit_run(generation_root,gate,inputs)
    selected = [row for row in cp_rows if int(row['master_tick']) == args.checkpoint_tick]
    need(len(selected) == 1, 'missing/ambiguous requested checkpoint')
    cp = selected[0]
    expected = {'checkpoint':Path(cp['filename']), 'metadata':Path(cp['metadata_file']),
                'prediction_closure':Path(cp['prediction_closure_state_v4_file']),
                'segment_id':gcontract['segment_id']}
    checkpoint_state = load_checkpoint_state(expected['metadata'])
    if args.generation_root:
        lruntime,lcontract,lterminal,_=audit_run(args.left,gate,inputs,expected)
    else:
        lruntime,lcontract,lterminal=gruntime,gcontract,gterminal
    rruntime, rcontract, rterminal, _ = audit_run(args.right,gate,inputs,expected)
    same_physical_argv(lcontract['solver_argv'],rcontract['solver_argv'],bool(args.generation_root))
    allowed_differences = {'segment_id','segment_start','end_time','predecessor_segment_id',
                          'restore_checkpoint_sha256','restore_metadata_sha256','restore_closure_sha256'}
    need(set(lruntime) == set(rruntime), 'runtime schema differs')
    for key in lruntime:
        if key not in allowed_differences:
            need(lruntime[key] == rruntime[key], 'same-source/configuration mismatch: '+key)
    need(lruntime['source_sha256'] == cp['source_sha256'], 'checkpoint source mismatch')
    data = {}
    duplicate_counts = []
    for side,root,runtime in [('left',args.left,lruntime),('right',args.right,rruntime)]:
        count = 0
        data[side] = {}
        for kind,name in [('hydraulic','hydraulic_plane_metrics.csv'),('raw','raw_frame_summary.csv'),
                          ('solver','solver_health_metrics.csv')]:
            path = root/name
            source_rows = rows(path)
            indexed_rows = indexed(source_rows,kind,runtime['master_tick_dt'])
            # indexed() rejects any duplicate in the complete emitted inventory.
            need(source_rows, 'empty required output')
            data[side][kind] = indexed_rows
            inputs.append(gate.file_record(path))
        duplicate_counts.append(count)
    tick = args.comparison_tick
    need(tick > args.checkpoint_tick, 'comparison must follow checkpoint')
    selected_data = {}
    for side in data:
        selected_data[side] = {}
        for kind, mapping in data[side].items():
            selected_rows = {key[1]: row for key,row in mapping.items() if key[0] == tick}
            need(set(selected_rows) == (set(gate.PLANES) if kind=='hydraulic' else {'singleton'}),
                 'incomplete required comparison plane set')
            selected_data[side][kind] = selected_rows
        iterations = {int(row['i']) for mapping in selected_data[side].values() for row in mapping.values()}
        need(len(iterations)==1, 'metric event-iteration mismatch')
    comparisons=[]
    for metric,criterion in gate.RESTART.items():
        family,name=metric.split('/',1)
        if family in gate.PLANES:
            left=float(selected_data['left']['hydraulic'][family][name])
            right=float(selected_data['right']['hydraulic'][family][name])
        elif family=='raw':
            left=float(selected_data['left']['raw']['singleton'][name])
            right=float(selected_data['right']['raw']['singleton'][name])
        elif name in ('fallback_generation_errors','checkpoint_identity_errors'):
            # Exact selected dump/meta/closure and actual observed restore were
            # validated above. No fallback was requested or silently selected.
            left=right=0
        elif name=='duplicate_outputs':
            left,right=duplicate_counts
        else:
            kind='raw' if name in ('detached_proxy_count','one_cell_debris_count','post_tag_count') else 'solver'
            left=exact_integer(selected_data['left'][kind]['singleton'][name])
            right=exact_integer(selected_data['right'][kind]['singleton'][name])
        need(math.isfinite(left) and math.isfinite(right),'nonfinite metric: '+metric)
        err=abs(left-right)/max(1,abs(left),abs(right))
        comparisons.append({'metric':metric,'left':left,'right':right,'scale_floor':1,
                            'tolerance':gate.CRITERIA[criterion],'criterion':criterion,
                            'normalized_error':err,'pass':err<=gate.CRITERIA[criterion]})
    failures=[row for row in comparisons if not row['pass']]
    out={'schema':'internal_nozzle_same_source_restart_comparison_v1',
         'checkpoint_tick':args.checkpoint_tick,'comparison_tick':tick,
         'case_role':lruntime['case_role'],'source_commit':lruntime['scientific_source_commit'],
         'solver_sha256':lruntime['solver_sha256'],'schedule_sha256':lruntime['schedule_sha256'],
         'inputs':list({row['path']:row for row in inputs}.values()),
         'terminals':list({str(p):gate.file_record(p) for p in (gterminal,lterminal,rterminal)}.values()),
         'comparison_kind':'same_generation_instrumentation_control' if args.generation_root else 'continuous_vs_restored',
         'checkpoint_integral_state':checkpoint_state,
         'exact_generation_selection_verified':True,'registered_output_uniqueness_verified':True,
         'comparison_count':len(comparisons),'comparisons':comparisons,'failures':failures,'passed':not failures,
         'claim_boundary':'Complete registered metric equivalence; field-stage and other production gates remain separate.'}
    with args.output.open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'passed':out['passed'],'count':len(comparisons),'failures':len(failures),
                      'maximum_error':max(row['normalized_error'] for row in comparisons)}))
    return 0 if out['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
