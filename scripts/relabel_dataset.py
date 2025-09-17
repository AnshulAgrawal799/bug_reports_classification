#!/usr/bin/env python3
"""
relabel_dataset.py

Relabel a dataset from old, screen-focused categories to the new canonical taxonomy
(ids in config/categories.json).

Usage examples:
  python scripts/relabel_dataset.py --input data.csv --output relabeled.csv --col category
  python scripts/relabel_dataset.py --input data.json --output relabeled.json --json --col category

Notes:
- For CSV, expects a column with the label name (default: category)
- For JSON, expects a top-level dict of id -> record objects containing the label field
- Unmapped labels are set to 'unclear_insufficient_info'
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict

# Old->new mapping
OLD_TO_NEW: Dict[str, str] = {
    # screen-focused to problem-focused
    'login_screens': 'authentication_access',
    'error_screens': 'functional_errors',
    'navigation_screens': 'ui_ux_issues',
    'form_screens': 'ui_ux_issues',
    'loading_screens': 'performance_issues',
    'transaction_screens': 'integration_failures',
    'success_screens': 'functional_errors',
    # filename-based
    'error_screenshots': 'functional_errors',
    'login_screenshots': 'authentication_access',
    'navigation_screenshots': 'ui_ux_issues',
    'general_screenshots': 'unclear_insufficient_info',
    'image_files': 'unclear_insufficient_info',
    'log_files': 'unclear_insufficient_info',
    # metadata-based
    'reported_issues': 'functional_errors',
    'feature_requests': 'feature_requests',
    'test_data': 'unclear_insufficient_info',
    # fallbacks
    'no_attachments': 'unclear_insufficient_info',
    'uncategorized': 'unclear_insufficient_info',
    'processing_error': 'unclear_insufficient_info',
    # arrange_by_headers & misc
    'empty_or_unreadable_headers': 'unclear_insufficient_info',
    'minimal_text_content': 'unclear_insufficient_info',
}

DEFAULT_FALLBACK = 'unclear_insufficient_info'


def map_label(old: str) -> str:
    if not old:
        return DEFAULT_FALLBACK
    return OLD_TO_NEW.get(old.strip(), DEFAULT_FALLBACK)


def relabel_csv(inp: Path, out: Path, col: str) -> None:
    with open(inp, 'r', encoding='utf-8') as f_in, open(out, 'w', encoding='utf-8', newline='') as f_out:
        reader = csv.DictReader(f_in)
        fieldnames = list(reader.fieldnames or [])
        if col not in fieldnames:
            raise SystemExit(f"Column '{col}' not found in {inp}")
        # Write the same columns
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            row[col] = map_label(row.get(col, ''))
            writer.writerow(row)


def relabel_json(inp: Path, out: Path, col: str) -> None:
    with open(inp, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Expect dict of id -> record
    if isinstance(data, dict):
        for _id, rec in data.items():
            old = (rec or {}).get(col, '')
            rec[col] = map_label(old)
    elif isinstance(data, list):
        for rec in data:
            if isinstance(rec, dict):
                old = rec.get(col, '')
                rec[col] = map_label(old)
    else:
        raise SystemExit('Unsupported JSON structure (expected dict or list)')

    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--col', type=str, default='category', help='Column/field name for labels (default: category)')
    ap.add_argument('--json', action='store_true', help='Treat input/output as JSON instead of CSV')
    args = ap.parse_args()

    if args.json:
        relabel_json(args.input, args.output, args.col)
    else:
        relabel_csv(args.input, args.output, args.col)

    print(f"Wrote relabeled dataset -> {args.output}")


if __name__ == '__main__':
    main()
