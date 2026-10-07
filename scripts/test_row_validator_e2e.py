"""Ensure the E2E assertions reject broken reports and changed original rows."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from run_e2e import row_validator_cases as cases


class RowValidatorE2ETests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.work = Path(directory.name)

    def records(self, *, failed=False, single=False, copy_id=0, count=4, output=None):
        return [
            {'record_type': 'run_start', 'schema_version': 1, 'run_id': f'run-{copy_id}',
             'copy': copy_id, 'mode': 'single_pass' if single else 'full',
             'class': 'Rows.Data.Row'},
            *([{'record_type': 'issue', 'severity': 'ERROR', 'phase': 'second_pass',
                'copy': copy_id, 'input_number': count}] if failed else []),
            {'record_type': 'validation_end', 'complete': not (single and failed),
             'errors': 1 if failed else 0, 'warnings': 0, 'input_rows': count,
             'release': not failed},
            {'record_type': 'run_end', 'status': 'validation_failed' if failed else 'success',
             'input_rows': count, 'output_rows': output if output is not None else (0 if failed else count)},
        ]

    def report(self, records, name='report.jsonl'):
        path = self.work / name
        path.write_text(''.join(json.dumps(record) + '\n' for record in records), encoding='utf-8')
        return path

    def test_accepts_success_failure_and_empty_reports(self):
        for case, records in [('valid', self.records()),
                              ('late-unique', self.records(failed=True)),
                              ('empty', self.records(count=0))]:
            with self.subTest(case=case):
                self.assertEqual(cases.verify_reports([self.report(records)], case), [records[-1]])

    def test_rejects_missing_duplicate_or_out_of_order_terminal_records(self):
        good = self.records()
        for records in [[], good[:-1], good[1:], [good[0], good[-1]],
                        [good[0], good[1], good[1], good[-1]],
                        [good[0], good[-1], good[1]]]:
            with self.subTest(records=records), self.assertRaises(AssertionError):
                cases.verify_reports([self.report(records)], 'valid')

    def test_rejects_truncated_json(self):
        path = self.report(self.records())
        with path.open('a', encoding='utf-8') as stream:
            stream.write('{"record_type":')
        with self.assertRaises(json.JSONDecodeError):
            cases.verify_reports([path], 'valid')

    def test_rejects_inconsistent_counts_release_and_status(self):
        for record, key, value in [(1, 'input_rows', 3), (1, 'release', False),
                                   (1, 'complete', False), (1, 'errors', 1),
                                   (2, 'input_rows', 5), (2, 'output_rows', 3),
                                   (2, 'output_rows', 5), (2, 'status', 'technical_error')]:
            with self.subTest(key=key, value=value):
                records = self.records()
                records[record][key] = value
                with self.assertRaises(AssertionError):
                    cases.verify_reports([self.report(records)], 'valid')

    def test_rejects_output_after_late_full_validation_failure(self):
        path = self.report(self.records(failed=True, output=1))
        with self.assertRaises(AssertionError):
            cases.verify_reports([path], 'late-unique')

    def test_single_pass_failure_requires_two_read_rows_and_one_emitted_row(self):
        records = self.records(failed=True, single=True, count=2, output=1)
        cases.verify_reports([self.report(records)], 'single-invalid')
        for count, output in [(2, 0), (2, 2), (4, 1)]:
            with self.subTest(count=count, output=output), self.assertRaises(AssertionError):
                cases.verify_reports([self.report(self.records(
                    failed=True, single=True, count=count, output=output))], 'single-invalid')

    def test_parallel_reports_require_distinct_copies_and_runs(self):
        records = [self.records(single=True, copy_id=i, count=2) for i in range(2)]
        paths = [self.report(report, f'copy-{i}.jsonl') for i, report in enumerate(records)]
        cases.verify_reports(paths, 'single-parallel')
        for key in ('copy', 'run_id'):
            changed = copy.deepcopy(records)
            changed[1][0][key] = changed[0][0][key]
            with self.subTest(key=key), self.assertRaises(AssertionError):
                cases.verify_reports([self.report(report, f'copy-{i}.jsonl')
                                      for i, report in enumerate(changed)], 'single-parallel')
        with self.assertRaises(AssertionError):
            cases.verify_reports(paths[:1], 'single-parallel')

    def test_rejects_issue_from_wrong_copy_or_unread_row(self):
        for key, value in [('copy', 1), ('input_number', 5)]:
            records = self.records(failed=True)
            records[1][key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                cases.verify_reports([self.report(records)], 'late-unique')

    def output(self, rows, fields=cases.FIELDS, case='valid'):
        with (self.work / (case + '.csv')).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream, delimiter=';')
            writer.writerow(fields)
            writer.writerows(rows)

    def test_output_preserves_all_original_values_in_order(self):
        rows = [(str(i), '3', '1', '2', f' extra-{i}; "ä<&>" ') for i in range(4)]
        self.output(rows)
        cases.verify_output(self.work, 'valid')
        self.output(rows[::-1])
        with self.assertRaises(AssertionError):
            cases.verify_output(self.work, 'valid')
        self.output([(*row[:-1], row[-1].strip()) for row in rows])
        with self.assertRaises(AssertionError):
            cases.verify_output(self.work, 'valid')

    def test_parallel_output_preserves_rows_without_requiring_global_order(self):
        rows = [(str(i), '3', '1', '2', f' extra-{i}; "ä<&>" ') for i in (2, 0, 3, 1)]
        self.output(rows, case='single-parallel')
        cases.verify_output(self.work, 'single-parallel')

    def test_full_validation_failure_rejects_even_one_output_row(self):
        self.output([('0', '3', '1', '2', 'extra')], case='late-unique')
        with self.assertRaises(AssertionError):
            cases.verify_output(self.work, 'late-unique')

    def test_rejects_changed_output_schema(self):
        self.output([], fields=(*cases.FIELDS, 'is_valid'))
        with self.assertRaises(AssertionError):
            cases.verify_output(self.work, 'valid')


if __name__ == '__main__':
    unittest.main()
