"""Audit complete real accepted-step traces and checkpoint/restart prefixes.

Sparse reconstruction uses a declared subset of the SAME accepted-step
endpoint samples. Legacy output-driven cumulative columns are reported as a
separate, historically unqualified definition. No matching gate is relaxed.
"""
import argparse
import csv
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import sys


def need(ok,message):
    if not ok:raise ValueError(message)


def read_rows(path):
    with path.open(newline='') as stream:
        reader=csv.DictReader(stream)
        need(reader.fieldnames and len(reader.fieldnames)==len(set(reader.fieldnames)),'invalid CSV header')
        return list(reader)


def audit(root,verifier,gate):
    prepared=gate.load(root/'prepared-qualified-launch.json');contract=prepared['contract']
    segment=contract['segment_id'];terminal=root/'supervision'/segment/'terminal.json'
    gate.verify_terminal(gate.file_record(terminal))
    initial_path=root/'accepted_step_initial_state.json'
    final_path=root/'accepted_step_terminal_state.json'
    trace_path=root/'accepted_step_integral.csv'
    initial=verifier.initial_state(verifier.load_state(initial_path))
    final=verifier.initial_state(verifier.load_state(final_path))
    summary_path=root/'visual_pipeline_case_summary.csv'
    summary=read_rows(summary_path)
    need(len(summary)==1,'nonunique terminal native summary')
    summary=summary[0]
    health_path=root/'solver_health_metrics.csv';health=read_rows(health_path)
    need(health,'missing native terminal health')
    last=health[-1]
    # The independently emitted native terminal row labels the step beginning;
    # actual accepted state is at t+dt. Summary time has reduced print precision.
    native_iteration=int(summary['i'])
    need(native_iteration==int(last['i']),'terminal summary/health iteration mismatch')
    need(math.isclose(float(summary['t']),float(last['t']),rel_tol=1e-10,abs_tol=1e-12),
         'terminal summary/health time mismatch')
    expected_end=float(last['t'])+float(last['dt'])
    expected_count=native_iteration+1-initial['accepted_steps']
    need(final['last_iteration']==native_iteration,'terminal accepted-step counter mismatches native solver')
    rows=read_rows(trace_path)
    result=verifier.verify(iter(rows),initial,expected_count,expected_end,final)
    inputs=[gate.file_record(p) for p in (initial_path,final_path,trace_path,summary_path,health_path,
                                        root/'prepared-qualified-launch.json')]
    if contract['restore']['kind']=='checkpoint':
        metadata=Path(contract['restore']['metadata']['path'])
        need(gate.digest(metadata)==contract['restore']['metadata']['sha256'],'restore metadata changed')
        prefix=verifier.load_checkpoint_state(metadata)
        need(prefix==initial,'restart initial accepted-step prefix is not exact')
        inputs.append(gate.file_record(metadata))
    by_iteration={int(row['iteration']):row for row in rows}
    need(len(by_iteration)==len(rows),'duplicate native step')
    checkpoint_checks=[]
    index_path=root/'checkpoint_index.csv'
    for cp in read_rows(index_path):
        metadata=Path(cp['metadata_file']);state=verifier.load_checkpoint_state(metadata)
        row=by_iteration.get(state['last_iteration'])
        need(row is not None,'checkpoint has no accepted-step trace member')
        for field,col in [('time','end'),('previous_flow','Q_right'),('net_volume','net_volume'),
                          ('positive_volume','positive_volume')]:
            need(state[field]==float(row[col]),'checkpoint/trace state differs: '+field)
        checkpoint_checks.append({'master_tick':int(cp['master_tick']),
                                  'state':state,'metadata':gate.file_record(metadata),'passed':True})
    inputs.append(gate.file_record(index_path))
    output_iterations={int(row['i']) for row in health}
    # Retain terminal sample even if an output cadence omitted it: only a
    # same-trace sample already present in the accepted-step trace may be used.
    sparse=[row for row in rows if int(row['iteration']) in output_iterations]
    need(sparse and int(sparse[-1]['iteration'])==native_iteration,'sparse coverage lacks terminal sample')
    sparse_net=initial['net_volume'];sparse_positive=initial['positive_volume']
    prev_t=initial['time'];prev_q=initial['previous_flow'];sparse_history=[]
    for row in sparse:
        time=float(row['end']);flow=float(row['Q_right'])
        dt=time-prev_t;need(dt>0,'invalid sparse interval')
        sparse_net+=.5*(flow+prev_q)*dt
        sparse_positive+=.5*(max(flow,0.)+max(prev_q,0.))*dt
        sparse_history.append({'time':time,'net_volume':sparse_net,'positive_volume':sparse_positive,
                               'same_step_net_volume':float(row['net_volume']),
                               'same_step_positive_volume':float(row['positive_volume'])})
        prev_t,prev_q=time,flow
    result.update(run_root=str(root),inputs=inputs,terminal=gate.file_record(terminal),
        native_terminal_iteration=native_iteration,native_terminal_step_begin=float(last['t']),
        native_terminal_step_end=expected_end,checkpoint_prefix_checks=checkpoint_checks,
        sparse={'definition':'endpoint_trapezoid_on_native_output_iteration_subset_of_same_stage_trace',
                'classification':'approximation_not_same_step_acceptance',
                'sample_count':len(sparse),'net_volume':sparse_net,'positive_volume':sparse_positive,
                'net_difference':sparse_net-final['net_volume'],
                'positive_difference':sparse_positive-final['positive_volume'],'history':sparse_history},
        legacy_coordinate_status='retained_output_driven_definition_unqualified_not_used_as_same_step',
        step_history=[{'iteration':int(row['iteration']),'begin':float(row['begin']),'end':float(row['end']),
                       'net_volume':float(row['net_volume']),'positive_volume':float(row['positive_volume']),
                       'Q_right':float(row['Q_right'])} for row in rows])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--fresh',type=Path,required=True)
    p.add_argument('--restored',type=Path,action='append',default=[])
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.source_root/'scripts'))
    import internal_nozzle_qualification as gate
    import verify_internal_nozzle_step_integral as verifier
    records=[audit(root,verifier,gate) for root in [a.fresh,*a.restored]]
    fresh=records[0];baseline={row['iteration']:row for row in fresh['step_history']}
    restart_comparisons=[]
    for restored in records[1:]:
        for key in ('source_commit','solver_sha256','schedule_sha256','execution_id','case_role'):
            need(restored['initial_state'][key]==fresh['initial_state'][key],'cross-run material mismatch')
        final=restored['computed_final_state'];match=baseline.get(final['last_iteration'])
        need(match is not None,'restored endpoint outside continuous bracket')
        need(abs(match['end']-final['time'])<=1e-12,'restart interval endpoint mismatch')
        values=[]
        for key in ('net_volume','positive_volume'):
            left,right=match[key],final[key]
            values.append({'metric':key,'left':left,'right':right,'absolute_difference':abs(left-right),
                           'passed':math.isclose(left,right,rel_tol=verifier.RTOL,abs_tol=verifier.ATOL)})
        restart_comparisons.append({'run_root':restored['run_root'],'values':values,
                                    'passed':all(row['passed'] for row in values)})
    passed=all(row['passed'] for row in records) and all(row['passed'] for row in restart_comparisons)
    output={'schema':'internal_nozzle_cumulative_same_step_campaign_audit_v1','passed':passed,
            'relative_tolerance':verifier.RTOL,'absolute_tolerance':verifier.ATOL,
            'runs':records,'restart_comparisons':restart_comparisons,
            'claim_boundary':'Same-step bookkeeping and declared restart total checks only; historical sparse coordinate remains excluded.'}
    with a.output.open('x') as stream:json.dump(output,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'passed':passed,'runs':len(records),'steps':[row['checked_steps'] for row in records],
                      'restart_comparisons':restart_comparisons}))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
