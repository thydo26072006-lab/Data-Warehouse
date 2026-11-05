"""Validation failures must quarantine evidence and preserve the last valid output."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from preprocess import ROOT, OUTPUT_COLUMNS, ValidationError, normalize, preprocess


class PreprocessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with (ROOT / 'data/superstore.csv').open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            self.headers = reader.fieldnames
            self.row = next(reader)

    def run_batch(self, rows):
        source = self.root / 'input.csv'
        with source.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=self.headers)
            writer.writeheader()
            writer.writerows(rows)
        return preprocess(source, self.root / 'output.csv', self.root / 'report.json', self.root / 'rejected.csv')

    def assert_rejected(self, rows, expected_count):
        output = self.root / 'output.csv'
        output.write_bytes(b'previous valid snapshot')
        with self.assertRaises(ValidationError):
            self.run_batch(rows)
        self.assertEqual(output.read_bytes(), b'previous valid snapshot')
        report = json.loads((self.root / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'rejected_batch')
        self.assertEqual(report['rejected_rows'], expected_count)
        with (self.root / 'rejected.csv').open(encoding='utf-8-sig', newline='') as stream:
            rejected = list(csv.DictReader(stream))
        self.assertEqual(len(rejected), expected_count)
        self.assertTrue(all(row['reason'] and row['raw_json'] for row in rejected))

    def test_valid_batch_preserves_id_and_zero_sales_margin(self):
        self.row.update({'Sales': '0', 'Profit': '-1.11'})
        result = self.run_batch([self.row])
        self.assertEqual(result['zero_sales_rows'], 1)
        self.assertEqual(result['database_status'], 'not_run')
        with (self.root / 'output.csv').open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            row = next(reader)
            self.assertEqual(reader.fieldnames, OUTPUT_COLUMNS)
        self.assertEqual(row['row_id'], self.row['Row.ID'])
        self.assertEqual(row['profit_margin'], '')
        self.assertEqual(row['profit'], '-1.11')

    def test_invalid_numeric_is_quarantined(self):
        self.row['Quantity'] = '0'
        self.assert_rejected([self.row], 1)

    def test_python_numbers_follow_pdf_and_csv_margin_stays_unrounded(self):
        self.row.update({'Profit': '9.3312', 'Sales': '19'})
        row = normalize(self.row)
        self.assertIsInstance(row['profit'], float)
        self.assertIsInstance(row['sales'], float)
        self.assertEqual(row['profit_margin'], 9.3312 / 19.0)
        self.assertNotEqual(row['profit_margin'], round(row['profit_margin'], 8))
        self.run_batch([self.row])
        with (self.root / 'output.csv').open(encoding='utf-8-sig', newline='') as stream:
            saved = next(csv.DictReader(stream))
        self.assertEqual(saved['profit_margin'], str(9.3312 / 19.0))

    def test_nonfinite_money_is_quarantined(self):
        self.row['Profit'] = 'NaN'
        self.assert_rejected([self.row], 1)

    def test_invalid_date_order_is_quarantined(self):
        self.row['Ship.Date'] = '2010-01-01 00:00:00.000'
        self.assert_rejected([self.row], 1)

    def test_duplicate_ids_quarantine_both_records(self):
        self.assert_rejected([self.row, self.row.copy()], 2)

    def test_conflicting_product_descriptions_quarantine_entire_key(self):
        second = dict(self.row, **{'Row.ID': '999999', 'Category': 'Different category'})
        self.assert_rejected([self.row, second], 2)

    def test_missing_column_rejects_batch(self):
        self.headers.remove('Year')
        del self.row['Year']
        self.assert_rejected([self.row], 0)


if __name__ == '__main__':
    unittest.main()
