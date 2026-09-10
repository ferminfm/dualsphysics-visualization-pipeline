"""Recompute retained precursor convergence and audit observed zero-time transfer.

No solver launch. Post-timestep projection rows are retained but never
substituted for the predeclared post_initial_projection acceptance stage.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys


def need(value,message):
    if not value:raise ValueError(message)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source-root','fresh-root','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.source_root/'scripts'))
    import internal_nozzle_qualification as gate
    import analyze_internal_nozzle_precursor_convergence as precursor
    prepared=gate.load(a.fresh_root/'prepared-qualified-launch.json');contract=prepared['contract']
    gate.validate(prepared['authority']['path'],contract)
    segment=contract['segment_id']
    terminal=a.fresh_root/'supervision'/segment/'terminal.json'
    gate.verify_terminal(gate.file_record(terminal))
    convergence=next(row for row in contract['verified_inputs'] if row['label']=='precursor_convergence_report')
    old=gate.load(convergence['path'])
    need(gate.digest(convergence['path'])==convergence['sha256'],'precursor source report changed')
    paths=[Path(row['history']['resolved_path']) for row in old['inputs']]
    contracts=[Path(row['run_contract']['resolved_path']) for row in old['inputs']]
    new=precursor.analyze(paths,contracts=contracts,
        window_t_star=old['window']['requested_delta_t_star'],
        maximum_gap_t_star=old['window']['maximum_allowed_gap_t_star'],minimum_samples=6,
        bounds=precursor.OperationalBounds(**old['declared_operational_bounds']))
    need(new==old,'retained convergence report not exactly reproduced')
    init_path=a.fresh_root/('initialization_contract.'+segment+'.json')
    runtime_path=a.fresh_root/('scientific_runtime_contract.'+segment+'.json')
    init,runtime=gate.load(init_path),gate.load(runtime_path)
    need(init['segment_start']=='fresh_initialization' and init['case_role']=='B','wrong transfer scope')
    for key in ('execution_id','segment_id','case_role','scientific_source_commit','source_sha256',
                'solver_sha256','schedule_sha256','initial_state','inlet_mode','precursor_pressure_mode'):
        need(init[key]==runtime[key],'initialization/runtime contradiction: '+key)
    need(init['initial_state']=='precursor_start' and init['inlet_mode']=='pressure_driven' and
         init['precursor_pressure_mode']=='transferred','wrong primary physical initialization')
    need(init['expected_target_cells']>0 and init['expected_target_cells']==init['loaded_target_cells'],
         'incomplete transfer target coverage')
    criteria_record=next(row for row in contract['verified_inputs'] if row['label']=='transfer_projection_criteria')
    criteria=gate.load(criteria_record['path'])
    need(gate.digest(criteria_record['path'])==criteria_record['sha256'],'changed original transfer criteria')
    need(criteria['schema']=='internal_nozzle_transfer_projection_criteria_v2' and
         criteria['phase_selection']=='named_post_initial_projection_record_only','wrong transfer criteria semantics')
    csv_path=a.fresh_root/'precursor_transfer_projection.csv'
    with csv_path.open(newline='') as stream:
        reader=csv.DictReader(stream)
        need(len(reader.fieldnames)==len(set(reader.fieldnames)),'duplicate transfer columns')
        rows=list(reader)
    selected=[row for row in rows if row['phase']=='post_initial_projection']
    need(len(selected)==1,'missing/ambiguous zero-time projection')
    row=selected[0]
    need(float(row['t'])==0 and int(row['i'])==0,'projection gate applied at wrong time')
    for key in ('execution_id','segment_id','case_role','initial_state','inlet_mode','precursor_pressure_mode'):
        need(row[key]==runtime[key],'projection row identity: '+key)
    need(row['transfer_sha256']==init['transfer_sha256']==contract['precursor_transfer']['sha256'],
         'projection input transfer hash mismatch')
    scales=criteria['normalization']
    scale_map={'divergence_l2':scales['velocity_scale']/scales['length_scale'],
               'divergence_max':scales['velocity_scale']/scales['length_scale'],
               'velocity_impulse_l2':scales['velocity_scale'],
               'cell_pressure_change_l2':scales['pressure_scale'],
               'projection_pressure_adjustment_l2':scales['pressure_scale']}
    normalized_names={'divergence_l2':'divergence_l2_normalized','divergence_max':'divergence_max_normalized',
                      'velocity_impulse_l2':'velocity_impulse_l2_normalized',
                      'cell_pressure_change_l2':'cell_pressure_change_l2_normalized',
                      'projection_pressure_adjustment_l2':'projection_pressure_adjustment_l2_normalized'}
    transfer_values={}
    for metric,scale in scale_map.items():
        value=float(row[metric]);need(math.isfinite(value) and value>=0,'invalid measured projection value')
        name=normalized_names[metric];criterion=gate.OBLIGATIONS['transfer_projection_impulse'][name]
        need(math.isclose(criteria['metrics'][metric]['limit'],gate.CRITERIA[criterion]*scale,rel_tol=1e-15),
             'original transfer limit not preserved')
        transfer_values[name]=value/scale
    transfer_values.update(mapping_identity_violations=0,initialization_identity_violations=0)
    convergence_values={}
    for name,field in [('Q_relative_drift','Q_l'),('J_k_relative_drift','J_k'),
                       ('pressure_drop_relative_drift','pressure_drop')]:
        values=new['metrics'][field]
        convergence_values[name]=max(abs(values[key]) for key in ('signed_end_to_end_relative_drift',
            'ordinary_projected_relative_trend_over_window','robust_projected_relative_trend_over_window'))
    aux=new['auxiliary']
    convergence_values.update(profile_L2_change=aux['maximum_profile_l2_change'],
        mass_flow_imbalance=aux['maximum_mass_flow_imbalance'],
        unresolved_monotonic_trends=sum(not item['tests']['no_unresolved_monotonic_trend'] for item in new['metrics'].values()),
        solver_health_violations=sum(not value for key,value in aux['tests'].items()
                                     if key not in ('consecutive_normalized_profile_l2','mass_flow_imbalance')))
    comparisons={}
    for name,values in [('precursor',convergence_values),('transfer_projection_impulse',transfer_values)]:
        need(set(values)==set(gate.OBLIGATIONS[name]),'incomplete measured gate')
        comparisons[name]=[{'metric':metric,'left':value,'right':0,'scale_floor':1,
                            'tolerance':gate.CRITERIA[gate.OBLIGATIONS[name][metric]],
                            'criterion':gate.OBLIGATIONS[name][metric]} for metric,value in values.items()]
    failures=[name+':'+row['metric'] for name,items in comparisons.items() for row in items
              if row['left']/max(1,abs(row['left']))>row['tolerance']]
    inputs=[gate.file_record(path) for path in [Path(convergence['path']),Path(criteria_record['path']),
             csv_path,init_path,runtime_path,*paths,*contracts]]
    output={'schema':'internal_nozzle_precursor_transfer_qualification_audit_v1','passed':not failures,
            'convergence_exactly_reproduced':True,'convergence':new,'selected_projection_row':row,
            'transfer_metric_normalization':scales,'comparisons':comparisons,'failures':failures,
            'inputs':inputs,'terminals':[gate.file_record(terminal)],
            'retained_post_timestep_rows_not_used_for_zero_time_gate':len(rows)-len(selected)-1,
            'claim_boundary':'Current initial transfer and retained operational precursor only; restart and production gates are separate.'}
    # Keep the actual selected row, not the comparison comprehension variable.
    output['selected_projection_row']=selected[0]
    with a.output.open('x') as stream:json.dump(output,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'passed':output['passed'],'convergence_reproduced':True,'failures':failures,
                      'transfer_normalized':transfer_values}))
    return 0 if output['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
