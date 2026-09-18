#!/usr/bin/env python3
"""Generate and compile a post-qcc observation draft, never run CFD."""
import argparse, hashlib, json, pathlib, subprocess
from instrument_internal_nozzle_operator import transform

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--generated',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 root=pathlib.Path(__file__).resolve().parents[1];runtime=root/'cases/basilisk/internal_nozzle_operand_runtime.h'
 a.output.mkdir(exist_ok=False,parents=True)
 text,sites=transform(a.generated.read_text())
 target=a.output/'instrumented.c';target.write_text(text+'\n'+runtime.read_text())
 manifest={'schema':'post_qcc_operator_build_draft_v1','generated_sha256':digest(a.generated),'transformer_sha256':digest(root/'scripts/instrument_internal_nozzle_operator.py'),'runtime_sha256':digest(runtime),'output_sha256':digest(target),'site_count':len(sites),'sites':sites,'solver_started':False,'M1_coverage_pass':False}
 (a.output/'site-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 argv=['gcc','-std=c99','-D_GNU_SOURCE','-O2','-Wall','-I/home/franco/opt/basilisk-survey-20260606/basilisk/src',str(target),'-o',str(a.output/'operator-inspection-draft'),'-L/home/franco/opt/basilisk-survey-20260606/basilisk/src/gl','-lglutils','-lfb_tiny','-lz','-lm']
 print(json.dumps({'argv':argv,'generated_sha256':manifest['generated_sha256'],'site_count':len(sites)}),flush=True)
 rc=subprocess.call(argv)
 print(json.dumps({'compiler_rc':rc,'solver_started':False,'binary_sha256':digest(a.output/'operator-inspection-draft') if rc==0 else None}),flush=True)
 return rc
if __name__=='__main__':raise SystemExit(main())
