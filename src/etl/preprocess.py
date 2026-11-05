"""Reproducible source CSV validation, quarantine and normalization (PDF section 2.2).

Invalid batches leave the previous processed CSV intact. No database is contacted.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COLMAP = {
    'Category': 'category', 'City': 'city', 'Country': 'country',
    'Customer.ID': 'customer_id', 'Customer.Name': 'customer_name',
    'Discount': 'discount', 'Market': 'market', 'Order.Date': 'order_date',
    'Order.ID': 'order_id', 'Order.Priority': 'order_priority',
    'Product.ID': 'product_id', 'Product.Name': 'product_name', 'Profit': 'profit',
    'Quantity': 'quantity', 'Region': 'region', 'Row.ID': 'row_id', 'Sales': 'sales',
    'Segment': 'segment', 'Ship.Date': 'ship_date', 'Ship.Mode': 'ship_mode',
    'Shipping.Cost': 'shipping_cost', 'State': 'state',
    'Sub.Category': 'sub_category', 'Market2': 'market_group', 'weeknum': 'weeknum',
}
OUTPUT_COLUMNS = list(COLMAP.values()) + ['profit_margin']
INTEGER_LIMITS = {'row_id': (1, 2147483647), 'quantity': (1, 32767), 'weeknum': (1, 53)}
DECIMALS = ['sales', 'profit', 'discount', 'shipping_cost']
TEXT_LIMITS = {
    'category': 50, 'city': 100, 'country': 100, 'customer_id': 20,
    'customer_name': 100, 'market': 20, 'order_id': 30, 'order_priority': 20,
    'product_id': 30, 'product_name': 255, 'region': 50, 'segment': 30,
    'ship_mode': 30, 'state': 100, 'sub_category': 50, 'market_group': 30,
}
KEYS = {
    'dim_customer': (['customer_id'], ['customer_name', 'segment']),
    'dim_product': (['product_id', 'product_name'], ['category', 'sub_category']),
    'dim_geography': (['country', 'state', 'city', 'region', 'market'], ['market_group']),
    'dim_order': (['order_id', 'order_date', 'customer_id'], ['ship_mode', 'order_priority']),
}
COUNTS = dict(dim_date=1468, dim_customer=4873, dim_product=10768,
              dim_geography=3819, dim_order=25754, fact_sales=51290)
TOTALS = dict(sales='12642905', profit='1467457.29128', quantity='178312',
              shipping_cost='1352815.70340')


class ValidationError(ValueError):
    pass


def write_csv(path, columns, rows):
    """Replace one complete file atomically, never expose a partial processed CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8-sig', newline='',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def normalize(raw):
    row = {target: unicodedata.normalize('NFC', raw[source].strip())
           for source, target in COLMAP.items()}
    if any(value == '' for value in row.values()):
        raise ValidationError('Empty required field')
    for name, limit in TEXT_LIMITS.items():
        if len(row[name]) > limit:
            raise ValidationError(f'{name} exceeds varchar({limit})')
    for name, (low, high) in INTEGER_LIMITS.items():
        value = Decimal(row[name])
        if not value.is_finite() or value != value.to_integral_value() or not low <= value <= high:
            raise ValidationError(f'{name} must be an integer in [{low}, {high}]')
        row[name] = int(value)
    for name in DECIMALS:
        value = Decimal(row[name])
        scale = 4 if name == 'discount' else 5
        if not value.is_finite() or abs(value) >= Decimal(10) ** (2 if name == 'discount' else 13):
            raise ValidationError(f'{name} is outside the database numeric range')
        if value != value.quantize(Decimal(1).scaleb(-scale)):
            raise ValidationError(f'{name} exceeds {scale} fractional digits')
        # The official report uses real numbers in Python. Decimal above only
        # validates the source against the database's range and precision.
        row[name] = float(value)
    if not 0 <= row['discount'] <= 1 or row['sales'] < 0 or row['shipping_cost'] < 0:
        raise ValidationError('Discount, sales or shipping_cost out of range')
    for name in ['order_date', 'ship_date']:
        value = datetime.strptime(row[name], '%Y-%m-%d %H:%M:%S.%f')
        if value.time() != datetime.min.time():
            raise ValidationError(f'{name} contains a non-midnight time; DATE would lose information')
        row[name] = value.date().isoformat()
    if row['ship_date'] < row['order_date']:
        raise ValidationError('ship_date precedes order_date')
    if Decimal(raw['Year'].strip()) != int(row['order_date'][:4]):
        raise ValidationError('Year differs from Order.Date')
    if raw['记录数'].strip() != '1':
        raise ValidationError('Record count must be 1')
    row['profit_margin'] = None if row['sales'] == 0 else row['profit'] / row['sales']
    if row['profit_margin'] is not None and (not math.isfinite(row['profit_margin']) or
                                            abs(row['profit_margin']) >= 10000000000):
        raise ValidationError('profit_margin exceeds numeric(18,8)')
    return row


