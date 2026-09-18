"""Strict optional observation-overlay binding, shared by launch and sealing."""
import hashlib,json
from pathlib import Path

def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
def unique(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('duplicate overlay key')
  d[k]=v
 return d
def verify_operator_overlay(build,bundle):
 extended=build.get('schema')=='internal_nozzle_observable_qcc_build_operator_v2'
 if not extended:
  if 'operator_observation_overlay' in build or bundle.get('schema')=='internal_nozzle_source_bundle_operator_v2':raise ValueError('missing/version-mismatched operator binding')
  return []
 if bundle.get('schema')!='internal_nozzle_source_bundle_operator_v2':raise ValueError('operator source-bundle version mismatch')
 r=build.get('operator_observation_overlay')
 if not isinstance(r,dict) or set(r)!={'path','sha256'}:raise ValueError('operator manifest binding shape')
 p=Path(r['path'])
 if p.is_symlink() or not p.is_file() or digest(p)!=r['sha256']:raise ValueError('operator manifest changed or missing')
 o=json.loads(p.read_text(),object_pairs_hook=unique);files={x['path']:x['sha256'] for x in bundle['tracked_behavior_files']}
 for label,rel in [('runtime','cases/basilisk/internal_nozzle_operand_runtime.h'),('transformer','scripts/instrument_internal_nozzle_operator.py'),('adapter','scripts/compile_internal_nozzle_operand_overlay.py')]:
  if o.get(label+'_sha256')!=files.get(rel) or rel not in files:raise ValueError('operator source identity '+label)
 if o.get('schema')!='post_qcc_operand_overlay_v1' or o.get('compiler_returncode')!=0 or o.get('binary_sha256')!=build['binary']['sha256']:raise ValueError('operator compiler/binary identity')
 if not isinstance(o.get('sites'),list) or o.get('site_count')!=len(o['sites']) or not o['sites']:raise ValueError('operator site coverage missing')
 identities=[{'label':'operator_site_manifest','path':str(p),'sha256':r['sha256']}]
 for label in ('generated','instrumented','compiler'):
  path=Path(o[label+'_path'])
  if path.is_symlink() or not path.is_file() or digest(path)!=o[label+'_sha256']:raise ValueError('operator material changed '+label)
  identities.append({'label':'operator_'+label,'path':str(path),'sha256':o[label+'_sha256']})
 return identities
