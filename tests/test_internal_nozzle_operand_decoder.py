"""Strict decoder regression: unmistakably synthetic operator observations."""
import gzip,importlib.util,json,pathlib,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('decoder',ROOT/'scripts/read_internal_nozzle_operand_trace.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
def rec(seq,site,role=0,kind=0,value=0.):return (seq,site,role,kind,3,4,5,6,0,0,0,0,0,value)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='aux-synthetic-decoder-');self.root=pathlib.Path(self.tmp.name)
  self.rows=[rec(0,-10),rec(1,-3),rec(2,1,1,value=0.125),rec(3,-1),rec(4,-2),rec(5,-11)]
  self.meta=[{'schema':'aux_consumed_operands_v1','record_bytes':64,'endianness':'little','synthetic':True},{'event':'field_state','sequence':0,'field':0,'name':'synthetic_pf'},{'event':'terminal','complete':True,'address_escapes':0,'records':6,'reads':1,'writes':0}]
  self.manifest={'sites':[{'site':1,'role':1,'kind':'val','observation_only':False}]}
 def tearDown(self):self.tmp.cleanup()
 def read(self):
  binary=self.root/'synthetic.bin.gz';meta=self.root/'synthetic.jsonl'
  with gzip.open(binary,'wb') as f:
   for row in self.rows:f.write(d.RECORD.pack(*row))
  meta.write_text(''.join(json.dumps(x)+'\n' for x in self.meta))
  return list(d.records(binary,meta,self.manifest))
 def test_positive_complete_synthetic(self):self.assertEqual(len(self.read()),6)
 def test_duplicate_json_key(self):
  with self.assertRaisesRegex(ValueError,'duplicate'):d.load('{"a":1,"a":2}')
 def test_missing_observation(self):
  del self.rows[2]
  with self.assertRaisesRegex(ValueError,'missing or reordered'):self.read()
 def test_missing_terminal(self):
  self.meta.pop()
  with self.assertRaisesRegex(ValueError,'terminal'):self.read()
 def test_wrong_site(self):
  self.rows[2]=rec(2,2,1)
  with self.assertRaisesRegex(ValueError,'undeclared'):self.read()
 def test_observer_not_consumption(self):
  self.manifest['sites'][0]['observation_only']=True
  with self.assertRaisesRegex(ValueError,'misclassified'):self.read()
 def test_wrong_role(self):
  self.rows[2]=rec(2,1,2)
  with self.assertRaisesRegex(ValueError,'misclassified'):self.read()
 def test_missing_field_identity(self):
  self.meta.pop(1)
  with self.assertRaisesRegex(ValueError,'field semantic'):self.read()
 def test_missing_cycle_coverage(self):
  self.rows[3]=rec(3,-3)
  with self.assertRaisesRegex(ValueError,'phase coverage'):self.read()
 def test_count_mismatch(self):
  self.meta[-1]['records']=7
  with self.assertRaisesRegex(ValueError,'count mismatch'):self.read()
 def test_unobserved_pointer_escape(self):
  self.meta[-1]['address_escapes']=1
  with self.assertRaisesRegex(ValueError,'address escape'):self.read()
 def test_nonfinite_consumption(self):
  self.rows[2]=rec(2,1,1,value=float('nan'))
  with self.assertRaisesRegex(ValueError,'nonfinite'):self.read()
 def test_exact_grid_identity(self):
  row=list(rec(0,1,1));row[9:12]=[1,-1,0]
  self.assertEqual(d.target_identity(row),(3,5,4,6,0))
  row[3]=1;self.assertEqual(d.target_identity(row),(4,7,7,10,0))
  row[3]=2;self.assertEqual(d.target_identity(row),(2,4,2,4,0))
 def test_truncated_record(self):
  binary=self.root/'bad.gz';meta=self.root/'m.jsonl';meta.write_text(''.join(json.dumps(x)+'\n' for x in self.meta))
  with gzip.open(binary,'wb') as f:f.write(b'bad')
  with self.assertRaisesRegex(ValueError,'truncated'):list(d.records(binary,meta,self.manifest))
if __name__=='__main__':unittest.main()
