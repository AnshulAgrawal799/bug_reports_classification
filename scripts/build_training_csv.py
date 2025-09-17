#!/usr/bin/env python3
"""
build_training_csv.py

Build a training CSV from a Firebase-like JSON of bug reports.

Input JSON format (top-level dict):
{
  "<id>": {
    "attachments": ["https://.../bug_reports%2FSomeScreenshot.jpg?..."],
    "category": "<canonical_or_old_label>",
    "comment": "...",
    "createdAt": "...",
    "email": "...",
    "hasResolved": false,
    "logFile": "https://.../bug_reports%2Fdate.txt?...",
    "name": "...",
    "userId": "..."
  },
  ...
}

This script produces a CSV with columns: id, text, category
Where `text` = comment + (joined filenames)  (OCR text is optional; you can merge it offline)

Usage:
  python scripts/build_training_csv.py --input final_output.json --output data/train.csv --category-is-canonical

Notes:
- If your input labels are old, you can run scripts/relabel_dataset.py to map them to canonical ids.
- Optionally, you can append OCR text later if you have it, to improve training quality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import unquote, urlparse
import csv


def _extract_filename_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        last_segment = parsed.path.rsplit('/', 1)[-1]
        decoded = unquote(last_segment)
        if '%2F' in last_segment:
            decoded = unquote(last_segment)
        if '/' in decoded:
            decoded = decoded.rsplit('/', 1)[-1]
        if '?' in decoded:
            decoded = decoded.split('?', 1)[0]
        return decoded
    except Exception:
        return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True, help='Input JSON of reports (e.g., final_output.json)')
    ap.add_argument('--output', type=Path, required=True, help='Output CSV path (e.g., data/train.csv)')
    ap.add_argument('--category-field', type=str, default='category')
    ap.add_argument('--text-fields', type=str, default='comment', help='Comma-separated record fields to include in text (default: comment)')
    args = ap.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fields = [f.strip() for f in args.text_fields.split(',') if f.strip()]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8', newline='') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=['id', 'text', 'category'])
        writer.writeheader()

        for rid, rec in data.items():
            attachments = (rec or {}).get('attachments', []) or []
            fnames = [_extract_filename_from_url(u) for u in attachments if u]
            text_parts = []
            for fld in fields:
                val = (rec or {}).get(fld, '')
                if val:
                    text_parts.append(str(val))
            if fnames:
                text_parts.append(' '.join(fnames))
            text = ' '.join(text_parts).strip()

            cat = (rec or {}).get(args.category_field, '') or ''

            writer.writerow({'id': rid, 'text': text, 'category': cat})

    print(f'Wrote training CSV -> {args.output}')


if __name__ == '__main__':
    main()
