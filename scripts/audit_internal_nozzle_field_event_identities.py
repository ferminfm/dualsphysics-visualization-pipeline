"""Validate the identities and coverage of an observed keyed restart trace.

This does not invent a full-field numerical tolerance. Finite differences and
inactive/coarse unavailable values remain diagnostic measurements. Hydraulic
acceptance is performed independently with every original registered metric.
"""
import argparse
import json
from pathlib import Path
import sys

CELL = 'f ux uy uz gx gy gz p pf cs cm un rho'.split()
FACE = 'uf fs fm a alpha mu'.split()
EXPECTED = {
    'fresh-post-projection-to-post-checkpoint': ('post_projection', 'post_checkpoint', 0),
    'checkpoint-to-post_restore_pre_centered': ('post_checkpoint', 'post_restore_pre_centered', 0),
    'checkpoint-to-stability_post_sidecar': ('post_checkpoint', 'stability_post_sidecar', 0),
    'matched-next-stability_post_sidecar': ('stability_post_sidecar', 'stability_post_sidecar', 1),
    'matched-next-before_advection_term': ('before_advection_term', 'before_advection_term', 1),
    'matched-next-before_projection': ('before_projection', 'before_projection', 1),
    'matched-next-post_projection': ('post_projection', 'post_projection', 1),
}


def inspect(summary, comparisons):
    errors = []
    observed = {}
    cp = summary['checkpoint_iteration']
    if set(comparisons) != set(EXPECTED):
        errors.append('missing_or_extra_event_comparison')
    for label, (left_phase, right_phase, offset) in EXPECTED.items():
        value = comparisons.get(label)
        if value is None:
            continue
        if value.get('schema') != 'internal_nozzle_keyed_state_comparison_v1' or value.get('exact_keys_and_geometry') is not True:
            errors.append(label + ':unproven_key_geometry_join')
            continue
        left, right = value['left_header'], value['right_header']
        if (left['phase'], right['phase']) != (left_phase, right_phase):
            errors.append(label + ':wrong_event_phase')
        if left['i'] != cp + offset or right['i'] != cp + offset:
            errors.append(label + ':wrong_iteration')
        if left['t'] != right['t'] or left['exit_x'] != right['exit_x']:
            errors.append(label + ':different_native_time_or_geometry')
        if offset and left['dt'] != right['dt']:
            errors.append(label + ':different_matched_event_timestep')
        # The early pre-centered restore stage deliberately precedes derived
        # coefficient reconstruction; no bitwise-field equality is inferred.
        fields = value['summaries']
        expected_fields = {f'cell/{group}/{name}' for group in (0, 1, 2) for name in CELL}
        expected_fields |= {f'face/{axis}/{name}' for axis in (0, 1, 2) for name in FACE}
        if set(fields) != expected_fields:
            errors.append(label + ':incomplete_primary_cell_or_face_coverage')
        physical_nonfinite = []
        unavailable = {}
        differences = {}
        for key, row in fields.items():
            if row['count'] <= 0:
                errors.append(label + ':empty_observed_field:' + key)
            nonfinite = row['nonfinite_left_count'] + row['nonfinite_right_count']
            if nonfinite:
                unavailable[key] = {name: row[name] for name in ('count', 'finite_pair_count',
                    'nonfinite_left_count', 'nonfinite_right_count', 'nonfinite_bitwise_disagreement_count',
                    'norm_scope')}
                if not key.startswith('cell/2/'):
                    physical_nonfinite.append(key)
            if row['changed_count']:
                differences[key] = {name: row[name] for name in ('changed_count', 'max_absolute',
                    'max_point_normalized', 'weighted_relative_l2', 'support_min', 'support_max', 'norm_scope')}
        errors.extend(label + ':nonfinite_physical_field:' + key for key in physical_nonfinite)
        if label == 'fresh-post-projection-to-post-checkpoint':
            # Serialization must not mutate any observed finite value. Unknown
            # values are not equated: even their bitwise disagreements are kept.
            if any(row['changed_count'] or row['nonfinite_bitwise_disagreement_count'] for row in fields.values()):
                errors.append(label + ':serialization_side_effect')
        observed[label] = {'left_header': left, 'right_header': right,
                           'finite_differences': differences, 'unavailable_values': unavailable}
    return {'field_event_identity_errors': errors, 'unresolved_field_event_identity_errors': len(errors),
            'passed': not errors, 'observed_stages': observed,
            'numeric_full_field_equivalence_claimed': False,
            'identity_gate_definition': 'exact keys, native time/iteration, matched event dt, geometry, complete primary-field coverage, physical finite availability, and absence of serialization side effects',
            'numerical_acceptance_scope': 'all original registered hydraulic/profile/raw and exact-count restart metrics are evaluated separately; no new field tolerance or pressure gauge subtraction'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source-root', 'comparison', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.source_root / 'scripts'))
    import internal_nozzle_qualification as gate
    summary = gate.load(a.comparison / 'summary.json')
    if summary['schema'] != 'internal_nozzle_diagnostic_first_divergence_packet_v1':
        raise ValueError('wrong actual trace summary')
    comparisons = {}
    inputs = [gate.file_record(a.comparison / 'summary.json')]
    for row in summary['comparisons']:
        if row['label'] in comparisons:
            raise ValueError('duplicate event comparison')
        if row['structural_join'] != 'exact':
            comparisons[row['label']] = {'structural_join': 'failed'}
            continue
        path = gate.verify_file(row['comparison'])
        record = gate.load(path)
        for side in ('left', 'right'):
            gate.verify_file(record[side])
            inputs.append(record[side])
        inputs.append(gate.file_record(path))
        comparisons[row['label']] = record
    result = inspect(summary, comparisons)
    result.update(schema='internal_nozzle_field_event_identity_audit_v1',
                  material_identity=summary['material_identity'],
                  inputs=list({r['path']:r for r in inputs}.values()),
                  source_trace_summary=gate.file_record(a.comparison / 'summary.json'))
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'identity_errors': result['field_event_identity_errors'],
                      'numeric_full_field_equivalence_claimed': False}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
