"""Synthetic bookkeeping fixtures only. No solver or scientific acceptance."""
import copy
import csv
import ctypes as ct
import io
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import verify_internal_nozzle_step_integral as v

def state(q=0.,scale=1.):
    return {'schema':v.SCHEMA,'accepted_steps':0,'last_iteration':-1,'time':0.,
            'previous_flow':q,'net_volume':0.,'positive_volume':0.,
            'execution_id':'synthetic-bookkeeping-only','case_role':'B',
            'source_commit':'a'*40,'solver_sha256':'b'*64,'schedule_sha256':'c'*64,
            'nozzle_scale_volume':scale}

def samples(times,flows,initial=None):
    s=state(flows[0]) if initial is None else copy.deepcopy(initial)
    rows=[]
    for a,b,l,r in zip(times,times[1:],flows,flows[1:]):
        dn=(l+r)*(b-a)/2; dp=(max(l,0.)+max(r,0.))*(b-a)/2
        s['net_volume']+=dn;s['positive_volume']+=dp
        s['accepted_steps']+=1;s['last_iteration']+=1
        row={k:s[k] for k in ('execution_id','case_role','source_commit','solver_sha256','schedule_sha256')}
        row.update(schema=v.SCHEMA,step_index=s['accepted_steps'],iteration=s['last_iteration'],
                   accepted=True,begin=a,end=b,dt=b-a,Q_left=l,Q_right=r,
                   net_increment=dn,positive_increment=dp,net_volume=s['net_volume'],positive_volume=s['positive_volume'],
                   normalized_net_volume=s['net_volume']/s['nozzle_scale_volume'],normalized_positive_volume=s['positive_volume']/s['nozzle_scale_volume'],
                   stage=v.STAGE,phase_convention=v.PHASE_CONVENTION,functional=v.FUNCTIONAL,plane='exit',quadrature=v.QUADRATURE)
        rows.append(row);s.update(time=b,previous_flow=r)
    return rows,s

