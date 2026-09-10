"""Cross-check all instantaneous registered moments on an exact stored state."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

import reduce_internal_nozzle_keyed_hydraulics as reducer


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source-root','run-root','snapshot','output'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.source_root/'scripts'))
    import internal_nozzle_qualification as gate
    prepared=gate.load(a.run_root/'prepared-qualified-launch.json')
    segment=prepared['contract']['segment_id']
    runtime_path=a.run_root/('scientific_runtime_contract.'+segment+'.json')
    runtime=gate.load(runtime_path)
    g={key:runtime[source] for key,source in [('width','width'),('height','height'),('Dh','hydraulic_diameter'),
        ('plenum_Dh','plenum_Dh'),('contraction_Dh','contraction_Dh'),('straight_Dh','straight_Dh'),
        ('rho_l','density_liquid'),('rho_g','density_gas')]}
    # Explicitly shared geometry source fixes the plenum scale at three and
    # pressure BCs fix ambient gauge zero; no inferred/fitted pressure offset.
    g.update(plenum_scale=3.,ambient_pressure=0.)
    result=reducer.reduce(a.snapshot,g)
    header=result['observation']
    if header['phase']!='post_projection':raise ValueError('wrong field event stage')
    metrics_path=a.run_root/'hydraulic_plane_metrics.csv'
    with metrics_path.open(newline='') as stream:
        reader=csv.DictReader(stream)
        if len(reader.fieldnames)!=len(set(reader.fieldnames)):raise ValueError('duplicate header')
        rows=[row for row in reader if int(row['i'])==header['i'] and abs(float(row['t'])-header['t'])<=1e-12]
    by_plane={row['plane_label']:row for row in rows}
    if len(rows)!=8 or set(by_plane)!=set(gate.PLANES):raise ValueError('incomplete exact-stage eight-plane output')
    comparisons=[]
    profile=('I2_liquid','I3_liquid','alpha','beta','momentum_equivalent_velocity')
    for label,observed in by_plane.items():
        if observed['execution_id']!=runtime['execution_id'] or observed['segment_id']!=segment:
            raise ValueError('metric execution/segment mismatch')
        for metric in (*gate.CORE,*profile):
            a_value=float(observed[metric]);b_value=result['planes'][label][metric]
            if not math.isfinite(a_value) or not math.isfinite(b_value):raise ValueError('nonfinite integral')
            criterion='restart_profile' if metric in profile else 'restart_core'
            error=abs(a_value-b_value)/max(1.,abs(a_value),abs(b_value))
            comparisons.append({'plane':label,'metric':metric,'solver':a_value,'independent':b_value,
                                'error':error,'criterion':criterion,'tolerance':gate.CRITERIA[criterion],
                                'pass':error<=gate.CRITERIA[criterion]})
    failures=[row for row in comparisons if not row['pass']]
    output={'schema':'internal_nozzle_exact_snapshot_quadrature_check_v1','passed':not failures,
            'input_state':result['input'],'runtime_input':gate.file_record(runtime_path),
            'metrics_input':gate.file_record(metrics_path),'observation':header,'geometry':g,
            'availability':result['availability'],'comparisons':comparisons,'failures':failures,
            'integration_mask':'actual local active non-boundary fluid leaves with cs>1e-8; exact rectangle overlap, not cs-weighted',
            'claim_boundary':'Instantaneous 144-metric reconstruction only; no cumulative or complete production qualification inference.'}
    with a.output.open('x') as stream:json.dump(output,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'passed':output['passed'],'comparisons':len(comparisons),'failures':len(failures),
                      'max_error':max(row['error'] for row in comparisons),'availability':result['availability']}))
    return 0 if output['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