def preprocess(source, output, report_path, rejected_path, check_baseline=False):
    source, output, report_path, rejected_path = map(Path, [source, output, report_path, rejected_path])
    if len({p.resolve() for p in [source, output, report_path, rejected_path]}) != 4:
        raise ValueError('Input, output, report and quarantine must have distinct paths')
    report = dict(status='validating', database_status='not_run', source=str(source),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  source_rows=0, source_columns=27, processed_columns=26,
                  rejected_rows=0, batch_errors=[], key_conflicts={},
                  official_reference='KDL_Main.pdf',
                  python_numeric_representation='float; CSV margin is not rounded to 8 places',
                  control_total_representation='Decimal from serialized numeric values')
    records, rejected, reasons = [], [], defaultdict(list)
    with source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = set(COLMAP) | {'Year', '记录数'}
        report['source_columns'] = len(reader.fieldnames or [])
        if len(reader.fieldnames or []) != 27 or set(reader.fieldnames) != required:
            report['batch_errors'].append('Source must contain exactly the 27 declared unique columns')
        else:
            for position, raw in enumerate(reader, 1):
                report['source_rows'] += 1
                try:
                    if None in raw or any(value is None for value in raw.values()):
                        raise ValidationError('CSV row has the wrong number of fields')
                    row = normalize(raw)
                    records.append((position, raw, row))
                except (ValueError, InvalidOperation, TypeError) as error:
                    rejected.append(dict(source_record=position, row_id=raw.get('Row.ID', ''),
                                         reason=str(error), raw_json=json.dumps(raw, ensure_ascii=False)))
    for name, (keys, attributes) in KEYS.items():
        groups = defaultdict(list)
        for index, (_, _, row) in enumerate(records):
            groups[tuple(row[k] for k in keys)].append(index)
        conflicts = 0
        for indices in groups.values():
            values = {tuple(records[i][2][a] for a in attributes) for i in indices}
            if len(values) > 1:
                conflicts += 1
                for i in indices:
                    reasons[i].append(f'{name}: same key has conflicting descriptions')
        report['key_conflicts'][name] = conflicts
    row_ids = defaultdict(list)
    for i, (_, _, row) in enumerate(records):
        row_ids[row['row_id']].append(i)
    for indices in row_ids.values():
        if len(indices) > 1:
            for i in indices:
                reasons[i].append('Duplicate row_id')
    for i, errors in reasons.items():
        position, raw, row = records[i]
        rejected.append(dict(source_record=position, row_id=row['row_id'], reason='; '.join(errors),
                             raw_json=json.dumps(raw, ensure_ascii=False)))
    valid = [row for i, (_, _, row) in enumerate(records) if i not in reasons]
    report['rejected_rows'] = len(rejected)
    report['valid_rows'] = len(valid)
    if not valid:
        report['batch_errors'].append('No valid source records')
    if valid:
        report['counts'] = {name: len({tuple(r[k] for k in keys) for r in valid}) for name, (keys, _) in KEYS.items()}
        first = min(r['order_date'] for r in valid)
        last = max(r['ship_date'] for r in valid)
        report['date_range'] = [first, last]
        report['counts']['dim_date'] = (datetime.fromisoformat(last) - datetime.fromisoformat(first)).days + 1
        report['counts']['fact_sales'] = len(valid)
        report['totals'] = {name: str(sum((Decimal(str(r[name])) for r in valid), Decimal(0))) for name in TOTALS}
        report['negative_profit_rows'] = sum(r['profit'] < 0 for r in valid)
        report['zero_sales_rows'] = sum(r['sales'] == 0 for r in valid)
        report['null_profit_margin_rows'] = sum(r['profit_margin'] is None for r in valid)
        if check_baseline:
            if report['counts'] != COUNTS:
                report['batch_errors'].append('Dimension/fact counts differ from KDL_Main.pdf')
            if any(Decimal(report['totals'][k]) != Decimal(v) for k, v in TOTALS.items()):
                report['batch_errors'].append('Measure totals differ from KDL_Main.pdf')
    write_csv(rejected_path, ['source_record', 'row_id', 'reason', 'raw_json'], sorted(rejected, key=lambda r: r['source_record']))
    report['rejected_file'] = str(rejected_path)
    if rejected or report['batch_errors']:
        report['status'] = 'rejected_batch'
    else:
        write_csv(output, OUTPUT_COLUMNS, valid)
        report['status'] = 'processed_only'
        report['output'] = str(output)
        report['output_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if report['status'] == 'rejected_batch':
        raise ValidationError(f'Batch rejected; processed output was not replaced. See {report_path} and {rejected_path}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/superstore.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/processed/superstore_processed.csv')
    parser.add_argument('--report', type=Path, default=ROOT / 'results/etl/validation.json')
    parser.add_argument('--rejected', type=Path, default=ROOT / 'results/etl/rejected_rows.csv')
    parser.add_argument('--check-baseline', action='store_true')
    args = parser.parse_args()
    try:
        result = preprocess(args.input, args.output, args.report, args.rejected, args.check_baseline)
    except ValidationError as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
