import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
"""Clearly synthetic reader fixtures; never scientific result records."""
import copy
import importlib.util
from pathlib import Path
import sys

import pytest


def load(name, filename):
    path = Path(__file__).parents[1] / 'scripts' / filename
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


fields = load('field_identity_test_reader', 'audit_internal_nozzle_field_event_identities.py')


def fixture():
    summary = {'checkpoint_iteration': 20}
    comparisons = {}
    for label, (left, right, offset) in fields.EXPECTED.items():
        row = {'count': 1, 'changed_count': 0, 'max_absolute': 0.,
               'max_point_normalized': 0., 'weighted_relative_l2': 0.,
               'support_min': None, 'support_max': None,
               'nonfinite_left_count': 0, 'nonfinite_right_count': 0,
               'nonfinite_bitwise_disagreement_count': 0,
               'finite_pair_count': 1, 'norm_scope': 'full_observed_field'}
        summaries = {f'cell/{g}/{k}': copy.deepcopy(row) for g in (0, 1, 2) for k in fields.CELL}
        summaries.update({f'face/{g}/{k}': copy.deepcopy(row) for g in (0, 1, 2) for k in fields.FACE})
        header = {'i': 20 + offset, 't': .2 + offset * .01, 'dt': .01, 'exit_x': 15.}
        comparisons[label] = {'schema': 'internal_nozzle_keyed_state_comparison_v1',
            'exact_keys_and_geometry': True, 'left_header': {**header, 'phase': left},
            'right_header': {**header, 'phase': right}, 'summaries': summaries}
    return summary, comparisons


def test_complete_synthetic_field_identity_is_not_numerical_equivalence():
    summary, comparisons = fixture()
    result = fields.inspect(summary, comparisons)
    assert result['passed'] and result['numeric_full_field_equivalence_claimed'] is False


def test_inactive_unavailability_remains_explicit_not_zero():
    summary, comparisons = fixture()
    value = comparisons['matched-next-post_projection']['summaries']['cell/2/p']
    value.update(nonfinite_left_count=1, nonfinite_right_count=1, finite_pair_count=0,
                 norm_scope='finite_paired_subset_only_not_full_field_equivalence')
    result = fields.inspect(summary, comparisons)
    assert result['passed']
    assert result['observed_stages']['matched-next-post_projection']['unavailable_values']['cell/2/p']['finite_pair_count'] == 0


@pytest.mark.parametrize('mutation', ['time', 'iteration', 'phase', 'dt', 'geometry',
                                     'missing_field', 'physical_nonfinite', 'join', 'serialization', 'missing_stage'])
def test_field_identity_defects_fail(mutation):
    summary, comparisons = fixture()
    value = comparisons['matched-next-post_projection']
    if mutation == 'time': value['right_header']['t'] += 1e-16
    elif mutation == 'iteration': value['right_header']['i'] += 1
    elif mutation == 'phase': value['right_header']['phase'] = 'wrong'
    elif mutation == 'dt': value['right_header']['dt'] += 1e-16
    elif mutation == 'geometry': value['right_header']['exit_x'] += 1
    elif mutation == 'missing_field': del value['summaries']['face/0/uf']
    elif mutation == 'physical_nonfinite': value['summaries']['cell/0/p']['nonfinite_left_count'] = 1
    elif mutation == 'join': value['exact_keys_and_geometry'] = False
    elif mutation == 'serialization': comparisons['fresh-post-projection-to-post-checkpoint']['summaries']['cell/0/ux']['changed_count'] = 1
    elif mutation == 'missing_stage': del comparisons['matched-next-post_projection']
    assert not fields.inspect(summary, comparisons)['passed']


def test_finite_evolved_difference_is_reported_without_invented_field_threshold():
    summary, comparisons = fixture()
    row = comparisons['matched-next-post_projection']['summaries']['cell/0/p']
    row.update(changed_count=1, max_absolute=.1, max_point_normalized=.1, weighted_relative_l2=.1)
    result = fields.inspect(summary, comparisons)
    assert result['passed'] and result['numeric_full_field_equivalence_claimed'] is False
    assert result['observed_stages']['matched-next-post_projection']['finite_differences']['cell/0/p']['max_absolute'] == .1
    # This is only the identity gate. Independent hydraulic criteria decide
    # whether an actual evolved numerical difference is scientifically accepted.
