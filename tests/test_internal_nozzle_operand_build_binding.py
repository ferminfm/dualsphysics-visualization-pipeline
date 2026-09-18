"""Synthetic build-binding regressions; no compiler or CFD process launched."""
import copy,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import verify_internal_nozzle_operand_build as v
import compile_internal_nozzle_operand_overlay as cc

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='aux-SYNTHETIC-binding-');self.root=pathlib.Path(self.tmp.name)
  self.bundle={'schema':'internal_nozzle_source_bundle_operator_v2','tracked_behavior_files':[{'path':p,'sha256':s} for p,s in [('cases/basilisk/internal_nozzle_operand_runtime.h','a'*64),('scripts/instrument_internal_nozzle_operator.py','b'*64),('scripts/compile_internal_nozzle_operand_overlay.py','c'*64)]]}
  self.o={'schema':'post_qcc_operand_overlay_v1','runtime_sha256':'a'*64,'transformer_sha256':'b'*64,'adapter_sha256':'c'*64,'compiler_returncode':0,'binary_sha256':'d'*64,'site_count':1,'sites':[{'synthetic':True}]}
  for label in ('generated','instrumented','compiler'):
   p=self.root/label;p.write_text('SYNTHETIC '+label);self.o[label+'_path']=str(p);self.o[label+'_sha256']=v.digest(p)
  self.path=self.root/'manifest.json';self.path.write_text(json.dumps(self.o))
  self.build={'schema':'internal_nozzle_observable_qcc_build_operator_v2','binary':{'sha256':'d'*64},'operator_observation_overlay':{'path':str(self.path),'sha256':v.digest(self.path)}}
 def tearDown(self):self.tmp.cleanup()
 def test_exact_binding(self):self.assertEqual(len(v.verify_operator_overlay(self.build,self.bundle)),4)
 def test_legacy_unchanged(self):self.assertEqual(v.verify_operator_overlay({'schema':'internal_nozzle_observable_qcc_build_v1'},{'schema':'internal_nozzle_source_bundle_v1'}),[])
 def test_missing_overlay(self):
  del self.build['operator_observation_overlay']
  with self.assertRaises(ValueError):v.verify_operator_overlay(self.build,self.bundle)
 def test_wrong_source(self):
  self.bundle['tracked_behavior_files'][0]['sha256']='e'*64
  with self.assertRaisesRegex(ValueError,'source identity'):v.verify_operator_overlay(self.build,self.bundle)
 def test_changed_generated(self):
  (self.root/'generated').write_text('changed')
  with self.assertRaisesRegex(ValueError,'material changed'):v.verify_operator_overlay(self.build,self.bundle)
 def test_wrong_binary(self):
  self.build['binary']['sha256']='f'*64
  with self.assertRaisesRegex(ValueError,'binary identity'):v.verify_operator_overlay(self.build,self.bundle)
 def test_version_downgrade(self):
  self.build['schema']='internal_nozzle_observable_qcc_build_v1'
  with self.assertRaisesRegex(ValueError,'version-mismatched'):v.verify_operator_overlay(self.build,self.bundle)
 def test_preprocessor_is_unchanged(self):
  self.assertEqual(cc.command(['-E','-I.','input.c']),([cc.COMPILER,'-E','-I.','input.c'],None))
 def test_parallel_and_fast_math_rejected(self):
  for flag in ('-fopenmp','-D_MPI=1','-ffast-math'):
   with self.assertRaisesRegex(ValueError,'parallel or altered'):cc.command([flag])
if __name__=='__main__':unittest.main()
