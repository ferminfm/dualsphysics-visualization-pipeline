#!/usr/bin/env python3
"""Post-qcc access-site inventory and lossless lvalue instrumentation.

The input is generated C, AFTER qcc stencil inference and macro expansion.
No Basilisk input, field declaration, boundary call or loop is rewritten.
No solver is launched. Every accepted access has a source/line/site identity;
unsupported syntax fails closed rather than silently losing coverage.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

TOKEN=re.compile(r'(?P<directive>^[ \t]*\#(?:\\\n|[^\n])*)|(?P<space>\s+)|(?P<comment>/\*.*?\*/|//[^\n]*)|(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|(?P<name>[A-Za-z_]\w*)|(?P<op>\+\+|--|<<=|>>=|[+*/%&|^!-]=|==|<=|>=|&&|\|\||->|.)',re.M|re.S)
ACCESS={'val':0,'fine':1,'coarse':2}
CONTROL={'is_leaf','is_active','is_coarse','is_border','is_local','is_vertex','allocated','allocated_child','is_refined_check','is_prolongation','is_local_prolongation','is_boundary_point','is_newpid','is_root'}
ASSIGN={'=':2,'+=':3,'-=':3,'*=':3,'/=':3,'%=':3,'&=':3,'|=':3,'^=':3,'<<=':3,'>>=':3,'++':3,'--':3}
OBSERVER_PREFIXES=('internal_nozzle_state_audit','internal_nozzle_stencil_trace','write_trace_','write_forensic_probe','internal_nozzle_projection_trace','internal_nozzle_poisson_trace','internal_nozzle_mg_trace','internal_nozzle_prediction_trace')

def tokens(text):
    out=[];end=0
    for m in TOKEN.finditer(text):
        if m.start()!=end:raise ValueError('unparsed C bytes')
        end=m.end()
        if m.lastgroup not in ('space','comment','directive'):out.append((m.group(),m.start(),m.end(),m.lastgroup))
    if end!=len(text):raise ValueError('unparsed terminal C bytes')
    return out

def calls(text):
    ts=tokens(text);sites=[]
    functions=[];braces=[];parens=[];pairs={}
    for n,tok in enumerate(ts):
        w=tok[0]
        if w=='(':parens.append(n)
        elif w==')':
            if not parens:raise ValueError('unmatched C parenthesis')
            pairs[n]=parens.pop()
        elif w=='{':
            name=None
            if not braces and n and ts[n-1][0]==')':
                op=pairs.get(n-1)
                if op and ts[op-1][3]=='name':name=ts[op-1][0]
            braces.append((n,name))
        elif w=='}':
            if not braces:raise ValueError('unmatched C brace')
            begin,name=braces.pop()
            if name:functions.append((ts[begin][1],tok[2],name))
    if braces or parens:raise ValueError('unclosed C structure')
    functions.sort()
    # Exact generated #line information, never a guess from a mutable source.
    lines=[];source='generated';line=1
    for raw in text.splitlines(keepends=True):
        m=re.match(r'\s*#(?:line\s+)?\s*(\d+)(?:\s+"([^"]+)")?',raw)
        lines.append((source,line))
        if m:line=int(m[1]);source=m[2] or source
        else:line+=1
    line_offsets=[0]
    for m in re.finditer('\n',text):line_offsets.append(m.end())
    import bisect
    for n,(word,start,end,kind) in enumerate(ts):
        if word not in ACCESS or n+1>=len(ts) or ts[n+1][0]!='(':continue
        depth=0;args=[];a=n+2;j=a
        while j<len(ts):
            w=ts[j][0]
            if w=='(' or w=='[' or w=='{':depth+=1
            elif w==')' and depth==0:
                args.append(text[ts[a][1]:ts[j-1][2]]);break
            elif w in (')',']','}'):depth-=1
            elif w==',' and depth==0:
                args.append(text[ts[a][1]:ts[j-1][2]]);a=j+1
            j+=1
        if j>=len(ts) or len(args)!=4:raise ValueError(f'unsupported {word} access at {start}')
        if any(re.search(r'\+\+|--|(?<![=<>!])=(?!=)',x) for x in args):raise ValueError('side-effecting access identity')
        if any(re.search(r'\b[A-Za-z_]\w*\s*\(',x) for x in args):raise ValueError('function call in access identity')
        if any(re.search(r'\b(?:val|fine|coarse)\s*\(',x) for x in args):raise ValueError('nested field identity')
        following=ts[j+1][0] if j+1<len(ts) else ''
        previous=ts[n-1][0] if n else ''
        role=ASSIGN.get(following,1)
        if previous in ('++','--'):role=3
        if previous=='&':role=4  # address escape; not proof of a value read
        if previous in ('sizeof','_Alignof'):role=5
        # Parenthesized lvalue/address uses require explicit classification.
        if following==')':
            k=j+1
            while k<len(ts) and ts[k][0]==')':k+=1
            if k<len(ts) and ts[k][0] in ASSIGN:raise ValueError('parenthesized lvalue needs explicit support')
        si=len(sites)+1;row=bisect.bisect_right(line_offsets,start)-1
        filename,lineno=lines[min(row,len(lines)-1)]
        fn=next((f for lo,hi,f in functions if lo<=start<hi),None)
        if not fn:raise ValueError('field access outside recognized C function')
        observed_only=fn.startswith(OBSERVER_PREFIXES)
        sites.append(dict(site=si,kind=word,role=role,args=args,start=start,end=ts[j][2],source=filename,line=lineno,function=fn,observation_only=observed_only,expression=text[start:ts[j][2]]))
    starts={item[1]:n for n,item in enumerate(ts)}
    for n,(word,start,end,kind) in enumerate(ts):
        if word not in CONTROL or n+1>=len(ts) or ts[n+1][0]!='(':continue
        depth=1;j=n+2
        while j<len(ts) and depth:
            if ts[j][0]=='(':depth+=1
            elif ts[j][0]==')':depth-=1
            j+=1
        if depth:raise ValueError('unclosed topology predicate')
        finish=ts[j-1][2]
        fn=next((f for lo,hi,f in functions if lo<=start<hi),None)
        if not fn:continue # declaration, not an evaluation
        expr=text[start:finish]
        if re.search(r'\+\+|--|(?<![=<>!])=(?!=)',expr):raise ValueError('side-effecting topology identity')
        row=bisect.bisect_right(line_offsets,start)-1;filename,lineno=lines[row]
        sites.append(dict(kind='topology_predicate',role=1,args=[],start=start,end=finish,source=filename,line=lineno,function=fn,observation_only=fn.startswith(OBSERVER_PREFIXES),expression=expr))
    for m in re.finditer(r'_attribute\[([^\[\]\n]+)\]\.stencil\.(bc|io|width)\b',text):
        if m.start() not in starts:continue # directive, literal or comment
        n=starts[m.start()];j=n
        while ts[j][2]<m.end():j+=1
        if ts[j][2]!=m.end():raise ValueError('metadata token boundary')
        following=ts[j+1][0] if j+1<len(ts) else ''
        previous=ts[n-1][0] if n else ''
        role=ASSIGN.get(following,1)
        if previous in ('++','--'):role=3
        if previous=='&':role=4
        field=m[1]
        if re.search(r'\+\+|--|(?<![=<>!])=(?!=)',field):raise ValueError('side-effecting metadata identity')
        fn=next((f for lo,hi,f in functions if lo<=m.start()<hi),None)
        if not fn:raise ValueError('metadata outside recognized function')
        row=bisect.bisect_right(line_offsets,m.start())-1;filename,lineno=lines[row]
        sites.append(dict(kind='stencil_metadata',role=role,args=[field,m[2]],start=m.start(),end=m.end(),source=filename,line=lineno,function=fn,observation_only=fn.startswith(OBSERVER_PREFIXES),expression=m[0]))
    for m in re.finditer(r'_constant\[([^\[\]\n]+)\]',text):
        if m.start() not in starts:continue
        n=starts[m.start()];j=n
        while ts[j][2]<m.end():j+=1
        if ts[j][2]!=m.end():raise ValueError('constant token boundary')
        fn=next((f for lo,hi,f in functions if lo<=m.start()<hi),None)
        if not fn:continue # array declaration, not an operator access
        role=ASSIGN.get(ts[j+1][0] if j+1<len(ts) else '',1)
        if n and ts[n-1][0]=='&':role=4
        if re.search(r'\+\+|--|(?<![=<>!])=(?!=)',m[1]):raise ValueError('side-effecting constant identity')
        row=bisect.bisect_right(line_offsets,m.start())-1;filename,lineno=lines[row]
        sites.append(dict(kind='constant',role=role,args=[m[1]],start=m.start(),end=m.end(),source=filename,line=lineno,function=fn,observation_only=fn.startswith(OBSERVER_PREFIXES),expression=m[0]))
    sites.sort(key=lambda s:s['start'])
    for n,s in enumerate(sites):s['site']=n+1
    for prev,nxt in zip(sites,sites[1:]):
        if prev['end']>nxt['start']:raise ValueError('overlapping operand sites')
    return sites

def transform(text):
    sites=calls(text);result=text;replacements=[];inserted=[]
    for s in reversed(sites):
        if s['observation_only']:continue
        if s['kind']=='topology_predicate':
            replacement=f'aux_topology_predicate(({s["expression"]}),{s["site"]},point.level,point.i,point.j,point.k)'
        elif s['kind']=='constant':
            replacement=f'(*aux_constant_access(&({s["expression"]}),{s["site"]},{s["role"]},({s["args"][0]})))'
        elif s['kind']=='stencil_metadata':
            field,member=s['args'];code={'bc':0,'io':1,'width':2}[member]
            replacement=f'(*aux_metadata_access(&({s["expression"]}),{s["site"]},{s["role"]},({field}),{code}))'
        else:
            a,x,y,z=s['args'];kind=ACCESS[s['kind']]
            replacement=f'(*aux_operand_access(&({s["expression"]}),{s["site"]},{s["role"]},{kind},point.level,point.i,point.j,point.k,({a}).i,({x}),({y}),({z})))'
        result=result[:s['start']]+replacement+result[s['end']:]
        replacements.append((replacement,s['expression']))
    prefix='/* Observation-only post-qcc overlay. */\nstatic double *aux_operand_access(double *,int,int,int,int,int,int,int,int,int,int,int);\nstatic int *aux_metadata_access(int *,int,int,int,int);\nstatic double *aux_constant_access(double *,int,int,int);\nstatic int aux_topology_predicate(int,int,int,int,int,int);\nstatic void aux_operand_begin(int,double,int);\nstatic void aux_operand_end(void);\nstatic void aux_operand_event(int,int,int,double);\n'
    # These are exact generated anchors, checked uniquely, not a reimplementation
    # of any operator. Existing tracing callbacks remain observation-only.
    anchors=[
      (r'(mgstats project\s*\([^;{}]*?\)\s*\{)',r'\1aux_operand_begin(p.i,dt,nrelax);'),
      (r'\breturn mgp;',r'aux_operand_end();return mgp;'),
      (r'(void mg_cycle\s*\([^;{}]*?\)\s*\{)',r'\1aux_operand_event(-1,trace_cycle,nrelax,0.);'),
      (r'(static void relax\s*\([^;{}]*?\)\s*\{)',r'\1aux_operand_event(-2,l,0,0.);'),
      (r'(static double residual\s*\([^;{}]*?\)\s*\{)',r'\1aux_operand_event(-3,0,0,0.);'),
    ]
    if 'mgstats project' in text:
        for pattern,repl in anchors:
            marker=repl.removeprefix(r'\1') if repl.startswith(r'\1') else 'aux_operand_end();'
            inserted.append(marker)
            result,n=re.subn(pattern,repl,result,count=0,flags=re.S)
            if n!=1:raise ValueError('ambiguous generated operator hook '+pattern)
    # Erasing exact wrappers must reconstruct the generated C byte-for-byte.
    recovered=result
    for marker in inserted:
        if recovered.count(marker)!=1:raise ValueError('operator marker erasure ambiguity')
        recovered=recovered.replace(marker,'',1)
    for replacement,original in replacements:
        if recovered.count(replacement)!=1:raise ValueError('operand wrapper erasure ambiguity')
        recovered=recovered.replace(replacement,original,1)
    if recovered!=text:raise ValueError('observation erasure changed generated operator bytes')
    return prefix+result,sites

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--output',type=Path);p.add_argument('--inventory',required=True,type=Path);a=p.parse_args()
    raw=a.source.read_bytes();text=raw.decode();out,sites=transform(text)
    payload={'schema':'post_qcc_operand_sites_v1','source_sha256':hashlib.sha256(raw).hexdigest(),'source_bytes':len(raw),'count':len(sites),'roles':{'1':'read','2':'write_only','3':'read_modify_write','4':'address_escape_not_qualified','5':'unevaluated'},'sites':sites,'solver_started':False,'coverage_qualified':False}
    for path in (a.inventory,a.output):
        if path and path.exists():raise ValueError('refuse overwrite existing output '+str(path))
    a.inventory.write_text(json.dumps(payload,indent=2)+'\n')
    if a.output:a.output.write_text(out)
    print(json.dumps({k:v for k,v in payload.items() if k!='sites'}))
if __name__=='__main__':main()
