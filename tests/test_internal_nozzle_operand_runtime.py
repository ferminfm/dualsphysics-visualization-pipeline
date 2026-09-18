"""Actual trace writer exercised on synthetic scalar operations, never CFD."""
import gzip,importlib.util,json,os,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('decoder',ROOT/'scripts/read_internal_nozzle_operand_trace.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
PREFIX=r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
typedef struct {int i;} scalar;
typedef void(*Fn)(void);
typedef struct {char*name;struct{int bc,io,width;}stencil;int face,third,block;Fn restriction,prolongation;Fn*boundary;} Attr;
static Fn bc[6];static Attr attrs[1]={{.name="pf",.block=1,.boundary=bc}};static Attr*_attribute=attrs;
static int nboundary=6,iter=363,enable_forensic_probes=0;static double t=0.13965500387229865;static char output_dir[1024];
static int projection_trace_active(scalar s){return s.i==0;}
int main(int argc,char**argv);
'''
BODY=r'''
int main(int argc,char**argv){
 if(argc!=2)return 2;snprintf(output_dir,sizeof(output_dir),"%s",argv[1]);
 const char*e=getenv("NOZZLE_OPERATOR_PROVENANCE");enable_forensic_probes=e&&!strcmp(e,"1")?2:0;
 double values[64];for(int i=0;i<64;i++)values[i]=(i+1)*0.03125;
 aux_operand_begin(0,0.0002,2);aux_operand_event(-3,0,0,0.);aux_operand_event(-1,0,2,0.);aux_operand_event(-2,3,0,0.);
 for(int q=0;q<100000;q++){
  int cell=q%64;double v=*aux_operand_access(&values[cell],1,1,0,3,cell+2,2,2,0,0,0,0);
  *aux_operand_access(&values[cell],2,2,0,3,cell+2,2,2,0,0,0,0)=v*1.0000001;
 }
 aux_operand_end();for(int i=0;i<64;i++)printf("%a\n",values[i]);return 0;
}
'''
class Tests(unittest.TestCase):
 def test_real_writer_and_decoder_with_synthetic_operands(self):
  with tempfile.TemporaryDirectory(prefix='aux-synthetic-writer-') as temp:
   root=pathlib.Path(temp);source=root/'synthetic.c';source.write_text(PREFIX+(ROOT/'cases/basilisk/internal_nozzle_operand_runtime.h').read_text()+BODY)
   subprocess.run(['gcc','-std=c99','-D_GNU_SOURCE','-O2',str(source),'-lz','-o',str(root/'synthetic')],capture_output=True,check=True)
   baseline=subprocess.check_output([str(root/'synthetic'),str(root)],env={**os.environ,'NOZZLE_OPERATOR_PROVENANCE':'0'})
   observed=subprocess.check_output([str(root/'synthetic'),str(root)],env={**os.environ,'NOZZLE_OPERATOR_PROVENANCE':'1'})
   self.assertEqual(baseline,observed)
   manifest={'sites':[{'site':i,'role':i,'kind':'val','observation_only':False} for i in (1,2)]}
   f=root/'aux-operand-values.bin.gz';meta=root/'aux-operand-metadata.jsonl'
   self.assertEqual(sum(1 for _ in d.records(f,meta,manifest)),200005)
   print(json.dumps({'synthetic_only':True,'records':200005,'raw_bytes':200005*64,'gzip_bytes':f.stat().st_size,'numerical_stdout_exact':True}))
   repeated=subprocess.run([str(root/'synthetic'),str(root)],env={**os.environ,'NOZZLE_OPERATOR_PROVENANCE':'1'},capture_output=True)
   self.assertEqual(repeated.returncode,86);self.assertIn(b'exclusive_trace_create',repeated.stderr)
if __name__=='__main__':unittest.main()
