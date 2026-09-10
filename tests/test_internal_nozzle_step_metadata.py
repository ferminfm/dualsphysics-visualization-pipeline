"""Synthetic strict metadata fixtures; never scientific evidence."""
import ctypes as ct
import unittest
from test_internal_nozzle_step_integral import NativeBookkeepingTests, CState
import verify_internal_nozzle_step_integral as verifier
import copy
from pathlib import Path
import tempfile

class MetadataTests(NativeBookkeepingTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lib.metadata_field.argtypes=[ct.c_char_p,ct.POINTER(CState),ct.POINTER(ct.c_uint),ct.POINTER(ct.c_double)]
        cls.lib.metadata_complete.argtypes=[ct.POINTER(CState),ct.c_uint,ct.c_double,ct.c_double,ct.c_int64,ct.c_double]
    def lines(self):
        return ['accepted_step_schema=internal_nozzle_accepted_step_integral_v1',
                'accepted_step_count=2','accepted_step_iteration=1',
                'accepted_step_time=0.5','accepted_step_previous_Q=-0.2',
                'accepted_step_net_volume=0.04','accepted_step_positive_volume=0.05',
                'accepted_step_nozzle_scale=0.001']
    def parse(self,lines):
        s=CState();mask=ct.c_uint();scale=ct.c_double()
        for line in lines:
            rc=self.lib.metadata_field((line+'\n').encode(),ct.byref(s),ct.byref(mask),ct.byref(scale))
            if rc != 1:return rc,s,mask.value,scale.value
        return 1,s,mask.value,scale.value
    def test_exact_metadata_state(self):
        rc,s,mask,scale=self.parse(self.lines());self.assertEqual(rc,1)
        self.assertEqual(self.lib.metadata_complete(ct.byref(s),mask,scale,.001,1,.5),1)
        self.assertEqual((s.accepted_steps,s.last_iteration,s.previous_flow),(2,1,-.2))
    def test_duplicate_unknown_malformed_and_nonfinite(self):
        base=self.lines()
        for bad in [base+[base[1]],base+['accepted_step_unknown=3'],
                    [x.replace('0.04','nan') for x in base],
                    [x.replace('count=2','count=-1') for x in base],
                    [x.replace('iteration=1','iteration=1tail') for x in base],
                    [x.replace('time=0.5','time=') for x in base],
                    [x.replace('time=0.5','time=0.5 junk') for x in base],
                    [x.replace('integral_v1','integral_v0') for x in base]]:
            self.assertEqual(self.parse(bad)[0],-1)
    def test_missing_wrong_fence_end_scale_counts(self):
        for lines,scale_expected,iteration,end in [
                (self.lines()[:-1],.001,1,.5),(self.lines(),.002,1,.5),
                (self.lines(),.001,2,.5),(self.lines(),.001,1,.500001),
                ([x.replace('count=2','count=3') for x in self.lines()],.001,1,.5)]:
            rc,s,mask,scale=self.parse(lines);self.assertEqual(rc,1)
            self.assertEqual(self.lib.metadata_complete(ct.byref(s),mask,scale,scale_expected,iteration,end),0)
    def test_unrelated_metadata_not_consumed(self):
        s=CState();m=ct.c_uint();scale=ct.c_double()
        self.assertEqual(self.lib.metadata_field(b'case_id=test\n',ct.byref(s),ct.byref(m),ct.byref(scale)),0)
        self.assertEqual(m.value,0)

if __name__=='__main__': unittest.main()

class PythonCheckpointTests(unittest.TestCase):
    def fields(self):
        fields={key:'SYNTHETIC-unused-context' for key in verifier.CHECKPOINT_BASE_KEYS}
        fields.update(schema='internal_nozzle_checkpoint_metadata_v8',
          execution_id='synthetic-step-metadata',case_role='B',scientific_source_commit='a'*40,
          solver_sha256='b'*64,schedule_sha256='c'*64,iteration='1',actual_time='0.4',solver_dt='0.1',
          accepted_step_schema=verifier.SCHEMA,accepted_step_count='2',accepted_step_iteration='1',
          accepted_step_time='0.5',accepted_step_previous_Q='-0.2',accepted_step_net_volume='0.04',
          accepted_step_positive_volume='0.05',accepted_step_nozzle_scale='0.001')
        return fields
    def test_supported_v8(self):
        state=verifier.checkpoint_state_from_fields(self.fields())
        self.assertEqual(state['accepted_steps'],2)
    def test_no_prefix_fabrication_and_wrong_interval(self):
        fields=self.fields()
        for key,value in [('schema','internal_nozzle_checkpoint_metadata_v7'),
          ('accepted_step_schema','unknown'),('accepted_step_count','3'),('iteration','2'),
          ('actual_time','0.3'),('solver_dt','0'),('accepted_step_time','nan'),
          ('scientific_source_commit','bad'),('case_role','C')]:
            bad=dict(fields);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):verifier.checkpoint_state_from_fields(bad)
        for key in fields:
            bad=dict(fields);del bad[key]
            with self.subTest(missing=key),self.assertRaises(ValueError):verifier.checkpoint_state_from_fields(bad)
    def test_duplicate_and_extra_metadata_fail(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC-step-metadata-') as tmp:
            path=Path(tmp)/'metadata'
            text=''.join(k+'='+v+'\n' for k,v in self.fields().items())
            path.write_text(text)
            self.assertEqual(verifier.load_checkpoint_state(path)['time'],.5)
            for extra in ('actual_time=0.4\n','unregistered=1\n','malformed\n'):
                path.write_text(text+extra)
                with self.assertRaises(ValueError):verifier.load_checkpoint_state(path)

def test_native_hook_phase_and_output_separation():
    root=Path(__file__).parents[1]
    source=(root/'cases/basilisk/rectangular_internal_nozzle_convergence_visual.c').read_text()
    assert 'event end_timestep (i++, last)' in source
    assert source.count('internal_nozzle_capture_accepted_step(iter);')==1
    assert 'internal_nozzle_checkpoint_metadata_v8' in source
    assert 'found_actual + found_solver_dt' in source
    assert 'legacy' in (root/'cases/basilisk/internal_nozzle_step_io.h').read_text().lower()
