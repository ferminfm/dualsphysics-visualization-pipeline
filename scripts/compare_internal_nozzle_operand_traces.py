#!/usr/bin/env python3
"""Stream two complete consumed-operand traces; never infer a causal repair.

No reordering, interpolation or unmatched-vector subtraction is permitted.
Exact differences and scale-floor-one numerical norms are descriptive only;
the original scientific acceptance thresholds are not changed by this tool.
"""
from __future__ import annotations
import argparse,hashlib,itertools,json,math,struct
from pathlib import Path
from read_internal_nozzle_operand_trace import records,metadata,load,target_identity

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def compare(left,right,manifest):
 sites={s['site']:s for s in manifest['sites']}
 lh,lf,le=metadata(left/'aux-operand-metadata.jsonl')
 rh,rf,re=metadata(right/'aux-operand-metadata.jsonl')
 for key in ('iteration','time','dt','nrelax','record_bytes','endianness'):
  if key not in lh or key not in rh or lh[key]!=rh[key]:
   raise ValueError('different operator interval '+key)
 first_identity=first_value=None;counts={'matched_records':0,'matched_reads':0,'differing_reads':0,'unmatched_records':0}
 groups={};examples=[]
 streams=[records(p/'aux-operand-values.bin.gz',p/'aux-operand-metadata.jsonl',manifest) for p in (left,right)]
 for a,b in itertools.zip_longest(*streams):
  if a is None or b is None or a[0][:-1]!=b[0][:-1] or a[1]!=b[1]:
   counts['unmatched_records']+=1
   if first_identity is None:first_identity={'left':a,'right':b}
   continue
  ar,field=a;br,_=b;counts['matched_records']+=1
  seq,site,role,kind,level,i,j,k,slot,di,dj,dk,bc,x=ar;y=br[-1]
  if role not in (1,3):continue
  counts['matched_reads']+=1
  s=sites[site];key=(s.get('function','unspecified'),level,field,kind)
  if key not in groups:
   if len(groups)>=100000:raise ValueError('bounded norm-group limit exceeded')
   groups[key]={'count':0,'exact_differences':0,'max_absolute':0.,'max_floor_one_relative':0.,'scaled_sum_squares':0.}
  g=groups[key];g['count']+=1
  delta=abs(x-y);normalized=delta/max(abs(x),abs(y),1.)
  if not math.isfinite(delta):raise ValueError('nonfinite difference')
  g['max_absolute']=max(g['max_absolute'],delta)
  g['max_floor_one_relative']=max(g['max_floor_one_relative'],normalized)
  g['scaled_sum_squares']+=normalized*normalized
  if struct.pack('<d',x)!=struct.pack('<d',y):
   counts['differing_reads']+=1;g['exact_differences']+=1
   item={'sequence':seq,'site':site,'function':s.get('function'),'source':s.get('source'),'line':s.get('line'),'expression':s.get('expression'),'field':field,'origin':[level,i,j,k],'target':target_identity(ar),'kind':kind,'role':role,'boundary_validity':bc,'left':x,'right':y,'absolute_difference':delta,'floor_one_relative_difference':normalized}
   if first_value is None:first_value=item
   if len(examples)<32:examples.append(item)
 # Both generators must reach their terminal verification, including negatives.
 norms=[]
 for key,g in sorted(groups.items(),key=lambda kv:repr(kv[0])):
  ss=g.pop('scaled_sum_squares');norms.append({'function':key[0],'level':key[1],'field':key[2],'kind':key[3],**g,'rms_floor_one_relative':math.sqrt(ss/g['count'])})
 return {'schema':'aux_consumed_operand_comparison_v1','complete_traces_verified':True,'same_operator_interval':True,'counts':counts,'first_identity_difference':first_identity,'first_value_difference':first_value,'field_metadata_exact':lf==rf,'first_value_examples':examples,'per_level_function_field_norms':norms,'vector_alignment_complete':first_identity is None,'causal_repair_demonstrated':False,'scientific_qualification':'not_established_by_this_comparison'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--left',type=Path,required=True);p.add_argument('--right',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 manifest=load(a.manifest.read_text());result=compare(a.left,a.right,manifest)
 paths=[('site_manifest',a.manifest)]+[(role+':'+name,root/name) for role,root in [('left',a.left),('right',a.right)] for name in ('aux-operand-values.bin.gz','aux-operand-metadata.jsonl')]
 result['inputs']=[{'role':role,'path':str(path),'size':path.stat().st_size,'sha256':digest(path)} for role,path in paths]
 with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'complete_traces_verified':True,**result['counts'],'vector_alignment_complete':result['vector_alignment_complete']}))
if __name__=='__main__':main()
