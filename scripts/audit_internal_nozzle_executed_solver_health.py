"""Read-only numerical health audit using the unchanged executed solver limits.

Pressure residuals are expressed in the native projection normalization:
mgp_resa*dt**2 and mgpf_resa*(dt/2)**2. This is not a new tolerance.
The CSV is sampled; the complete terminal stderr is scanned independently for
native convergence/restore errors. Neither check invents unrecorded residuals.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import re
import sys


def health_row(row):
    violations=[]
    def number(key):
        value=float(row[key])
        if not math.isfinite(value):raise ValueError('nonfinite health field: '+key)
        return value
    dt=number('dt');cap=number('DT');cfl=number('CFL')
    if not 0<dt<=cap*(1+1e-12) or cap!=.0004 or cfl!=.5:
        violations.append('timestep_or_CFL')
    if int(row['grid_maxdepth'])!=8 or int(row['maxlevel'])!=8 or int(row['total_grid_cells'])<=0:
        violations.append('physical_grid_identity')
    normalized={}
    for name,factor in [('mgp',dt*dt),('mgpf',(.5*dt)**2),('mgu',1.)]:
        count=int(row[name+'_i'])
        residual=number(name+'_resa')
        normalized[name]=residual*factor
        if not 0<=count<=100 or residual<0 or normalized[name]>1e-5:
            violations.append(name+'_convergence')
    return normalized,violations


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--run-root',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.source_root/'scripts'))
    import internal_nozzle_qualification as gate
    records=[];all_failures=[]
    for root in a.run_root:
        prepared=gate.load(root/'prepared-qualified-launch.json')
        contract=prepared['contract'];segment=contract['segment_id']
        terminal_path=root/'supervision'/segment/'terminal.json'
        terminal=gate.verify_terminal(gate.file_record(terminal_path))
        runtime_path=root/('scientific_runtime_contract.'+segment+'.json')
        runtime=gate.load(runtime_path)
        for key in ('execution_id','segment_id','case_role','scientific_source_commit'):
            if runtime[key]!=contract[key]:raise ValueError('runtime health scope mismatch: '+key)
        path=root/'solver_health_metrics.csv'
        with path.open(newline='') as stream:
            reader=csv.DictReader(stream)
            if len(reader.fieldnames)!=len(set(reader.fieldnames)):raise ValueError('duplicate health columns')
            rows=list(reader)
        if not rows:raise ValueError('missing health coverage')
        seen=set();failures=[];values=[]
        for row in rows:
            identity=(int(row['i']),float(row['t']))
            if identity in seen:raise ValueError('duplicate health sample')
            seen.add(identity)
            for key in ('execution_id','segment_id','case_role'):
                if row[key]!=runtime[key]:raise ValueError('contradictory health row identity')
            normalized,bad=health_row(row)
            values.append(normalized)
            failures.extend({'iteration':identity[0],'time':identity[1],'reason':reason} for reason in bad)
        stderr=Path(terminal['stderr']['path']) if isinstance(terminal.get('stderr'),dict) else terminal_path.parent/'stderr.log'
        warnings=[]
        pattern=re.compile(r'convergence for .* not reached|(?:FATAL|ERROR|ASSERTION|restore failed|segmentation fault)',re.I)
        with stderr.open(errors='replace') as stream:
            for line_number,line in enumerate(stream,1):
                if pattern.search(line):warnings.append({'line':line_number,'text':line.rstrip()[:512]})
        failures.extend({'reason':'native_stderr_error','detail':warning} for warning in warnings)
        record={'run_root':str(root),'sample_count':len(rows),
                'maximum_native_normalized_residual':{key:max(v[key] for v in values) for key in ('mgp','mgpf','mgu')},
                'native_tolerance':1e-5,'native_iteration_ceiling':100,
                'minimum_cells':min(int(row['total_grid_cells']) for row in rows),
                'maximum_cells':max(int(row['total_grid_cells']) for row in rows),
                'maximum_iterations':{key:max(int(row[key+'_i']) for row in rows) for key in ('mgp','mgpf','mgu')},
                'failures':failures,'passed':not failures,
                'terminal':gate.file_record(terminal_path),
                'inputs':[gate.file_record(p) for p in (path,runtime_path,root/'prepared-qualified-launch.json',stderr)]}
        records.append(record);all_failures.extend(failures)
    output={'schema':'internal_nozzle_executed_solver_health_audit_v1','passed':not all_failures,
            'runs':records,'health_limit_violations':len(all_failures),
            'coverage':'sampled native residuals plus complete stderr; unsampled values not fabricated',
            'claim_boundary':'Numerical health only; field identity, instrumentation and scientific acceptance remain separate.'}
    with a.output.open('x') as stream:json.dump(output,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'passed':output['passed'],'runs':len(records),'health_limit_violations':len(all_failures)}))
    return 0 if output['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
