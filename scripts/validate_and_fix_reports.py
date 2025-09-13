"""
Validates and fixes reports.csv for screenshot pipeline.
- Adds deterministic id (sha1 of full image path)
- Ensures cluster_id exists
- Coerces confidences to float
- Handles missing/duplicate filenames
- Supports --images-root
- Atomic writes, idempotent
- Logs actions, prints next steps
"""
import argparse
import csv
import hashlib
import logging
import os
import sys
from tempfile import NamedTemporaryFile

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')


def sha1_of_path(path):
    h = hashlib.sha1()
    h.update(path.encode('utf-8'))
    return h.hexdigest()


def validate_and_fix_reports(input_csv, output_csv, images_root):
    seen = set()
    rows = []
    with open(input_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames + \
            ['id'] if 'id' not in reader.fieldnames else reader.fieldnames
        for row in reader:
            filename = row.get('filename', '').strip()
            if not filename:
                logging.warning('Missing filename, skipping row: %s', row)
                continue
            abs_path = os.path.abspath(os.path.join(images_root, filename))
            row['id'] = sha1_of_path(abs_path)
            if row['id'] in seen:
                logging.warning(
                    'Duplicate id for filename %s, skipping', filename)
                continue
            seen.add(row['id'])
            # Coerce confidences
            for k in ['ocr_confidence', 'screen_confidence']:
                try:
                    row[k] = float(row.get(k, 0) or 0)
                except Exception:
                    row[k] = 0.0
            # Ensure cluster_id
            if not row.get('cluster_id'):
                row['cluster_id'] = ''
            rows.append(row)
    # Atomic write
    with NamedTemporaryFile('w', delete=False, newline='', encoding='utf-8') as tf:
        writer = csv.DictWriter(tf, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        tempname = tf.name
    os.replace(tempname, output_csv)
    logging.info('Validated and fixed CSV written to %s', output_csv)
    print(f'Next: Run generate_clusters_json.py to cluster uncertain screenshots.')


def main():
    parser = argparse.ArgumentParser(
        description='Validate and fix reports.csv for screenshot pipeline.')
    parser.add_argument('--input-csv', required=True,
                        help='Path to input reports.csv')
    parser.add_argument('--output-csv', required=True,
                        help='Path to output fixed CSV')
    parser.add_argument(
        '--images-root', default='input_screenshots', help='Root directory for images')
    args = parser.parse_args()
    validate_and_fix_reports(args.input_csv, args.output_csv, args.images_root)


if __name__ == '__main__':
    main()
