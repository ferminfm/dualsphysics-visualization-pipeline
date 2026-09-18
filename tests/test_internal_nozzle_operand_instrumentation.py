"""Synthetic C fixtures only. Never launches CFD or claims qualification."""
import importlib.util, pathlib, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('probe',ROOT/'scripts/instrument_internal_nozzle_operator.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

FIXTURE=r'''
#include <stdio.h>
typedef struct {int i;} scalar;
typedef struct {int level,i,j,k;} Point;
static double data[3][8];
#define val(s,x,y,z) data[(s).i][(x)+3]
#define fine(s,x,y,z) data[(s).i][(x)+2]
#define coarse(s,x,y,z) data[(s).i][(x)+1]
int main(void) {
 Point point={3,4,5,6};scalar a={0},b={1};
 for(int q=0;q<8;q++){data[0][q]=q*0.17;data[1][q]=q*-0.031;}
 val(a,0,0,0)=0.37;
 val(a,1,0,0)+=val(a,-1,0,0)*val(b,0,0,0);
 for(int l=0;l<4;l++) {
   double n=val(a,0,0,0)+val(a,1,0,0)*0.33;
   val(b,0,0,0)=n/(1.7+l);
   val(a,0,0,0)+=coarse(b,0,0,0)+fine(a,0,0,0);
 }
 double v=val(a,0,0,0)>0 ? val(a,-1,0,0) : val(b,-1,0,0);
 printf("%a\n",v);
 for(int s=0;s<2;s++)for(int q=0;q<8;q++)printf("%a\n",data[s][q]);
 return 0;
}
'''
STUB=r'''
static double *aux_operand_access(double *p,int site,int role,int kind,int level,int i,int j,int k,int field,int di,int dj,int dk) {
 (void)site;(void)kind;(void)level;(void)i;(void)j;(void)k;(void)field;(void)di;(void)dj;(void)dk;
 if(role==1||role==3){volatile double observation=*p;(void)observation;}
 return p;
}
'''

class Tests(unittest.TestCase):
 def test_neutral_compiled_synthetic_operator(self):
  rewritten,sites=probe.transform(FIXTURE)
  self.assertEqual({1,2,3},set(s['role'] for s in sites))
  self.assertEqual({'val','fine','coarse'},set(s['kind'] for s in sites))
  with tempfile.TemporaryDirectory(prefix='aux-synthetic-') as tmp:
   p=pathlib.Path(tmp);out=[]
   for name,text in [('base',FIXTURE),('probe',rewritten+STUB)]:
    src=p/(name+'.c');src.write_text(text)
    subprocess.run(['gcc','-O2','-std=c99',str(src),'-o',str(p/name)],check=True,capture_output=True)
    out.append(subprocess.check_output([str(p/name)]))
   self.assertEqual(out[0],out[1])
 def test_directives_and_comments_are_not_executable(self):
  t='#define M(x) \\\n val(x,0,0,0)\n/* val(x,0,0,0) */\nint f(){return 1;}\n'
  self.assertEqual(probe.calls(t),[])
 def test_source_line_binding(self):
  s=probe.calls('#line 9 "fixture.h"\ndouble f(){return val(s,0,0,0);}')
  self.assertEqual((s[0]['source'],s[0]['line'],s[0]['function']),('fixture.h',9,'f'))
 def test_missing_argument_fails(self):
  with self.assertRaises(ValueError):probe.calls('double f(){return val(a,0);}')
 def test_side_effect_identity_fails(self):
  with self.assertRaises(ValueError):probe.calls('double f(){return val(a,i++,0,0);}')
 def test_nested_field_identity_fails(self):
  with self.assertRaises(ValueError):probe.calls('double f(){return val(a,val(b,0,0,0),0,0);}')
 def test_function_side_effect_identity_fails(self):
  with self.assertRaises(ValueError):probe.calls('double f(){return val(a,next(),0,0);}')
 def test_parenthesized_write_fails(self):
  with self.assertRaises(ValueError):probe.calls('void f(){(val(a,0,0,0))=1.;}')
 def test_address_escape_not_mislabeled_read(self):
  self.assertEqual(probe.calls('void f(){double*p=&val(a,0,0,0); }')[0]['role'],4)
 def test_observer_reads_not_solver_reads(self):
  out,s=probe.transform('double write_trace_scalar_rows(){return val(a,0,0,0);}')
  self.assertTrue(s[0]['observation_only']);self.assertIn('return val(a,0,0,0);',out)
 def test_malformed_structure_fails(self):
  with self.assertRaises(ValueError):probe.calls('double f(){return val(a,0,0,0);')
 def test_site_order_and_unique_identity(self):
  s=probe.calls('double f(){return val(a,0,0,0)+val(a,0,0,0);}')
  self.assertEqual([x['site'] for x in s],[1,2]);self.assertNotEqual(s[0]['start'],s[1]['start'])
 def test_boundary_validity_reads_and_writes(self):
  s=probe.calls('void f(){_attribute[s.i].stencil.bc=0;if(_attribute[s.i].stencil.bc)g();_attribute[s.i].stencil.io |= 1;}')
  self.assertEqual([x['role'] for x in s],[2,1,3])
  self.assertTrue(all(x['kind']=='stencil_metadata' for x in s))
 def test_topology_predicate_is_single_evaluation(self):
  out,s=probe.transform('int f(){return is_leaf(neighbor(-1,0,0)) && allocated(0,0,0);}')
  self.assertEqual(len(s),2);self.assertTrue(all(x['kind']=='topology_predicate' for x in s))
  self.assertEqual(out.count('is_leaf(neighbor(-1,0,0))'),1)
 def test_duplicate_operator_hook_rejected(self):
  with self.assertRaisesRegex(ValueError,'ambiguous generated operator hook'):
   probe.transform('mgstats project(int p){return mgp;} mgstats project(int p){return mgp;}')
 def test_missing_operator_hook_rejected(self):
  with self.assertRaisesRegex(ValueError,'ambiguous generated operator hook'):
   probe.transform('mgstats project(int p){return mgp;}')

if __name__=='__main__':unittest.main()
