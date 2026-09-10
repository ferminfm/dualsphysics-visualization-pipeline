"""Compare the original complete stored metric set at a single exact master tick."""
import argparse,csv,hashlib,json,math,pathlib
p=argparse.ArgumentParser()
for k in ('freeze','left','right','output'):p.add_argument('--'+k,type=pathlib.Path,required=True)
p.add_argument('--label',required=True);a=p.parse_args()
def rows(path):
    with path.open() as f:
        r=csv.DictReader(f);assert len(r.fieldnames)==len(set(r.fieldnames));return list(r)
def identity(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(65536),b''):h.update(b)
    return {'path':str(path),'size':path.stat().st_size,'sha256':h.hexdigest()}
freeze=json.loads(a.freeze.read_text());template=freeze['comparison']['stored_report']
tick=template['master_tick'];tickdt=freeze['restart_launch']['schedule']['master_tick_dt']
matrix=[];inputs=[]
for kind,name in [('hydraulic','hydraulic_plane_metrics.csv'),('raw','raw_frame_summary.csv'),('solver','solver_health_metrics.csv')]:
    sides=[]
    for root in (a.left,a.right):
        path=root/name;inputs.append(identity(path)); selected={}
        for row in rows(path):
            t=float(row['t']); it=int(row.get('master_tick',round(t/tickdt)))
            if it!=tick:continue
            assert abs(t-it*tickdt)<=1e-12
            key=(it,row.get('plane_label','singleton'));assert key not in selected
            selected[key]=row
        assert selected, (kind,root,'missing target tick')
        sides.append(selected)
    assert set(sides[0])==set(sides[1])
    for key,left in sides[0].items():
        right=sides[1][key];assert left['i']==right['i'] and abs(float(left['t'])-float(right['t']))<=1e-12
        spec=(template['hydraulic'][key[1]] if kind=='hydraulic' else
              {'raw':template['raw']} if kind=='raw' else
              {'solver_residual':{'values':template['solver_residual_normalized_deltas'],'tolerance':None}})
        for group,tests in spec.items():
            for metric in tests['values']:
                x,y=float(left[metric]),float(right[metric]);assert math.isfinite(x) and math.isfinite(y)
                error=abs(x-y)/max(1,abs(x),abs(y));tol=tests.get('tolerance')
                matrix.append({'family':kind,'group':group,'plane':key[1],'metric':metric,
                  'i':int(left['i']),'t_left':float(left['t']),'t_right':float(right['t']),
                  'left':x,'right':y,'normalized_error':error,'tolerance':tol,'pass':None if tol is None else error<=tol})
failed=[r for r in matrix if r['pass'] is False]
out={'schema':'internal_nozzle_original_metric_comparison_v1','label':a.label,
     'master_tick':tick,'source_criteria':'exact frozen predecessor metric set and normalization',
     'inputs':inputs,'comparison_count':len(matrix),'failure_count':len(failed),'pass':not failed,
     'groups':{k:{'max':max(r['normalized_error'] for r in matrix if r['family']==k),
                  'failures':sum(r['pass'] is False for r in matrix if r['family']==k)} for k in ('hydraulic','raw','solver')},
     'comparisons':matrix,'claim_boundary':'Metric reproducibility only, not a complete field or production certificate.'}
a.output.parent.mkdir(parents=True,exist_ok=True)
with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
print(json.dumps({k:out[k] for k in ('label','master_tick','comparison_count','failure_count','pass','groups')}))
