"""Compile the actual callback dispatch prefixes with observer-only C stubs.

This is callback/control coverage, not a scientific probe-neutrality result.
"""
from pathlib import Path
import subprocess
import pytest

SOURCE=Path(__file__).resolve().parents[1]/'cases/basilisk/rectangular_internal_nozzle_convergence_visual.c'

def function(text,name):
    begin=text.index(name+' (') if name+' (' in text else text.index(name+'\n')
    start=text.index('{',begin);level=1;end=start+1
    while level:
        level+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[begin:end]

@pytest.fixture(scope='module')
def dispatch(tmp_path_factory):
    text=SOURCE.read_text()
    active=function(text,'projection_trace_active')
    prediction=function(text,'internal_nozzle_prediction_trace_stage').split('  char cell_path[1024]')[0]+'}\n'
    projection=function(text,'internal_nozzle_projection_trace_stage').split('  char data_path[1024]')[0]+'}\n'
    assert 'forensic_snapshot_end_time' not in prediction+projection
    native='static int '+active+'\nvoid '+prediction+'\nvoid '+projection
    native=native.replace('(const) face vector','int').replace('face vector','int')
    header='''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { const char *name; } scalar;
scalar pf={"pf"};
int enable_forensic_probes,iter=363,audits=0,stencils=0;
double t,forensic_start_time=1.,forensic_end_time=1.1,forensic_snapshot_end_time;
char projection_trace_dir[8]="trace",last[160]="";
void internal_nozzle_stencil_trace(const char *phase,int i){stencils++;}
void internal_nozzle_state_audit(const char *phase,int i){audits++;snprintf(last,sizeof(last),"%s",phase);}
'''
    main='''int main(int argc,char **argv){
enable_forensic_probes=atoi(argv[1]);t=atof(argv[2]);forensic_snapshot_end_time=atof(argv[3]);
scalar pressure={argv[4]},div={"div"};
internal_nozzle_prediction_trace_stage("before_prediction",0,0);
internal_nozzle_prediction_trace_stage("after_prediction_pre_projection",0,0);
internal_nozzle_projection_trace_stage("after_divergence_pre_poisson",0,pressure,0,div,.01,4);
internal_nozzle_projection_trace_stage("after_velocity_correction",0,pressure,0,div,.01,4);
printf("%d %d %s\\n",audits,stencils,last);return 0;}
'''
    d=tmp_path_factory.mktemp('compact-native-dispatch');src=d/'dispatch.c';src.write_text(header+native+main)
    subprocess.run(['cc','-std=c99','-Wall',str(src),'-o',str(d/'dispatch')],check=True,capture_output=True)
    return d/'dispatch'

@pytest.mark.parametrize('snapshot',[-1.,0.,1.01,100.])
@pytest.mark.parametrize('pressure',['p','pf'])
def test_four_callbacks_independent_of_bulk_snapshot(dispatch,snapshot,pressure):
    r=subprocess.run([str(dispatch),'2','1.002',str(snapshot),pressure],check=True,capture_output=True,text=True)
    assert r.stdout==f'4 2 project_{pressure}_after_velocity_correction\n'

@pytest.mark.parametrize('mode,t,pressure,expected',[(0,1.002,'pf','0 0'),(1,1.002,'pf','0 0'),(2,.99,'pf','0 0'),(2,1.11,'pf','0 0'),(2,1.002,'alien','2 2')])
def test_inactive_and_wrong_pressure_still_excluded(dispatch,mode,t,pressure,expected):
    r=subprocess.run([str(dispatch),str(mode),str(t),'-1',pressure],check=True,capture_output=True,text=True)
    assert r.stdout.startswith(expected+' ')

def test_bulk_snapshot_gate_still_separate():
    audit=(SOURCE.parent/'internal_nozzle_state_audit.h').read_text()
    assert 'if (forensic_snapshot_end_time < 0. || t > forensic_snapshot_end_time + 1e-14)' in audit
    assert audit.index('fputs("]}\\n", fp); fclose(fp);')<audit.index('if (forensic_snapshot_end_time < 0.')
