"""Deterministic contract tests; not a CFD qualification result."""
from pathlib import Path
import math

SOURCE = Path(__file__).parents[1] / 'cases/basilisk/rectangular_internal_nozzle_convergence_visual.c'

def subdivide(now, next_tick, cap):
    # Exact branch/formula of the pinned native events.h dtnext().
    assert math.isfinite(now) and next_tick > now and cap > 0
    count = int((next_tick-now)/cap)
    if count == 0:
        return next_tick-now
    if (next_tick-now)/count > cap*(1.+1e-10):
        return (next_tick-now)/(count+1)
    return (next_tick-now)/count

def test_terminal_lookahead_matches_interior_subdivision():
    tick = .013925712636838899
    now = 21*tick
    result = subdivide(now, 22*tick, .0004)
    assert result < .0004
    assert abs(result-.00039787750390968268) < 1e-15
    assert result == subdivide(now, 22*tick, .0004)

def test_nominal_label_does_not_replace_native_clock():
    source = SOURCE.read_text()
    recovery = source.split('static void recover_checkpoint_metadata',1)[1].split('static ',1)[0]
    assert 'internal_nozzle_same_double_v4(native_restore_time, found_actual)' in recovery
    assert 'restore_time = found_actual;' in recovery
    assert 't = found_target;' not in recovery
    actual = .27851425273677793
    target = .27851425273677799
    assert actual != target and math.nextafter(actual, math.inf) == target

def test_clock_and_stop_preserve_completed_step_order():
    source = SOURCE.read_text()
    assert '(t = 0.; t += diagnostic_dt; canonical_schedule_enabled())' in source
    assert 'event end (t = canonical_schedule_enabled() ? HUGE : end_time)' in source
    stop = source.split('event canonical_terminal_stop (i++, last)',1)[1]
    assert 't + schedule_time_tolerance < end_time' in stop
    assert 'event("end");' in stop and 'return 1;' in stop
    assert source.index('event canonical_terminal_stop') > source.index('event canonical_checkpoint_dumps')
