#!/usr/bin/env python3
"""
relabel_with_rules.py

Re-run deterministic categorization over an existing annotated JSON file (e.g., final_output.json)
using the latest rules in config/categories.json and config/rules.json and the enhanced
pipeline/mapping_rules.py logic (regex + normalization + comment_translated preference).

Usage:
  python scripts/relabel_with_rules.py --input final_output.json --output final_output_relabel.json

Outputs a summary of category changes and counts.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple

from pipeline.mapping_rules import categorize_record_with_meta


def _collect_ocr_texts(record: Dict[str, Any]) -> List[str]:
    # The current schema stores a single 'extracted_text' per record (OCR of primary image)
    # In future we might store a list. Support both.
    texts: List[str] = []
    if isinstance(record.get('extracted_text'), str):
        texts.append(record['extracted_text'])
    elif isinstance(record.get('extracted_text'), list):
        texts.extend([t for t in record['extracted_text'] if isinstance(t, str)])
    return texts


def _collect_filenames(record: Dict[str, Any]) -> List[str]:
    fns: List[str] = []
    atts = record.get('attachments') or []
    if isinstance(atts, list):
        for url in atts:
            if not isinstance(url, str):
                continue
            name = url.rsplit('/', 1)[-1]
            name = name.split('?', 1)[0]
            fns.append(name)
    return fns


def relabel(input_path: Path, output_path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    data = json.loads(input_path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object keyed by record IDs")

    changes: Dict[str, Tuple[str, str]] = {}
    counts_before = Counter()
    counts_after = Counter()

    for rec_id, rec in data.items():
        if not isinstance(rec, dict):
            continue
        old_cat = rec.get('category') or ''
        counts_before[old_cat] += 1

        ocr_texts = _collect_ocr_texts(rec)
        filenames = _collect_filenames(rec)

        new_cat, conf = categorize_record_with_meta(rec, ocr_texts=ocr_texts, filenames=filenames, model_pred=None)
        rec['category'] = new_cat
        # Optionally update or set label_confidence
        rec['label_confidence'] = max(float(rec.get('label_confidence') or 0.0), conf)

        counts_after[new_cat] += 1
        if new_cat != old_cat:
            changes[rec_id] = (old_cat, new_cat)

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    summary = {
        'total_records': sum(counts_after.values()),
        'changed_records': len(changes),
        'counts_before': counts_before,
        'counts_after': counts_after,
    }
    return changes, summary  # type: ignore[return-value]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=Path('final_output.json'))
    parser.add_argument('--output', type=Path, default=Path('final_output_relabel.json'))
    args = parser.parse_args()

    changes, summary = relabel(args.input, args.output)

    print(f"Relabeled file saved to: {args.output}")
    print(f"Total records: {summary['total_records']}")
    print(f"Changed records: {summary['changed_records']}")
    print("\nTop categories before:")
    for cat, cnt in summary['counts_before'].most_common():
        print(f"  {cat or '(empty)'}: {cnt}")
    print("\nTop categories after:")
    for cat, cnt in summary['counts_after'].most_common():
        print(f"  {cat}: {cnt}")

    # Show sample of quality-related relabels for manual QA
    sample = 0
    print("\nSample relabeled to product_quality_issues:")
    for rec_id, (old_cat, new_cat) in changes.items():
        if new_cat == 'product_quality_issues':
            print(f"  {rec_id}: {old_cat} -> {new_cat}")
            sample += 1
            if sample >= 10:
                break


if __name__ == '__main__':
    main()
