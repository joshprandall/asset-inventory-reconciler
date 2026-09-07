import copy
import csv
from datetime import date
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reconcile as app
ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 9, 7)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.baseline, _ = app.read_inventory(ROOT / 'examples/baseline.csv', AS_OF)
        self.current, _ = app.read_inventory(ROOT / 'examples/current.csv', AS_OF)

    def read_text(self, text):
        path = self.folder / 'input.csv'
        path.write_text(text, encoding='utf-8')
        return app.read_inventory(path, AS_OF)[0]

    def single(self, **changes):
        row = dict(self.current['LT-101'], **changes)
        return {row['asset_tag']: row}

    def codes(self, records):
        return [f['code'] for f in app.analyze(records, records, AS_OF)['findings']]

    def test_sample_counts(self):
        result = app.analyze(self.baseline, self.current, AS_OF)
        self.assertEqual(result['counts'], dict(baseline_assets=6, current_assets=6, added_assets=1, missing_assets=1, changed_assets=4, field_changes=5, findings=9))

    def test_input_not_mutated(self):
        before = copy.deepcopy(self.current)
        app.analyze(self.baseline, self.current, AS_OF)
        self.assertEqual(before, self.current)

    def test_no_snapshot_changes(self):
        self.assertEqual(app.analyze(self.current, self.current, AS_OF)['changes'], [])

    def test_empty_inventories(self):
        self.assertEqual(app.analyze({}, {}, AS_OF)['findings'], [])

    def test_stale_boundary_exclusive(self):
        self.assertNotIn('STALE_RECORD', self.codes(self.single(last_seen='2026-08-08')))
        self.assertIn('STALE_RECORD', self.codes(self.single(last_seen='2026-08-07')))

    def test_warranty_boundary_inclusive(self):
        self.assertIn('WARRANTY_DUE', self.codes(self.single(warranty_end='2026-11-06')))
        self.assertNotIn('WARRANTY_DUE', self.codes(self.single(warranty_end='2026-11-07')))

    def test_warranty_today_due_not_expired(self):
        codes = self.codes(self.single(warranty_end='2026-09-07'))
        self.assertIn('WARRANTY_DUE', codes)
        self.assertNotIn('WARRANTY_EXPIRED', codes)

    def test_retired_only_assignment_review(self):
        self.assertEqual(self.codes(self.single(status='retired', last_seen='', warranty_end='')), ['RETIRED_ASSIGNED'])

    def test_spare_can_have_no_assignee(self):
        self.assertNotIn('MISSING_ASSIGNEE', self.codes(self.single(status='spare', assigned_to='')))

    def test_duplicate_asset_case_insensitive(self):
        text = (ROOT / 'examples/current.csv').read_text()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.read_text(text + 'lt-101,DIFFERENT,,Office,spare,,\n')

    def test_duplicate_serial_case_insensitive(self):
        text = (ROOT / 'examples/current.csv').read_text()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.read_text(text + 'NEW,sn101,,Office,spare,,\n')

    def test_header_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            self.read_text('asset_tag,serial,assigned_to,site,status,last_seen,last_seen\n')

    def test_missing_cell_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            self.read_text(','.join(app.FIELDS) + '\nX,S,,Office,spare,\n')

    def test_extra_cell_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            self.read_text(','.join(app.FIELDS) + '\nX,S,,Office,spare,,,extra\n')

    def test_future_last_seen_rejected(self):
        with self.assertRaisesRegex(ValueError, 'future'):
            self.read_text(','.join(app.FIELDS) + '\nX,S,,Office,spare,2026-09-08,\n')

    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):
            app.iso_date('2026-02-30')
        with self.assertRaises(ValueError):
            app.iso_date('20260907')

    def test_negative_threshold_rejected(self):
        with self.assertRaises(ValueError):
            app.analyze({}, {}, AS_OF, -1)

    def test_unknown_status_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown status'):
            self.read_text(','.join(app.FIELDS) + '\nX,S,,Office,maybe,,\n')

    def test_html_escaping(self):
        report = app.analyze(self.single(assigned_to='Old'), self.single(assigned_to='<script>alert(1)</script>'), AS_OF)
        markup = app.render_html(report)
        self.assertNotIn('<script>alert(1)</script>', markup)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', markup)

    def test_csv_formula_prefixes(self):
        for prefix in ('=', '+', '-', '@'):
            self.assertTrue(app.csv_safe(prefix + 'test').startswith("'"))
        self.assertEqual(app.csv_safe('normal'), 'normal')

    def test_deterministic_order(self):
        self.assertEqual(app.analyze(self.baseline, self.current, AS_OF), app.analyze(dict(reversed(list(self.baseline.items()))), dict(reversed(list(self.current.items()))), AS_OF))

    def test_report_roundtrip_and_no_overwrite(self):
        output = self.folder / 'report'
        report = app.analyze(self.baseline, self.current, AS_OF)
        app.write_reports(report, output)
        self.assertEqual(json.loads((output / 'summary.json').read_text()), report)
        with self.assertRaises(FileExistsError):
            app.write_reports(report, output)
        self.assertEqual(len(list(csv.DictReader(io.StringIO((output / 'findings.csv').read_text())))), 9)

    def test_cli_findings_exit_one(self):
        run = subprocess.run([sys.executable, str(ROOT / 'reconcile.py'), str(ROOT / 'examples/baseline.csv'), str(ROOT / 'examples/current.csv'), '--as-of', AS_OF.isoformat(), '--output', str(self.folder / 'cli')], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertTrue((self.folder / 'cli/report.html').is_file())

    def test_cli_clean_exit_zero(self):
        path = self.folder / 'empty.csv'
        path.write_text(','.join(app.FIELDS) + '\n')
        run = subprocess.run([sys.executable, str(ROOT / 'reconcile.py'), str(path), str(path), '--as-of', AS_OF.isoformat(), '--output', str(self.folder / 'clean')], capture_output=True)
        self.assertEqual(run.returncode, 0)

    def test_cli_invalid_no_output(self):
        output = self.folder / 'invalid'
        run = subprocess.run([sys.executable, str(ROOT / 'reconcile.py'), 'missing.csv', 'missing.csv', '--as-of', AS_OF.isoformat(), '--output', str(output)], capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