class IndependentVerifierTests(unittest.TestCase):
    def test_constant(self):
        rows,final=samples([0,.2,.7,1.],[3,3,3,3]);r=v.verify(rows,state(3),3,1,final)
        self.assertTrue(r['passed']);self.assertEqual(r['computed_final_state']['net_volume'],3)

    def test_linear_nonuniform(self):
        ts=[0,.1,.8,1.3,2.];qs=[1+2*t for t in ts]
        rows,final=samples(ts,qs);r=v.verify(rows,state(1),4,2,final)
        self.assertTrue(r['passed']);self.assertAlmostEqual(float(r['decimal_net_volume']),6)

    def test_curved_sampling_difference_is_not_an_error_bound(self):
        def integral(n):
            ts=[i/n for i in range(n+1)];rows,_=samples(ts,[t*t for t in ts])
            return v.verify(rows,state(),n,1)['computed_final_state']['net_volume']
        coarse,fine=integral(2),integral(20)
        self.assertGreater(coarse-fine,100*v.RTOL)
        self.assertAlmostEqual(coarse-1/3,1/(6*4));self.assertAlmostEqual(fine-1/3,1/(6*400))

    def test_backflow_positive_net_is_not_local_outward_flux(self):
        rows,_=samples([0,1,2],[-1,1,-1]);r=v.verify(rows,state(-1),2,2)
        self.assertTrue(r['passed']);self.assertEqual(r['computed_final_state']['net_volume'],0)
        self.assertEqual(r['computed_final_state']['positive_volume'],1)
        # Simultaneous local outward 2 and inward -3 yield net -1, clipped 0,
        # not outward-local integral 2. This is a distinct spatial functional.
        self.assertNotEqual(max(2-3,0),max(2,0)+max(-3,0))

    def test_split_restart(self):
        rows,final=samples([0,.1,.4,.7,1.],[1,2,-1,4,2])
        middle=v.verify(rows[:2],state(1),2,.4)['computed_final_state']
        result=v.verify(rows[2:],middle,2,1,final)
        whole=v.verify(rows,state(1),4,1,final)
        self.assertTrue(result['passed']);self.assertEqual(result['computed_final_state'],whole['computed_final_state'])

    def test_dimensional_rescaling_and_nozzle_volume(self):
        rows,_=samples([0,1,2],[1,2,3]);base=v.verify(rows,state(1),2,2)
        scale=7.;t_scale=3.;initial=state(7,scale*t_scale)
        rr,_=samples([0,3,6],[7,14,21],initial)
        out=v.verify(rr,initial,2,6)
        self.assertAlmostEqual(out['computed_final_state']['net_volume']/(scale*t_scale),base['computed_final_state']['net_volume'])

    def test_missing_duplicate_permuted_rows(self):
        rows,_=samples([0,.1,.2,.3],[1,2,3,4])
        for bad in (rows[1:],rows[:-1],[rows[0],rows[0],rows[1]],list(reversed(rows))):
            with self.subTest(bad=bad),self.assertRaises(ValueError):v.verify(bad,state(1),3,.3)

    def test_zero_time_and_rejected_rows_fail(self):
        rows,_=samples([0,1],[1,2])
        for key,val in [('end',0),('accepted',False),('accepted','unknown'),('begin',.001),('dt',2)]:
            bad=copy.deepcopy(rows);bad[0][key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):v.verify(bad,state(1),1,1)

    def test_sample_counter_and_state_corruption(self):
        rows,final=samples([0,1,2],[1,2,3]);middle=v.verify(rows[:1],state(1),1,1)['computed_final_state']
        for key,val in [('previous_flow',2.001),('accepted_steps',0),('last_iteration',4),('time',.9)]:
            bad=dict(middle);bad[key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):v.verify(rows[1:],bad,1,2,final)
        bad=dict(middle);bad['net_volume']+=.01
        self.assertFalse(v.verify(rows[1:],bad,1,2)['passed'])
        with self.assertRaises(ValueError):v.verify(rows[1:],bad,1,2,final)

    def test_each_provenance_component(self):
        rows,_=samples([0,1],[1,2])
        for key in ('stage','phase_convention','functional','plane','quadrature','source_commit','solver_sha256','schedule_sha256','execution_id','case_role','schema'):
            bad=copy.deepcopy(rows);bad[0][key]='wrong'
            with self.subTest(key=key),self.assertRaises(ValueError):v.verify(bad,state(1),1,1)

    def test_exact_unchanged_tolerances(self):
        self.assertEqual((v.RTOL,v.ATOL),(5e-8,1e-12))
        rows,_=samples([0,1],[1,1]);rows[0]['net_volume']+=1e-6
        self.assertFalse(v.verify(rows,state(1),1,1)['passed'])

    def test_missing_unknown_nonfinite_and_duplicate_metadata(self):
        rows,_=samples([0,1],[1,2])
        for mutate in (lambda r:r.pop('stage'),lambda r:r.update(extra=2),lambda r:r.update(Q_right=float('nan'))):
            bad=copy.deepcopy(rows);mutate(bad[0])
            with self.assertRaises(ValueError):v.verify(bad,state(1),1,1)
        with self.assertRaises(ValueError):json.loads('{"x":1,"x":2}',object_pairs_hook=v.unique)
        bad=state(1);bad['net_volume']=1
        with self.assertRaises(ValueError):v.verify(rows,bad,1,1)

    def test_csv_round_trip_and_duplicate_header(self):
        rows,final=samples([0,.1,.7],[1,2,3])
        with tempfile.TemporaryDirectory(prefix='synthetic-integral-') as tmp:
            path=Path(tmp)/'trace.csv'
            with path.open('w') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            self.assertTrue(v.verify(v.csv_rows(path),state(1),2,.7,final)['passed'])
            path.write_text('a,a\n1,2\n')
            with self.assertRaises(ValueError):list(v.csv_rows(path))

    def test_paths_no_symlink_tree_missing_traversal(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-integral-') as tmp:
            root=Path(tmp);real=root/'real';real.write_text('1');link=root/'link';link.symlink_to(real)
            for path in (root,root/'missing',link,root/'x'/'..'/'real'):
                with self.subTest(path=path),self.assertRaises(ValueError):v.file_identity(path)

    def test_legacy_zero_time_endpoint_replacement(self):
        # Exact scalar arithmetic from the frozen historical implementation.
        def legacy(events):
            last=-1;previous=0;total=0
            for t,q in events:
                if last>=0 and t>last+1e-12:total+=(previous+q)*(t-last)/2
                previous=q;last=t
            return total
        self.assertEqual(legacy([(0,1),(1,1)]),1)
        self.assertEqual(legacy([(0,1),(0,3),(1,1)]),2)
        # This proves sensitivity of that algorithm, not the historical cause
        # of absent high-cadence samples or the actual CFD trajectory.

class CState(ct.Structure):
    _fields_=[('accepted_steps',ct.c_uint64),('last_iteration',ct.c_int64),
              ('time',ct.c_double),('previous_flow',ct.c_double),('net_volume',ct.c_double),
              ('positive_volume',ct.c_double),('initialized',ct.c_int)]

class NativeBookkeepingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch=tempfile.TemporaryDirectory(prefix='synthetic-integral-native-')
        root=Path(__file__).parents[1];output=Path(cls.scratch.name)/'bookkeeping.so'
        subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(root/'cases/basilisk'),str(root/'tests/fixtures/internal_nozzle_step_integral_wrapper.c'),'-lm','-o',str(output)],check=True)
        cls.lib=ct.CDLL(str(output));cls.lib.initialize.argtypes=[ct.POINTER(CState),ct.c_double,ct.c_double]
        cls.lib.advance.argtypes=[ct.POINTER(CState),ct.c_uint64,ct.c_int64,ct.c_double,ct.c_double,ct.c_double,ct.c_int]
        cls.lib.valid.argtypes=[ct.POINTER(CState)]
    @classmethod
    def tearDownClass(cls):cls.scratch.cleanup()
    def init(self,q=1.):
        s=CState();self.assertEqual(self.lib.initialize(ct.byref(s),0,q),1);return s
    def test_native_independent_reconstruction(self):
        ts=[0,.1,.4,.9,1.];qs=[1,2,-3,2,4];s=self.init();rows,final=samples(ts,qs)
        for k,(a,b,q) in enumerate(zip(ts,ts[1:],qs[1:])):
            self.assertEqual(self.lib.advance(ct.byref(s),k+1,k,a,b,q,1),1)
            self.assertTrue(v.close(s.net_volume,rows[k]['net_volume']))
            self.assertTrue(v.close(s.positive_volume,rows[k]['positive_volume']))
        self.assertTrue(v.verify(rows,state(1),4,1,final)['passed'])
    def test_rejected_step_does_not_mutate(self):
        s=self.init();old=bytes(s)
        self.assertEqual(self.lib.advance(ct.byref(s),999,999,1,0,float('nan'),0),1)
        self.assertEqual(bytes(s),old)
    def test_bad_steps_fail_without_mutating(self):
        for args in [(2,0,0,1,2,1),(1,1,0,1,2,1),(1,0,0,0,2,1),
                     (1,0,.1,1,2,1),(1,0,0,1,float('nan'),1),(1,0,0,1,2,2)]:
            s=self.init();old=bytes(s)
            self.assertEqual(self.lib.advance(ct.byref(s),*args),0);self.assertEqual(bytes(s),old)
    def test_split_native_state(self):
        s=self.init();self.assertEqual(self.lib.advance(ct.byref(s),1,0,0,.3,2,1),1)
        restored=CState.from_buffer_copy(bytes(s))
        for obj in (s,restored):self.assertEqual(self.lib.advance(ct.byref(obj),2,1,.3,1.,-1,1),1)
        self.assertEqual(bytes(s),bytes(restored))
    def test_duplicate_does_not_mutate(self):
        s=self.init();self.assertEqual(self.lib.advance(ct.byref(s),1,0,0,1,2,1),1);old=bytes(s)
        self.assertEqual(self.lib.advance(ct.byref(s),1,0,0,1,2,1),0);self.assertEqual(bytes(s),old)
    def test_corrupt_state_fails(self):
        for key,val in [('initialized',0),('positive_volume',-1),('time',float('nan')),('previous_flow',float('inf')),('last_iteration',2**63-1),('accepted_steps',2**64-1)]:
            s=self.init();setattr(s,key,val);self.assertEqual(self.lib.valid(ct.byref(s)),0)
    def test_counter_overflow_rejected_without_mutation(self):
        s=self.init();s.last_iteration=2**63-2;s.accepted_steps=2**63-1
        self.assertEqual(self.lib.valid(ct.byref(s)),1);old=bytes(s)
        self.assertEqual(self.lib.advance(ct.byref(s),2**63,2**63-1,0,1,2,1),0)
        self.assertEqual(bytes(s),old)

if __name__=='__main__':unittest.main(verbosity=2)
