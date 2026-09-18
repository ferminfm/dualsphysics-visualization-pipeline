#!/usr/bin/env python3
"""Task-scoped CC99 adapter: unchanged preprocessing; observed final C only.

This is not a scientific launcher. It never executes its binary. The enclosing
observable qcc invocation and source sealer bind this adapter and its outputs.
"""
import hashlib,json,os,pathlib,subprocess,sys
from instrument_internal_nozzle_operator import transform
COMPILER=str(pathlib.Path('/usr/bin/cc').resolve(strict=True))

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def command(argv):
 if '-E' in argv:return [COMPILER,*argv],None
 if any(x.startswith(('-fopenmp','-D_MPI','-ffast-math')) for x in argv):raise ValueError('parallel or altered floating-point mode forbidden')
 if argv.count('-o')!=1:raise ValueError('one exact compile output required')
 target=pathlib.Path(argv[argv.index('-o')+1])
 if not target.is_absolute() or target.exists():raise ValueError('new absolute compiler output required')
 sources=[x for x in argv if not x.startswith('-') and x.endswith('.c')]
 if len(sources)!=1:raise ValueError('one generated C translation unit required')
 source=pathlib.Path(sources[0])
 if source.is_symlink() or not source.is_file():raise ValueError('generated input must be regular')
 root=pathlib.Path(__file__).resolve().parents[1];runtime=root/'cases/basilisk/internal_nozzle_operand_runtime.h'
 out=target.parent/'operand-overlay';out.mkdir(exist_ok=False)
 raw=source.read_bytes();text,sites=transform(raw.decode())
 generated=out/'generated.c';generated.write_bytes(raw)
 rewritten=out/'instrumented.c';rewritten.write_text(text+'\n'+runtime.read_text())
 actual=[COMPILER,*(str(rewritten) if x==sources[0] else x for x in argv),'-lz']
 record={'schema':'post_qcc_operand_overlay_v1','qcc_generated_path':str(source.resolve()),'generated_path':str(generated),'generated_sha256':digest(generated),'instrumented_path':str(rewritten),'instrumented_sha256':digest(rewritten),'transformer_sha256':digest(root/'scripts/instrument_internal_nozzle_operator.py'),'runtime_sha256':digest(runtime),'adapter_sha256':digest(pathlib.Path(__file__)),'received_argv':argv,'compiler_argv':actual,'compiler_path':COMPILER,'site_count':len(sites),'sites':sites,'scientific_process_started':False,'compiler_returncode':None}
 return actual,(out,record,target)

def main():
 argv,context=command(sys.argv[1:])
 if context is None:return subprocess.call(argv)
 out,record,target=context
 with (out/'launch.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 rc=subprocess.call(argv);record['compiler_returncode']=rc
 record['binary_sha256']=digest(target) if rc==0 and target.is_file() else None
 record['compiler_sha256']=digest(pathlib.Path(record['compiler_path']))
 with (out/'site-manifest.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 return rc
if __name__=='__main__':raise SystemExit(main())
