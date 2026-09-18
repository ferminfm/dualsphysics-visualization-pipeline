"""Synthetic paired trace positives and intended-failure negatives; no CFD."""
import gzip,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import compare_internal_nozzle_operand_traces as c
from read_internal_nozzle_operand_trace import RECORD

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='aux-SYNTHETIC-pair-');self.root=pathlib.Path(self.tmp.name)
  self.manifest={'sites':[dict(site=1,kind='val',role=1,observation_only=False,function='synthetic_relax',source='synthetic.c',line=1,expression='val(pf,0,0,0)')]}
 def tearDown(self):self.tmp.cleanup()
 def fixture(self,name,value=.125,offset=0,missing=False):
  p=self.root/name;p.mkdir()
  rows=[(n,s,1 if s>0 else 0,0,3,4+offset,5,6,0,0,0,0,0,value if s>0 else 0.) for n,s in enumerate((-10,-3,-1,-2,1,-11))]
  if missing:rows.pop(4)
  with gzip.open(p/'aux-operand-values.bin.gz','wb') as f:
   for r in rows:f.write(RECORD.pack(*r))
  meta=[dict(schema='aux_consumed_operands_v1',iteration=363,time=.1,dt=.001,nrelax=2,record_bytes=64,endianness='little',synthetic=True),dict(event='field_state',sequence=0,field=0,name='synthetic_pf'),dict(event='terminal',complete=True,address_escapes=0,records=6,reads=1,writes=0)]
  (p/'aux-operand-metadata.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in meta))
  return p
 def test_equal_actual_values(self):
  r=c.compare(self.fixture('a'),self.fixture('b'),self.manifest)
  self.assertEqual(r['counts']['differing_reads'],0);self.assertTrue(r['vector_alignment_complete'])
 def test_first_numeric_difference_not_hash(self):
  r=c.compare(self.fixture('a'),self.fixture('b',value=.126),self.manifest)
  self.assertEqual(r['first_value_difference']['sequence'],4)
  self.assertEqual(r['first_value_difference']['left'],.125)
  self.assertEqual(r['first_value_difference']['right'],.126)
  self.assertFalse(r['causal_repair_demonstrated'])
 def test_wrong_cell_does_not_get_subtracted(self):
  r=c.compare(self.fixture('a'),self.fixture('b',offset=1),self.manifest)
  self.assertFalse(r['vector_alignment_complete']);self.assertIsNone(r['first_value_difference'])
 def test_missing_late_record_not_hidden_by_first_difference(self):
  with self.assertRaisesRegex(ValueError,'missing or reordered'):
   c.compare(self.fixture('a'),self.fixture('b',value=.126,missing=True),self.manifest)
 def test_wrong_scope_rejected(self):
  a=self.fixture('a');b=self.fixture('b');p=b/'aux-operand-metadata.jsonl';p.write_text(p.read_text().replace('"iteration": 363','"iteration": 364'))
  with self.assertRaisesRegex(ValueError,'operator interval'):c.compare(a,b,self.manifest)
 def test_corrupt_terminal_rejected(self):
  a=self.fixture('a');b=self.fixture('b');p=b/'aux-operand-metadata.jsonl';p.write_text(p.read_text().replace('"records": 6','"records": 7'))
  with self.assertRaisesRegex(ValueError,'count mismatch'):c.compare(a,b,self.manifest)
if __name__=='__main__':unittest.main()
