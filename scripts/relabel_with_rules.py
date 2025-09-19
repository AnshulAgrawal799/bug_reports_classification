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
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Ensure project root is on sys.path when executing from scripts/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.mapping_rules import categorize_record_with_meta
from pipeline.predictor import load_default_predictor
from pipeline.translation import detect_and_translate


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


def relabel(input_path: Path, output_path: Path, use_model: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    data = json.loads(input_path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object keyed by record IDs")

    changes: Dict[str, Tuple[str, str]] = {}
    counts_before = Counter()
    counts_after = Counter()
    reason_counts = Counter()
    functional_errors_by_reason = Counter()

    predictor = load_default_predictor() if use_model else None

    for rec_id, rec in data.items():
        if not isinstance(rec, dict):
            continue
        old_cat = rec.get('category') or ''
        counts_before[old_cat] += 1

        ocr_texts = _collect_ocr_texts(rec)
        filenames = _collect_filenames(rec)

        # Language detection and translation to enrich signals (mirrors run_pipeline)
        original_comment: str = rec.get('comment', '') or ''
        translated_comment, detected_lang = detect_and_translate(original_comment)
        if translated_comment:
            rec['comment_translated'] = translated_comment

        model_pred = None
        if predictor and predictor.is_ready():
            record_for_pred = dict(rec)
            # Prefer translated comment for model if present
            if rec.get('comment_translated'):
                record_for_pred['comment_translated'] = rec['comment_translated']
            model_pred = predictor.predict_from_record(record_for_pred, ocr_texts=ocr_texts, filenames=filenames)

        new_cat, conf, reason = categorize_record_with_meta(rec, ocr_texts=ocr_texts, filenames=filenames, model_pred=model_pred)
        rec['category'] = new_cat
        # Optionally update or set label_confidence
        rec['label_confidence'] = max(float(rec.get('label_confidence') or 0.0), conf)
        rec['label_reason'] = reason
        if detected_lang and detected_lang != 'en' and translated_comment:
            rec['detected_lang'] = detected_lang

        counts_after[new_cat] += 1
        reason_counts[reason] += 1
        if new_cat == 'functional_errors':
            functional_errors_by_reason[reason] += 1
        if new_cat != old_cat:
            changes[rec_id] = (old_cat, new_cat)

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    summary = {
        'total_records': sum(counts_after.values()),
        'changed_records': len(changes),
        'counts_before': counts_before,
        'counts_after': counts_after,
        'reason_counts': reason_counts,
        'functional_errors_by_reason': functional_errors_by_reason,
    }
    return changes, summary  # type: ignore[return-value]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=Path('final_output.json'))
    parser.add_argument('--output', type=Path, default=Path('final_output_relabel.json'))
    parser.add_argument('--use-model', action='store_true', help='Use ML predictor to supply model_pred to rules')
    args = parser.parse_args()

    changes, summary = relabel(args.input, args.output, use_model=args.use_model)

    print(f"Relabeled file saved to: {args.output}")
    print(f"Total records: {summary['total_records']}")
    print(f"Changed records: {summary['changed_records']}")
    print("\nTop categories before:")
    for cat, cnt in summary['counts_before'].most_common():
        print(f"  {cat or '(empty)'}: {cnt}")
    print("\nTop categories after:")
    for cat, cnt in summary['counts_after'].most_common():
        print(f"  {cat}: {cnt}")

    # Reason code breakdown
    print("\nReason code breakdown (all categories):")
    for reason, cnt in summary['reason_counts'].most_common():
        print(f"  {reason}: {cnt}")
    print("\nFunctional Errors by reason:")
    for reason, cnt in summary['functional_errors_by_reason'].most_common():
        print(f"  {reason}: {cnt}")

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
