#!/usr/bin/env python3
"""Strict streaming decoder for actual consumed-operand evidence, not hashes.

It rejects incomplete traces and undeclared sites. A valid decode is not a
scientific qualification certificate. No data files are modified.
"""
from __future__ import annotations
import gzip,json,math,struct
from pathlib import Path

RECORD=struct.Struct('<Q12id')
KINDS={'val':0,'fine':1,'coarse':2,'stencil_metadata':3,'constant':4,'topology_predicate':5}
def unique(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('duplicate JSON key '+k)
  d[k]=v
 return d
def load(text):return json.loads(text,object_pairs_hook=unique,parse_constant=lambda s:(_ for _ in ()).throw(ValueError('nonfinite JSON '+s)))
def target_identity(row):
 seq,site,role,kind,level,i,j,k,field,di,dj,dk,bc,value=row
 if kind==0:return (level,i+di,j+dj,k+dk,field)
 if kind==1:return (level+1,2*i-2+di,2*j-2+dj,2*k-2+dk,field)
 if kind==2:return (level-1,(i+2)//2+di,(j+2)//2+dj,(k+2)//2+dk,field)
 if kind==5:return (level,i,j,k,field)
 return (-1,kind,di,0,field)
def metadata(path):
 if Path(path).stat().st_size>64*1024*1024:raise ValueError('metadata memory bound exceeded')
 with Path(path).open() as f:rows=[load(s) for s in f if s.strip()]
 if len(rows)<2 or rows[0].get('schema')!='aux_consumed_operands_v1':raise ValueError('missing trace header')
 header=rows[0];end=rows[-1]
 if header.get('record_bytes')!=64 or header.get('endianness')!='little':raise ValueError('wrong record format')
 if end.get('event')!='terminal' or end.get('complete') is not True:raise ValueError('missing terminal evidence')
 if end.get('address_escapes')!=0:raise ValueError('unqualified address escape')
 previous=-1
 for x in rows[1:-1]:
  if x.get('event')!='field_state' or not isinstance(x.get('sequence'),int) or x['sequence']<previous:raise ValueError('invalid metadata order')
  if not isinstance(x.get('name'),str) or not x['name']:raise ValueError('missing field identity')
  previous=x['sequence']
 return header,rows[1:-1],end
def records(binary,meta,manifest):
 header,fields,end=metadata(meta)
 if not isinstance(manifest,dict) or 'sites' not in manifest:raise ValueError('missing site manifest')
 sites={s['site']:s for s in manifest['sites']}
 if len(sites)!=len(manifest['sites']):raise ValueError('duplicate site identity')
 seen=set();count=reads=writes=0;events=[];pos=0;identities={}
 with gzip.open(binary,'rb') as f:
  while True:
   chunk=f.read(64*8192)
   if not chunk:break
   if len(chunk)%64:raise ValueError('truncated operand record')
   for row in RECORD.iter_unpack(chunk):
    seq,site,role,kind,level,i,j,k,field,di,dj,dk,bc,value=row
    if seq!=count:raise ValueError('missing or reordered observation')
    while pos<len(fields) and fields[pos]['sequence']<=seq:
     identities[fields[pos]['field']]=fields[pos]['name'];pos+=1
    count+=1
    if site<0:
     if site not in (-10,-11,-1,-2,-3) or role!=0:raise ValueError('unknown operator event')
     events.append(site)
    else:
     s=sites.get(site)
     if not s or s.get('observation_only') or s['role']!=role or KINDS[s['kind']]!=kind:raise ValueError('undeclared or misclassified consumed site')
     if role not in (1,2,3):raise ValueError('unsupported consumed role')
     if kind<3 and field not in identities:raise ValueError('missing field semantic identity')
     if kind<3 and (level<0 or any(abs(v)>100000 for v in (i,j,k,di,dj,dk))):raise ValueError('malformed cell identity')
     if role in (1,3):
      reads+=1
      if not math.isfinite(value):raise ValueError('nonfinite actually consumed value')
     if role in (2,3):writes+=1
     seen.add(site)
    yield row, identities.get(field) if kind<3 else {3:'metadata',4:'constant',5:'topology'}[kind]
 if not events or events[0]!=-10 or events[-1]!=-11:raise ValueError('projection interval not closed')
 if not all(e in events for e in (-1,-2,-3)):raise ValueError('missing actual multigrid phase coverage')
 if (count,reads,writes)!=(end.get('records'),end.get('reads'),end.get('writes')):raise ValueError('terminal count mismatch')
 if pos!=len(fields):raise ValueError('metadata refers beyond terminal observation')
